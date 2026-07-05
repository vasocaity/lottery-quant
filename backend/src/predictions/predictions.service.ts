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

  /**
   * Honest scoreboard: for every draw, find the newest prediction made BEFORE
   * that draw's date and check whether the winning number was in the list.
   * Reports actual hits next to the hit count pure chance would produce
   * (top-10 of 100 → 10% for last2, top-20 of 1000 → 2% for back3).
   */
  async hitRate() {
    const [draws, preds] = await Promise.all([
      this.prisma.draw.findMany({ orderBy: { date: 'asc' } }),
      this.prisma.prediction.findMany({ orderBy: { createdAt: 'asc' } }),
    ]);

    const stats = {
      last2: { evaluated: 0, hits: 0, k: 10, pool: 100 },
      back3: { evaluated: 0, hits: 0, k: 20, pool: 1000 },
    };

    let i = -1;
    for (const draw of draws) {
      while (i + 1 < preds.length && preds[i + 1].createdAt < draw.date) i++;
      if (i < 0) continue; // draw predates every prediction (e.g. backfilled history)

      const stored = preds[i].items as any;
      const back3Numbers: string[] = (stored?.back3_items ?? (Array.isArray(stored) ? stored : []))
        .slice(0, stats.back3.k)
        .map((x: any) => x.number);
      const last2Numbers: string[] = (stored?.last2_items ?? [])
        .slice(0, stats.last2.k)
        .map((x: any) => x.number);

      if (back3Numbers.length) {
        stats.back3.evaluated++;
        if (back3Numbers.includes(draw.back3)) stats.back3.hits++;
      }
      if (last2Numbers.length && draw.last2) {
        stats.last2.evaluated++;
        if (last2Numbers.includes(draw.last2)) stats.last2.hits++;
      }
    }

    const summarize = (s: { evaluated: number; hits: number; k: number; pool: number }) => ({
      evaluated: s.evaluated,
      hits: s.hits,
      hitRate: s.evaluated ? s.hits / s.evaluated : null,
      expectedRate: s.k / s.pool,
      expectedHits: Number(((s.evaluated * s.k) / s.pool).toFixed(2)),
    });
    return { last2: summarize(stats.last2), back3: summarize(stats.back3) };
  }

  /** Called after a new official draw is added: retrain + re-predict automatically. */
  async onNewDraw() {
    this.logger.log('New draw detected — retraining + re-predicting');
    await this.trainModel();
    return this.predict();
  }
}
