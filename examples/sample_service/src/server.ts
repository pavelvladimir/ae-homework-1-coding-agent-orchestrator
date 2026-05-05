import { buildApp } from "./app";

async function start() {
  const app = await buildApp();
  const port = Number(process.env.PORT ?? 3000);

  try {
    await app.listen({ port, host: "0.0.0.0" });
  } catch (error) {
    app.log.error(error);
    process.exitCode = 1;
  }
}

void start();
