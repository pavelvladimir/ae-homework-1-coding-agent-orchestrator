import type { Ticket, WebhookRetryEvent } from "./domain";

export class TicketRepository {
  private readonly tickets: Ticket[] = [];

  save(ticket: Ticket): void {
    this.tickets.push(ticket);
  }

  list(): Ticket[] {
    return [...this.tickets];
  }
}

export class WebhookEventRepository {
  private readonly retryEvents: WebhookRetryEvent[] = [];

  save(event: WebhookRetryEvent): void {
    this.retryEvents.push(event);
  }

  hasProcessed(eventId: string): boolean {
    return this.retryEvents.some((event) => event.eventId === eventId);
  }
}
