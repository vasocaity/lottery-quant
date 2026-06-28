import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { DrawsModule } from './draws/draws.module';
import { PredictionsModule } from './predictions/predictions.module';
import { MlModule } from './ml/ml.module';
import { WebsocketModule } from './websocket/websocket.module';

@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true }),
    MlModule,
    WebsocketModule,
    DrawsModule,
    PredictionsModule,
  ],
})
export class AppModule {}
