import { Module, forwardRef } from '@nestjs/common';
import { PredictionsService } from './predictions.service';
import { PredictionsController } from './predictions.controller';
import { PrismaService } from '../prisma.service';
import { MlModule } from '../ml/ml.module';
import { DrawsModule } from '../draws/draws.module';
import { WebsocketModule } from '../websocket/websocket.module';

@Module({
  imports: [MlModule, forwardRef(() => DrawsModule), WebsocketModule],
  controllers: [PredictionsController],
  providers: [PredictionsService, PrismaService],
  exports: [PredictionsService],
})
export class PredictionsModule {}
