import { Module, forwardRef } from '@nestjs/common';
import { DrawsService } from './draws.service';
import { DrawsController } from './draws.controller';
import { PrismaService } from '../prisma.service';
import { PredictionsModule } from '../predictions/predictions.module';

@Module({
  imports: [forwardRef(() => PredictionsModule)],
  controllers: [DrawsController],
  providers: [DrawsService, PrismaService],
  exports: [DrawsService],
})
export class DrawsModule {}
