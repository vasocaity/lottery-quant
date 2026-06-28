import { Module } from '@nestjs/common';
import { PredictionsGateway } from './predictions.gateway';

@Module({
  providers: [PredictionsGateway],
  exports: [PredictionsGateway],
})
export class WebsocketModule {}
