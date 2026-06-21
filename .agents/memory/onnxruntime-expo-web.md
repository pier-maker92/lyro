---
name: onnxruntime on Expo (web + native) and CLIP preprocessing parity
description: How to run TinyCLIP ONNX on-device in the Visual Lyrics Expo app without breaking the Metro web bundle, and how JS preprocessing reaches golden parity.
---

# onnxruntime-web cannot be Metro-bundled for Expo web

`import * as ort from "onnxruntime-web"` resolves to `ort.bundle.min.mjs`, which does a
runtime `import(/*webpackIgnore*/ t)` to spawn its WASM worker. Metro/Babel rejects this
("Invalid call ... import(...)") and the web bundle returns a 500 (serves error JSON, blank
preview).

**Fix:** do NOT import onnxruntime-web in app code on web. Load its UMD build from the CDN at
runtime via an injected `<script src=".../ort.min.js">` and use the global `ort`. Set
`ort.env.wasm.wasmPaths` to the same CDN dir. Keep this in a `*.web.ts` file so Metro never
pulls the package into the web graph.

**Why:** Metro can statically bundle dynamic `import()` only when the argument is analyzable;
onnxruntime-web's worker URL is fully dynamic.

**How to apply:** platform-split the runtime — `runtime.web.ts` (CDN script + `<canvas>` decode),
`runtime.native.ts` (`onnxruntime-react-native` + `jpeg-js` decode), a stub `runtime.ts` so TS
can resolve `./runtime`. Native onnxruntime is a native module — web bundle never sees it because
`runtime.native.ts` is only in native bundles. Native needs an EAS build (not Expo Go / not the
Replit web preview), so validate via golden parity only.

# CLIP preprocessing parity in pure JS

Reproducing HF CLIPImageProcessor (resize shortest-edge 224 + center-crop + rescale + per-channel
mean/std, RGB, NOT L2-normalized) in pure JS with an **area-weighted (box) average downscale**
matches the Python sentence-transformers golden vectors at cosine >= 0.998 across the fixtures —
well above the 0.98 bar. Area averaging (not naive bilinear/bicubic) is what makes downscales
antialias close enough to PIL.

**How to apply:** keep one shared `preprocess.ts` used by both platforms AND the Node parity test
(`scripts/parity-test.mjs`, runs onnxruntime-web in Node + pngjs to decode fixtures). Re-run the
parity test whenever preprocessing or the exported ONNX changes.
