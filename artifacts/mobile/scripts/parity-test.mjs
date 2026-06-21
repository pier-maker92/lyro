// Parity test: on-device JS preprocessing + ONNX image tower vs the Python golden
// vectors (sentence-transformers). Runs the SAME preprocess.ts the app uses, with
// onnxruntime-web in Node. Acceptance: cosine >= 0.98 for every fixture.
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const mobileRoot = path.resolve(__dirname, "..");
const require = createRequire(path.join(mobileRoot, "package.json"));

const ort = require("onnxruntime-web");
const { PNG } = require("pngjs");

ort.env.wasm.wasmPaths = path.join(
  mobileRoot,
  "node_modules/onnxruntime-web/dist/",
);
ort.env.wasm.numThreads = 1;

const { preprocessToTensor, CLIP_SIZE } = await import(
  path.join("file://", "/tmp/preprocess.mjs")
);

const fixturesDir = path.resolve(
  mobileRoot,
  "../../services/lyrics-engine/fixtures",
);
const golden = JSON.parse(
  readFileSync(path.join(fixturesDir, "golden.json"), "utf8"),
);

const modelBytes = new Uint8Array(
  readFileSync(path.join(mobileRoot, "assets/models/tinyclip_image.onnx")),
);
const session = await ort.InferenceSession.create(modelBytes, {
  executionProviders: ["wasm"],
});

function cosine(a, b) {
  let dot = 0;
  let na = 0;
  let nb = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    na += a[i] * a[i];
    nb += b[i] * b[i];
  }
  return dot / (Math.sqrt(na) * Math.sqrt(nb));
}

let min = 1;
let worst = "";
for (const item of golden) {
  const file = `${item.name}.png`;
  const png = PNG.sync.read(
    readFileSync(path.join(fixturesDir, file)),
  );
  const tensorData = preprocessToTensor({
    data: png.data,
    width: png.width,
    height: png.height,
  });
  const input = new ort.Tensor("float32", tensorData, [
    1,
    3,
    CLIP_SIZE,
    CLIP_SIZE,
  ]);
  const result = await session.run({ pixel_values: input });
  const vec = result.image_embeds.data;
  const c = cosine(vec, item.embedding);
  if (c < min) {
    min = c;
    worst = file;
  }
  console.log(`${file.padEnd(20)} cosine=${c.toFixed(4)}`);
}
console.log(`\nMIN cosine=${min.toFixed(4)} (${worst})`);
console.log(min >= 0.98 ? "PASS (>= 0.98)" : "FAIL (< 0.98)");
process.exit(min >= 0.98 ? 0 : 1);
