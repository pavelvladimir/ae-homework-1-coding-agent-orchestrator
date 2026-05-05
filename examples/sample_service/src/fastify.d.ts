import "fastify";

import type { AppConfig } from "./domain";
import type { TicketRepository, WebhookEventRepository } from "./repository";

declare module "fastify" {
  interface FastifyInstance {
    configValues: AppConfig;
    ticketRepository: TicketRepository;
    webhookRepository: WebhookEventRepository;
  }
}
