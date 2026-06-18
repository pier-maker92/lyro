# [Project name]

_Replace the heading above with the project's name, and this line with one sentence describing what this app does for users._

## Run & Operate

- `pnpm --filter @workspace/api-server run dev` — run the API server (port 5000)
- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages
- `pnpm --filter @workspace/api-spec run codegen` — regenerate API hooks and Zod schemas from the OpenAPI spec
- `pnpm --filter @workspace/db run push` — push DB schema changes (dev only)
- Required env: `DATABASE_URL` — Postgres connection string

## Stack

- pnpm workspaces, Node.js 24, TypeScript 5.9
- API: Express 5
- DB: PostgreSQL + Drizzle ORM
- Validation: Zod (`zod/v4`), `drizzle-zod`
- API codegen: Orval (from OpenAPI spec)
- Build: esbuild (CJS bundle)

## Where things live

_Populate as you build — short repo map plus pointers to the source-of-truth file for DB schema, API contracts, theme files, etc._

## Architecture decisions

_Populate as you build — non-obvious choices a reader couldn't infer from the code (3-5 bullets)._

## Product

**Visual Lyrics** — a TikTok/Reels-style mobile app. The user picks a photo or video; the
app analyzes the visual and returns matching song lyrics grouped into 5 moods
(Amore / Avventura / Divertente / Relax / Festa). In the full-screen player, swipe
left/right to change mood and up/down to move between matches.

- Frontend: `artifacts/mobile` (Expo). Single screen `app/index.tsx` (home -> loading -> player).
- Backend proxy: `artifacts/api-server` `/api/analyze`.
- Engine: `services/lyrics-engine` (Python FastAPI + ChromaDB + OpenRouter embeddings), port 8000.

## Architecture decisions

- The lyrics engine is a **standalone Python workflow**, not an artifact. It must be wired
  into production before deploying the backend, or `/api/analyze` breaks. See `.agents/memory/visual-lyrics.md`.
- Client sends visuals as resized JPEG data URLs (height 720) to keep payloads small; api-server json limit is 25mb.

## User preferences

- User communicates in **Italian** — respond in Italian.
- **No emojis** in the UI.

## Gotchas

_Populate as you build — sharp edges, "always run X before Y" rules._

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details
