# Support Service

This is a tiny `pnpm` + Fastify + TypeScript example repository that PatchPilot can analyze during demos.

It represents a small customer-support API with a couple of realistic constraints:

- ticket routes accept JSON payloads
- webhook retries are accepted, but not yet idempotent
- settings still point at SQLite, which makes migration planning realistic
- observability is weak because request correlation logging is still missing
- tests run through Vitest, linting runs through ESLint, and install is guarded to `pnpm`

## Commands

```bash
pnpm install
pnpm lint
pnpm build
pnpm test
pnpm dev
```

The project is intentionally small so the orchestration artifacts stay easy to read in class or during a GitHub walkthrough.
