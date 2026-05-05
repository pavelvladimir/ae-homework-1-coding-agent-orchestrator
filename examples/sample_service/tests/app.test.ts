import { afterEach, describe, expect, it } from "vitest";

import { buildApp } from "../src/app";

const openApps: Array<Awaited<ReturnType<typeof buildApp>>> = [];

afterEach(async function () {
  while (openApps.length > 0) {
    const app = openApps.pop();
    if (app) {
      await app.close();
    }
  }
});

describe("support service", function () {
  it("health route returns service metadata", async function () {
    const app = await buildApp();
    openApps.push(app);

    const response = await app.inject({
      method: "GET",
      url: "/health",
    });

    expect(response.statusCode).toBe(200);
    expect(response.json().ok).toBe(true);
  });

  it("ticket route rejects invalid email", async function () {
    const app = await buildApp();
    openApps.push(app);

    const response = await app.inject({
      method: "POST",
      url: "/tickets",
      payload: {
        email: "invalid",
        message: "Need help with webhook retries",
      },
    });

    expect(response.statusCode).toBe(400);
    expect(response.json().error).toBe("invalid_email");
  });

  it("ticket route persists valid submissions", async function () {
    const app = await buildApp();
    openApps.push(app);

    const createResponse = await app.inject({
      method: "POST",
      url: "/tickets",
      payload: {
        email: "team@example.com",
        message: "Need help because webhook retries keep creating duplicates",
        topic: "webhooks",
      },
    });

    expect(createResponse.statusCode).toBe(201);

    const listResponse = await app.inject({
      method: "GET",
      url: "/tickets",
    });

    expect(listResponse.statusCode).toBe(200);
    expect(listResponse.json().count).toBe(1);
  });
});
