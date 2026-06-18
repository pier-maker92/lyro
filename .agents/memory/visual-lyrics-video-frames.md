---
name: Visual Lyrics video frame averaging
description: How video is turned into a query in the analyze pipeline, and the contract that ties the 3 layers together.
---

# Video frame averaging in /api/analyze

For video, the **client** (Expo `lib/media.ts`) samples frames at ~1fps using
`expo-video-thumbnails`, capped at a small max, evenly spaced **including first
(t=0) and last (t≈duration)** frame. Images produce a single frame. The client
sends `{ frames: string[] }` (JPEG data URLs).

The **engine** (`services/lyrics-engine`) embeds *every* frame conditioned on
*each* mood prompt, then averages the per-frame vectors element-wise into one
query vector per mood. A shared `asyncio.Semaphore` bounds OpenRouter
concurrency because the call count is `moods × frames` (5 × N) — without it the
free embed model rate-limits. The engine also re-caps frames (even sampling
including endpoints) as a server-side safety net.

**Contract rule:** the request shape lives in `lib/api-spec/openapi.yaml`
(`AnalyzeRequest.frames`, required, minItems 1). All three layers — mobile
client, `api-server` proxy, python engine — must agree on `frames`. After
editing the spec, run `pnpm --filter @workspace/api-spec run codegen` or the
generated client/zod drift from the server.

**Why:** the embed model is multimodal and embeds prompt+image *jointly*, so
there is no pure-image embedding to reuse across moods — averaging must happen
per mood. There is intentionally **no `imageDataUrl` backward-compat fallback**;
the canonical field is `frames` and keeping a second path made the OpenAPI
contract inconsistent with the code.

## Web platform frame extraction

`expo-video-thumbnails` is **native-only** — it silently does nothing on web. On
web (`Platform.OS === "web"`) frames are extracted with an offscreen HTML
`<video>` + `<canvas>`: load metadata, seek to evenly spaced timestamps, and
`canvas.toDataURL("image/jpeg", 0.7)` at height 720. The element is never
appended to the DOM.

**Detection trap:** on web `expo-image-picker` frequently does **not** set
`asset.type` to `"video"`. Relying on `asset.type` alone misroutes a picked
video into the image path, where `ImageManipulator` hangs forever on a video
blob — the UI just sits on the home screen with no error (RN-Web `Alert.alert`
is effectively a no-op, so failures are invisible). Detect video via
`asset.type` **OR** `asset.mimeType` (`video/*`) **OR** filename/uri extension.

**Why:** "metto i video ma non funziona" was this exact silent hang on the web
preview. The backend was always fine.

**Testing caveat:** the Playwright e2e harness cannot reliably resolve
`expo-image-picker`'s web file dialog (its dynamically-created `<input>` change
event often never fires, so `launchImageLibraryAsync` hangs). Verify the backend
path directly instead (ffmpeg-extract frames → base64 → POST /api/analyze).
