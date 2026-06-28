import { Injectable, Logger } from '@nestjs/common';
import { PrismaService } from '../prisma.service';
import { MlService } from '../ml/ml.service';
import { DrawsService } from '../draws/draws.service';
import { PredictionsGateway } from '../websocket/predictions.gateway';

@Injectable()
export class PredictionsService {
  private readonly logger = new Logger(PredictionsService.name);

  constructor(
    private prisma: PrismaService,
    private ml: MlService,
    private draws: DrawsService,
    private gateway: PredictionsGateway,
  ) {}

  /** Full pipeline: pull draws -> train ML -> persist model version -> broadcast. */
  async trainModel() {
    const draws = await this.draws.forMl();
    this.gateway.emitProgress({ step: 'Sending draws to ML service', pct: 10 });

    const res = await this.ml.train(draws);
    this.gateway.emitProgress({ step: 'Persisting model version', pct: 80 });

    // deactivate previous, store new version metadata
    await this.prisma.modelVersion.updateMany({ data: { isActive: false } });
    const version = await this.prisma.modelVersion.create({
      data: {
        trainedAt: new Date(res.trained_at),
        nDraws: res.n_draws,
        weightLr: res.weights.lr,
        weightRf: res.weights.rf,
        weightGb: res.weights.gb,
        metrics: res.metrics,
        isActive: true,
      },
    });

    this.gateway.emitProgress({ step: 'Done', pct: 100 });
    this.gateway.emitModelTrained(version);
    return version;
  }

  /** Score all combos and persist + broadcast the top-N. */
  async predict(topN = 20) {
    const draws = await this.draws.forMl();
    const result = await this.ml.predict(draws, topN);
    const { items, last2_items } = result;

    const active = await this.prisma.modelVersion.findFirst({
      where: { isActive: true },
      orderBy: { createdAt: 'desc' },
    });

    const prediction = await this.prisma.prediction.create({
      data: {
        modelVersionId: active?.id ?? 0,
        items: { back3_items: items, last2_items } as any,
      },
    });

    this.gateway.emitPrediction({ back3_items: items, last2_items });
    return { id: prediction.id, items, last2_items };
  }

  async backtest() {
    const draws = await this.draws.forMl();
    return this.ml.backtest(draws);
  }

  featureImportance() {
    return this.ml.featureImportance();
  }

  async latest() {
    const pred = await this.prisma.prediction.findFirst({ orderBy: { createdAt: 'desc' } });
    if (!pred) return null;
    const stored = pred.items as any;
    return {
      id: pred.id,
      items: stored?.back3_items ?? (Array.isArray(stored) ? stored : []),
      last2_items: stored?.last2_items ?? [],
    };
  }

  /** Called after a new official draw is added: retrain + re-predict automatically. */
  async onNewDraw() {
    this.logger.log('New draw detected — retraining + re-predicting');
    await this.trainModel();
    return this.predict();
  }
}
