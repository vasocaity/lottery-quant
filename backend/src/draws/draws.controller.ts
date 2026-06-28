import { Body, Controller, Get, Post } from '@nestjs/common';
import { DrawsService } from './draws.service';
import { PredictionsService } from '../predictions/predictions.service';

@Controller('draws')
export class DrawsController {
  constructor(
    private draws: DrawsService,
    private predictions: PredictionsService,
  ) {}

  @Get()
  list() {
    return this.draws.findAll();
  }

  @Post()
  async add(@Body() dto: { date: string; back3: string; last2?: string; firstPrize?: string }) {
    const draw = await this.draws.create(dto);
    // Self-improvement loop: a new official result triggers retrain + re-predict.
    // Fire-and-forget so the POST returns fast; progress streams over WebSocket.
    this.predictions.onNewDraw().catch(() => undefined);
    return draw;
  }

  @Post('import')
  bulk(@Body() dto: { items: { date: string; back3: string; last2?: string }[] }) {
    return this.draws.bulkImport(dto.items);
  }
}
