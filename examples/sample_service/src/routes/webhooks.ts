import type { FastifyInstance } from "fastify";

interface RetryWebhookBody {
  eventId: string;
  provider?: string;
}

export default async function registerWebhookRoutes(app: FastifyInstance) {
  app.post<{ Body: Partial<RetryWebhookBody> }>(
    "/retry",
    async function retryWebhookHandler(request, reply) {
      const payload = request.body ?? {};
      const eventId = String(payload.eventId ?? "").trim();
      const provider = String(payload.provider ?? "unknown").trim().toLowerCase();

      if (!eventId) {
        return reply.code(400).send({ error: "event_id_required" });
      }

      // TODO: make this endpoint idempotent before enabling upstream retries.
      app.webhookRepository.save({
        eventId,
        provider,
        receivedAt: new Date().toISOString(),
      });

      return reply.code(202).send({ accepted: true });
    },
  );
}
