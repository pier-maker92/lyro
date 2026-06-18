---
name: Visual Lyrics architecture
description: How the Visual Lyrics app is wired across three services, and the production deploy caveat.
---

# Visual Lyrics

Expo mobile app (TikTok/Reels style). User picks a photo/video -> client resizes to a
JPEG data URL (height 720) -> POST /api/analyze -> response is keyed by 5 moods
(love/adventure/funny/chill/party), each an array of lyric matches -> full-screen
reels player (swipe horizontal = change mood, vertical = change match).

## Three services
- `artifacts/mobile` — Expo client (the only artifact for this product).
- `artifacts/api-server` — Express; `/api/analyze` is a thin proxy.
- `services/lyrics-engine` — standalone Python FastAPI (uvicorn, port 8000) doing the
  embeddings (OpenRouter `nvidia/llama-nemotron-embed-vl-1b-v2:free`, 2048-dim, text+image)
  + ChromaDB retrieval. Express proxies to `localhost:8000`.

## Production deploy caveat (important)
**Why:** `services/lyrics-engine` is run by a standalone Replit workflow, NOT registered
as an artifact / not in any `artifact.toml`. Only artifacts deploy. So in a published
backend, `/api/analyze` will fail because nothing serves port 8000.
**How to apply:** Before deploying the backend to production, either (a) make the Python
service an artifact.toml service, or (b) have Express spawn/host it. The Expo client
itself (Expo Launch / App Store) is independent, but it points at the production API
domain, so the backend must be fixed first or analysis breaks in prod.

## Embedding/retrieval note
Mood conditioning works: for a concert photo the `party` mood returns the lowest
distances. The seeded catalog is 30 ORIGINAL placeholder stanzas (6 per mood) in
`services/lyrics-engine/catalog.json` — meant to be swapped for the user's real dataset.
