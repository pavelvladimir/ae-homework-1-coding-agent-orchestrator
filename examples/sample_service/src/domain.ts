export interface AppConfig {
  serviceName: string;
  databaseUrl: string;
  enableAdminAuth: boolean;
  requestTimeoutMs: number;
}

export interface TicketInput {
  email: string;
  message: string;
  topic: string;
}

export interface Ticket extends TicketInput {
  id: string;
  createdAt: string;
}

export interface WebhookRetryEvent {
  eventId: string;
  provider: string;
  receivedAt: string;
}
