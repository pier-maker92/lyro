---
name: Visual Lyrics architecture
description: How the Visual Lyrics app is wired across three services, and the production deploy caveat.
---

# Visual Lyrics

Expo mobile app (TikTok/Reels style). User picks a photo/video -> client resizes to a
JPEG data URL (height 720) -> POST /api/analyze -> response is a map: a guaranteed
`best` bucket plus one bucket per mood actually found, each an array of lyric matches
-> full-screen reels player (swipe horizontal = change bucket, vertical = change match).
See the mood-logic section below — the mood taxonomy is dynamic, NOT a fixed 5.

## Three services
- `artifacts/mobile` — Expo client (the only artifact for this product).
- `artifacts/api-server` — Express; `/api/analyze` is a thin proxy.
- `services/lyrics-engine` — standalone Python FastAPI (uvicorn, port 8000) doing the
  embeddings (LOCAL TinyCLIP `wkcn/TinyCLIP-ViT-8M-16-Text-3M-YFCC15M` via
  sentence-transformers, 512-dim, image-only query) + ChromaDB retrieval. Express
  proxies to `localhost:8000`. See lyrics-engine-tinyclip.md for the embedding details.

## Production deploy caveat (important) — RESOLVED via sidecar launcher
**Why:** `services/lyrics-engine` is run by a standalone Replit workflow, NOT registered
as an artifact / not in any `artifact.toml`. Only artifacts deploy. So in a published
backend, `/api/analyze` fails with `ECONNREFUSED 127.0.0.1:8000` because nothing serves
port 8000.
**Fix in place:** the api-server's production run command is `artifacts/api-server/start-prod.sh`
(set in its `artifact.toml` `[services.production.run]`). The script starts `uvicorn main:app`
for the engine on `127.0.0.1:8000` as an in-container sidecar, then `exec node` for Express.
Both run in the same autoscale container; Express reaches the engine over localhost.
**Prereqs that make this work in prod (verify if it ever breaks again):** the ChromaDB
`services/lyrics-engine/TinyCLAPdb/` (~217M) is git-tracked so it ships; `chromadb` +
torch/sentence-transformers are root `pyproject.toml` deps so the platform `uv sync` installs
them at deploy build; `MUSIXMATCH_API_KEY` is a global secret (available in prod).
**Cold-start tradeoff:** on autoscale, scale-from-zero reloads the 217M Chroma index + TinyCLIP
model each time, so the first `/api/analyze` after a cold start is slow (model warms in uvicorn
lifespan; the port binds immediately so it's latency, not ECONNREFUSED). Switch the deployment
to `vm` (always-on) if cold-start latency becomes a problem.

## Engine Python deps must be declared in root pyproject.toml (prod-only crash)
**Why:** the dev `.pythonlibs` had `numpy`/`pillow`/`sentence-transformers`/`torch`/`transformers`
installed ad-hoc, so the engine ran locally — but they were NOT in root `pyproject.toml`
`[project].dependencies`. Production deploy installs ONLY locked/declared deps, so uvicorn
crashed importing `embeddings.py` (ImportError) → engine never bound 8000 → `/api/analyze`
still 502'd with ECONNREFUSED even after the sidecar launcher was wired in.
**How to apply:** anything `services/lyrics-engine/*.py` imports at module load must be a declared
root dependency, and `uv.lock` must be regenerated (`uv lock`). After ANY engine import change,
re-lock and redeploy.
**Two uv gotchas hit here:** (1) the giant `[tool.uv.sources]` block pins many names to the
`pytorch-cpu` index (`explicit=true`, download.pytorch.org/whl/cpu). That index only hosts
torch-family wheels — mapping `sentence-transformers`/`transformers` there makes uv unable to
find recent versions ("only <X available"). Keep ONLY `torch` mapped to pytorch-cpu; let the
rest resolve from PyPI. (2) `requires-python` was `>=3.11` which forced resolution for 3.14+
where sentence-transformers 5.6.0 has no wheel; capped to `>=3.11,<3.13` (runtime is 3.11).
**The cap must be `<3.13`, not `<3.14`:** the deploy build runs `uv sync` which validates the
FULL requires-python range (not just the active 3.11). torch 2.12.1+cpu has no cp313 wheel on the
pytorch-cpu index, so the 3.13 split makes sentence-transformers 5.6.0 unsatisfiable and the
publish build fails with "No solution found ... python_full_version == '3.13.*'". `uv lock` can
succeed locally while the build's `uv sync` still fails on an excluded-but-in-range split — always
re-run `uv sync` (not just `uv lock`) locally to catch this before redeploying.

## Embedding/retrieval note
The image query is PURELY visual (no text prompt; video = average of frame vectors).
Embeddings are computed LOCALLY with TinyCLIP (no OpenRouter/network) — see
embeddings.embed_frames(frames). Mood is NOT computed at request time — it is
precomputed at catalog ingestion and stored in Chroma metadata. The catalog is the
user's REAL ChromaDB (collection `song_lyrics_min`, cosine, 512-dim, ~74k stanzas) at
`services/lyrics-engine/TinyCLAPdb/`. It is swappable; a swap can change row count,
the mood vocabulary, AND the embedding model/dim (which must match the query encoder).

## Real catalog + Musixmatch (important)
Real Chroma ids are `{track_id}_stanza_{j}` (numeric Musixmatch track_id + stanza
index); metadata only has `genre`/`language` — NO lyric/artist/title. So `analyze`
resolves artist/title/lyrics from Musixmatch (`track.get` + `track.lyrics.get`, keyed
by `track_id`) and picks stanza `j` by splitting lyrics on blank lines (`\n\n`).
`musixmatch.py` caches per `track_id` (process-wide) — one `analyze` can need ~50
tracks, so the cache matters for plan limits. Needs `MUSIXMATCH_API_KEY` secret.
**Per-track resilience:** `analyze` gathers fetches with `return_exceptions=True` and
DROPS tracks Musixmatch can't resolve, so one bad track no longer 502s the whole
request; it only 502s if EVERY candidate fails (empty `best`). `fetch_track` itself
still raises on incomplete data — the resilience is at the `analyze` call site.
**Danger:** `seed.py` wipes+rebuilds `song_lyrics_min` — gated behind `ALLOW_SEED_RESET=1`
+ a catalog arg so it can never nuke the real DB. The placeholder `catalog.json` is gone.

## Restart engine after merges

The `Lyrics Engine` is a **standalone Python workflow**, not an artifact, so the
post-merge setup script does **not** restart it. After any merge that touches
`services/lyrics-engine`, manually restart the `Lyrics Engine` workflow — otherwise
it keeps serving the pre-merge code. Symptom of the stale process: `/api/analyze`
returns 200 but with empty lyric/artist/track fields (old code read Chroma
metadata that does not exist in the real DB) and Musixmatch is never called.

## React Compiler breaks expo-video useVideoPlayer

The mobile app has `experiments.reactCompiler: true` (app.json). The React Compiler
mis-compiles components that call expo-video `useVideoPlayer`, throwing a runtime
"Invalid hook call" that the ErrorBoundary swallows — so the video silently never
mounts/plays. Fix: add the `"use no memo";` directive as the first statement inside
any component that calls `useVideoPlayer` (see components/VideoBackground.tsx).

## expo-video does not autoplay on web — use a native <video> there

On web, expo-video `useVideoPlayer` + `player.play()` does NOT reliably start a
muted-autoplay blob: source (browser autoplay policy). The VideoView mounts but
stays paused/black. Fix: in components/VideoBackground.tsx, branch on
`Platform.OS === "web"` and render a raw HTML `<video autoPlay loop muted
playsInline>` via React.createElement("video"), setting `el.muted = true` /
`el.defaultMuted = true` in the ref BEFORE calling `el.play()`. Keep expo-video
only for native (iOS/Android), where it still needs the `"use no memo"` directive
to survive the React Compiler.


## Mood logic: precomputed mood metadata + best/dynamic-mood response

The mood is NOT computed at request time. It is precomputed during catalog
ingestion and stored in each stanza's Chroma metadata (`mood`, plus `genre`,
`language`, `length_bin`). At request time the engine:
- embeds the image(s) PURELY visually with LOCAL TinyCLIP (no text prompt; video =
  average of frame vectors) — see embeddings.embed_frames(frames),
- queries Chroma top CANDIDATE_K (100) with a `where` filter combining `language=en`,
  `explicit=0` (clean only), and `length_bin $in ["25-50".."125-150"]` (25–150 chars),
- returns a dict: `best` = simply the top-K results (NO dedup — per the user, all 100)
  in pure visual-distance order, plus one bucket per mood ACTUALLY retrieved. Mood
  buckets are ordered by their ACTUAL returned lyric count (post-Musixmatch-filter,
  computed AFTER dropping unresolved tracks — not the raw Chroma hit count).

**The mood taxonomy is dynamic and large** (e.g. romantic_love, street_hustle,
euphoria_dance, freedom_adventure, chill_relaxed, ... ~19 values), NOT the old
fixed 5. So the API contract `AnalyzeResponse` is a map (`additionalProperties`),
not fixed keys. The mobile player derives its mood tabs from `Object.keys(results)`
(best first), and constants/moods.ts maps each catalog mood id to an Italian
label/color/icon with a prettified fallback for unmapped ids.

**Why:** the user replaced the catalog with one that embeds mood at ingestion.
Any future catalog swap can change the mood vocabulary again — keep the contract
and UI taxonomy-agnostic (map + fallback), never hardcode the mood set.
