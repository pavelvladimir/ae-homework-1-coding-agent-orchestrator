import type { AppConfig } from "./domain";

export function loadConfig(): AppConfig {
  return {
    serviceName: "support-service",
    databaseUrl: "sqlite:///support.db",
    enableAdminAuth: false,
    requestTimeoutMs: 3000,
  };
}
