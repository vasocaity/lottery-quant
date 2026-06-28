import { Module } from '@nestjs/common';
import { HttpModule } from '@nestjs/axios';
import { ConfigModule } from '@nestjs/config';
import { MlService } from './ml.service';

@Module({
  imports: [HttpModule, ConfigModule],
  providers: [MlService],
  exports: [MlService],
})
export class MlModule {}
