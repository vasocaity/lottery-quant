import { Controller, Get, Post, Query } from '@nestjs/common';
import { PredictionsService } from './predictions.service';

@Controller('predictions')
export class PredictionsController {
  constructor(private svc: PredictionsService) {}

  @Post('train')
  train() {
    return this.svc.trainModel();
  }

  @Post('run')
  run(@Query('topN') topN?: string) {
    return this.svc.predict(topN ? parseInt(topN, 10) : 20);
  }

  @Get('backtest')
  backtest() {
    return this.svc.backtest();
  }

  @Get('feature-importance')
  fi() {
    return this.svc.featureImportance();
  }

  @Get('latest')
  latest() {
    return this.svc.latest();
  }

  @Get('hit-rate')
  hitRate() {
    return this.svc.hitRate();
  }
}
