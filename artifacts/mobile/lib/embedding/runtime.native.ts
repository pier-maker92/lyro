// Native on-device embedding runtime: decode JPEG via jpeg-js, run via
// onnxruntime-react-native. Requires a native (EAS) build; not available in Expo Go.
import { Asset } from "expo-asset";
import * as jpeg from "jpeg-js";
import * as ort from "onnxruntime-react-native";

import modelAsset from "./model";
import { CLIP_SIZE, preprocessToTensor, type Rgba } from "./preprocess";

let sessionPromise: Promise<ort.InferenceSession> | null = null;

function getSession(): Promise<ort.InferenceSession> {
  if (!sessionPromise) {
    sessionPromise = (async () => {
      const asset = Asset.fromModule(modelAsset);
      await asset.downloadAsync();
      const uri = asset.localUri ?? asset.uri;
      return ort.InferenceSession.create(uri.replace(/^file:\/\//, ""));
    })();
  }
  return sessionPromise;
}

const B64 =
  "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

function base64ToBytes(b64: string): Uint8Array {
  const clean = b64.replace(/[^A-Za-z0-9+/]/g, "");
  const len = clean.length;
  const pad = clean.endsWith("==") ? 2 : clean.endsWith("=") ? 1 : 0;
  const outLen = Math.floor((len * 3) / 4) - pad;
  const out = new Uint8Array(outLen);
  let o = 0;
  for (let i = 0; i < len; i += 4) {
    const c0 = B64.indexOf(clean[i]);
    const c1 = B64.indexOf(clean[i + 1]);
    const c2 = B64.indexOf(clean[i + 2]);
    const c3 = B64.indexOf(clean[i + 3]);
    const n = (c0 << 18) | (c1 << 12) | ((c2 & 63) << 6) | (c3 & 63);
    if (o < outLen) out[o++] = (n >> 16) & 0xff;
    if (o < outLen) out[o++] = (n >> 8) & 0xff;
    if (o < outLen) out[o++] = n & 0xff;
  }
  return out;
}

function decode(dataUrl: string): Rgba {
  const comma = dataUrl.indexOf(",");
  const b64 = comma >= 0 ? dataUrl.slice(comma + 1) : dataUrl;
  const bytes = base64ToBytes(b64);
  const { width, height, data } = jpeg.decode(bytes, {
    useTArray: true,
    formatAsRGBA: true,
  });
  return { data, width, height };
}

export async function embedImages(dataUrls: string[]): Promise<Float32Array[]> {
  const session = await getSession();
  const out: Float32Array[] = [];
  for (const url of dataUrls) {
    const rgba = decode(url);
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
