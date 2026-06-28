import { Injectable } from '@nestjs/common';
import { PrismaService } from '../prisma.service';

@Injectable()
export class DrawsService {
  constructor(private prisma: PrismaService) {}

  findAll() {
    return this.prisma.draw.findMany({ orderBy: { date: 'asc' } });
  }

  async create(dto: { date: string; back3: string; last2?: string; firstPrize?: string }) {
    return this.prisma.draw.upsert({
      where: { date: new Date(dto.date) },
      update: { back3: dto.back3, last2: dto.last2, firstPrize: dto.firstPrize },
      create: {
        date: new Date(dto.date),
        back3: dto.back3,
        last2: dto.last2,
        firstPrize: dto.firstPrize,
      },
    });
  }

  /** Returns draws as {date, back3} pairs ready for the ML service. */
  async forMl(): Promise<{ date: string; back3: string }[]> {
    const rows = await this.findAll();
    return rows.map((r) => ({
      date: r.date.toISOString().slice(0, 10),
      back3: r.back3,
    }));
  }

  async bulkImport(items: { date: string; back3: string; last2?: string }[]) {
    let count = 0;
    for (const it of items) {
      await this.create(it);
      count++;
    }
    return { imported: count };
  }
}
