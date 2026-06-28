import {
  WebSocketGateway, WebSocketServer, SubscribeMessage,
} from '@nestjs/websockets';
import { Server } from 'socket.io';
import { Logger } from '@nestjs/common';

/**
 * Pushes live training progress + new predictions to connected React clients.
 * Frontend subscribes via socket.io and updates the UI without polling.
 */
@WebSocketGateway({ cors: { origin: '*' }, namespace: '/live' })
export class PredictionsGateway {
  @WebSocketServer() server: Server;
  private readonly logger = new Logger(PredictionsGateway.name);

  emitProgress(payload: { step: string; pct: number }) {
    this.server.emit('training:progress', payload);
  }

  emitModelTrained(version: unknown) {
    this.server.emit('model:trained', version);
  }

  emitPrediction(payload: { back3_items: unknown; last2_items: unknown }) {
    this.server.emit('prediction:new', payload);
  }

  @SubscribeMessage('ping')
  handlePing() {
    return { event: 'pong', data: Date.now() };
  }
}
