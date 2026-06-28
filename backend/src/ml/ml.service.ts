import { Injectable, Logger, HttpException } from '@nestjs/common';
import { HttpService } from '@nestjs/axios';
import { firstValueFrom } from 'rxjs';
import { ConfigService } from '@nestjs/config';

export interface DrawDto { date: string; back3: string; }
export interface PredictItem {
  rank: number; number: string; score: number;
  lr_score: number; rf_score: number; gb_score: number;
  confidence: string; top_features: Array<{ name: string; value: number; importance: number }>;
}

/**
 * Thin HTTP client to the Python FastAPI ML microservice.
 * The backend NEVER does ML math itself — it delegates to this service,
 * which owns the trained .pkl artifact.
 */
@Injectable()
export class MlService {
  private readonly logger = new Logger(MlService.name);
  private readonly baseUrl: string;

  constructor(private http: HttpService, private config: ConfigService) {
    this.baseUrl = this.config.get('ML_SERVICE_URL', 'http://ml-service:8000');
  }

  private async post<T>(path: string, body: unknown): Promise<T> {
    try {
      const { data } = await firstValueFrom(
        this.http.post<T>(`${this.baseUrl}${path}`, body, { timeout: 120_000 }),
      );
      return data;
    } catch (err: any) {
      this.logger.error(`ML ${path} failed: ${err.message}`);
      throw new HttpException(`ML service error: ${err.message}`, 502);
    }
  }

  private async get<T>(path: string): Promise<T> {
    const { data } = await firstValueFrom(this.http.get<T>(`${this.baseUrl}${path}`));
    return data;
  }

  train(draws: DrawDto[]) {
    return this.post<{ trained_at: string; weights: any; metrics: any; n_draws: number }>(
      '/train', { draws },
    );
  }

  predict(draws: DrawDto[], topN = 20) {
    return this.post<PredictItem[]>('/predict', { draws, top_n: topN });
  }

  backtest(draws: DrawDto[]) {
    return this.post<{ results: any[]; optimized_weights: any }>('/backtest', { draws });
  }

  featureImportance() {
    return this.get<{ importances: Record<string, number>; weights: any }>('/feature-importance');
  }

  modelInfo() {
    return this.get<any>('/model-info');
  }

  health() {
    return this.get<{ status: string; model_present: boolean }>('/health');
  }
}
