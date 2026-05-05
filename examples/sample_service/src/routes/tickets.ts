import { randomUUID } from "node:crypto";

import type { FastifyInstance } from "fastify";

import type { TicketInput } from "../domain";

export default async function registerTicketRoutes(app: FastifyInstance) {
  app.get("/", async function listTicketsHandler() {
    const tickets = app.ticketRepository.list();

    return {
      items: tickets,
      count: tickets.length,
    };
  });

  app.post<{ Body: Partial<TicketInput> }>(
    "/",
    async function submitTicketHandler(request, reply) {
      const payload = request.body ?? {};
      const email = String(payload.email ?? "").trim().toLowerCase();
      const message = String(payload.message ?? "").trim();
      const topic = String(payload.topic ?? "general").trim().toLowerCase();

      if (!email || !email.includes("@")) {
        return reply.code(400).send({ error: "invalid_email" });
      }

      if (message.length < 10) {
        return reply.code(400).send({ error: "message_too_short" });
      }

      const ticket = {
        id: randomUUID(),
        email,
        message,
        topic,
        createdAt: new Date().toISOString(),
      };

      app.ticketRepository.save(ticket);
      // TODO: log requestId, route, topic, and ticketId in a structured way.
      return reply.code(201).send({ ticketId: ticket.id });
    },
  );
}
