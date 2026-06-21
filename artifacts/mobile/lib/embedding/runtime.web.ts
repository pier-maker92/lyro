// Web on-device embedding runtime: decode via <canvas>, run via onnxruntime-web.
//
// onnxruntime-web's ESM build does a runtime `import()` of its WASM worker that
// Metro cannot statically bundle, so instead of importing the package we load its
// UMD build from the CDN at runtime (script tag -> global `ort`). This keeps
// onnxruntime-web out of the Metro web bundle entirely.
import { Asset } from "expo-asset";

import modelAsset from "./model";
import { CLIP_SIZE, preprocessToTensor, type Rgba } from "./preprocess";

type Ort = typeof import("onnxruntime-web");

const ORT_VERSION = "1.27.0";
const ORT_CDN = `https://cdn.jsdelivr.net/npm/onnxruntime-web@${ORT_VERSION}/dist/`;

let ortPromise: Promise<Ort> | null = null;
let sessionPromise: Promise<import("onnxruntime-web").InferenceSession> | null =
  null;

function loadOrt(): Promise<Ort> {
  if (!ortPromise) {
    ortPromise = new Promise<Ort>((resolve, reject) => {
      const w = globalThis as unknown as { ort?: Ort };
      if (w.ort) {
        resolve(w.ort);
        return;
      }
      const script = document.createElement("script");
      script.src = `${ORT_CDN}ort.min.js`;
      script.async = true;
      script.onload = () => {
        if (w.ort) {
          w.ort.env.wasm.wasmPaths = ORT_CDN;
          resolve(w.ort);
        } else {
          reject(new Error("onnxruntime-web did not register a global"));
        }
      };
      script.onerror = () =>
        reject(new Error("failed to load onnxruntime-web from CDN"));
      document.head.appendChild(script);
    });
  }
  return ortPromise;
}

function getSession(
  ort: Ort,
): Promise<import("onnxruntime-web").InferenceSession> {
  if (!sessionPromise) {
    sessionPromise = (async () => {
      const asset = Asset.fromModule(modelAsset);
      await asset.downloadAsync();
      const uri = asset.localUri ?? asset.uri;
      const res = await fetch(uri);
      const bytes = new Uint8Array(await res.arrayBuffer());
      return ort.InferenceSession.create(bytes, {
        executionProviders: ["wasm"],
      });
    })();
  }
  return sessionPromise;
}

async function decode(dataUrl: string): Promise<Rgba> {
  const img = new Image();
  img.crossOrigin = "anonymous";
  await new Promise<void>((resolve, reject) => {
    img.onload = () => resolve();
    img.onerror = () => reject(new Error("image decode failed"));
    img.src = dataUrl;
  });
  const canvas = document.createElement("canvas");
  canvas.width = img.naturalWidth;
  canvas.height = img.naturalHeight;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("could not get 2d canvas context");
  ctx.drawImage(img, 0, 0);
  const { data, width, height } = ctx.getImageData(
    0,
    0,
    canvas.width,
    canvas.height,
  );
  return { data, width, height };
}

export async function embedImages(dataUrls: string[]): Promise<Float32Array[]> {
  const ort = await loadOrt();
  const session = await getSession(ort);
  const out: Float32Array[] = [];
  for (const url of dataUrls) {
    const rgba = await decode(url);
    const input = new ort.Tensor("float32", preprocessToTensor(rgba), [
      1,
      3,
      CLIP_SIZE,
      CLIP_SIZE,
    ]);
    const result = await session.run({ pixel_values: input });
    out.push(Float32Array.from(result.image_embeds.data as Float32Array));
  }
  return out;
}
