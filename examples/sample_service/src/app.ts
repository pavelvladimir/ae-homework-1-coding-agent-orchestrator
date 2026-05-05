import Fastify from "fastify";

import { loadConfig } from "./config";
import { TicketRepository, WebhookEventRepository } from "./repository";
import registerTicketRoutes from "./routes/tickets";
import registerWebhookRoutes from "./routes/webhooks";

export async function buildApp() {
  const config = loadConfig();
  const app = Fastify({
    logger: false,
  });

  app.decorate("configValues", config);
  app.decorate("ticketRepository", new TicketRepository());
  app.decorate("webhookRepository", new WebhookEventRepository());

  app.get("/health", async function healthHandler() {
    return {
      ok: true,
      service: config.serviceName,
      database: config.databaseUrl,
    };
  });

  // TODO: enable structured request logging with request correlation and route timing.
  await app.register(registerTicketRoutes, { prefix: "/tickets" });
  await app.register(registerWebhookRoutes, { prefix: "/webhooks" });

  return app;
}
