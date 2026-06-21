/**
 * CLIP image preprocessing, shared by the web and native runtimes.
 *
 * Must reproduce the catalog encoder's preprocessing (TinyCLIP via
 * sentence-transformers / HF CLIPImageProcessor) closely enough that the
 * on-device embedding matches the golden vectors (cosine >= 0.98):
 *   1. resize so the SHORTEST edge is 224 (area-averaged, antialiased downscale),
 *   2. center-crop 224x224,
 *   3. rescale 1/255,
 *   4. normalize per channel with the CLIP mean/std,
 *   5. layout as CHW float32 (1,3,224,224), RGB.
 *
 * No L2 normalization is applied — the catalog vectors are NOT normalized.
 */

export const CLIP_SIZE = 224;
const MEAN = [0.48145466, 0.4578275, 0.40821073] as const;
const STD = [0.26862954, 0.26130258, 0.27577711] as const;

export interface Rgba {
  /** RGBA bytes, length = width * height * 4. */
  data: Uint8Array | Uint8ClampedArray;
  width: number;
  height: number;
}

/**
 * Resize (shortest edge -> 224) + center-crop -> 224x224 in one pass, using an
 * area-weighted average of the covered source pixels. Area averaging approximates
 * the antialiased bicubic downscale CLIP uses well enough for parity on downscales
 * (every realistic photo is larger than 224). Returns a 224*224*3 float RGB buffer
 * already rescaled to [0,1].
 */
function resizeCenterCrop(img: Rgba): Float32Array {
  const { data, width: w, height: h } = img;
  const scale = CLIP_SIZE / Math.min(w, h);
  const newW = Math.round(w * scale);
  const newH = Math.round(h * scale);
  const left = Math.floor((newW - CLIP_SIZE) / 2);
  const top = Math.floor((newH - CLIP_SIZE) / 2);

  const out = new Float32Array(CLIP_SIZE * CLIP_SIZE * 3);

  for (let fy = 0; fy < CLIP_SIZE; fy++) {
    // Resized-space row range for this output row, mapped back to source space.
    const ry = fy + top;
    const sy0 = (ry * h) / newH;
    const sy1 = ((ry + 1) * h) / newH;
    const iy0 = Math.floor(sy0);
    const iy1 = Math.min(h, Math.ceil(sy1));

    for (let fx = 0; fx < CLIP_SIZE; fx++) {
      const rx = fx + left;
      const sx0 = (rx * w) / newW;
      const sx1 = ((rx + 1) * w) / newW;
      const ix0 = Math.floor(sx0);
      const ix1 = Math.min(w, Math.ceil(sx1));

      let r = 0;
      let g = 0;
      let b = 0;
      let wsum = 0;
      for (let yy = iy0; yy < iy1; yy++) {
        const wy = Math.min(yy + 1, sy1) - Math.max(yy, sy0);
        if (wy <= 0) continue;
        const rowBase = yy * w * 4;
        for (let xx = ix0; xx < ix1; xx++) {
          const wx = Math.min(xx + 1, sx1) - Math.max(xx, sx0);
          if (wx <= 0) continue;
          const weight = wx * wy;
          const p = rowBase + xx * 4;
          r += data[p] * weight;
          g += data[p + 1] * weight;
          b += data[p + 2] * weight;
          wsum += weight;
        }
      }
      const o = (fy * CLIP_SIZE + fx) * 3;
      if (wsum > 0) {
        out[o] = r / wsum / 255;
        out[o + 1] = g / wsum / 255;
        out[o + 2] = b / wsum / 255;
      }
    }
  }
  return out;
}

/**
 * Full preprocessing: RGBA image -> normalized CHW float32 tensor data for the
 * ONNX image tower (shape [1,3,224,224]).
 */
export function preprocessToTensor(img: Rgba): Float32Array {
  const rgb = resizeCenterCrop(img); // HWC, [0,1]
  const plane = CLIP_SIZE * CLIP_SIZE;
  const chw = new Float32Array(3 * plane);
  for (let i = 0; i < plane; i++) {
    const base = i * 3;
    chw[i] = (rgb[base] - MEAN[0]) / STD[0];
    chw[plane + i] = (rgb[base + 1] - MEAN[1]) / STD[1];
    chw[2 * plane + i] = (rgb[base + 2] - MEAN[2]) / STD[2];
  }
  return chw;
}

/** Average several per-frame embedding vectors into one query vector. */
export function averageVectors(vectors: Float32Array[]): number[] {
  if (vectors.length === 0) throw new Error("no vectors to average");
  const dim = vectors[0].length;
  const acc = new Float64Array(dim);
  for (const v of vectors) {
    for (let i = 0; i < dim; i++) acc[i] += v[i];
  }
  const out = new Array<number>(dim);
  for (let i = 0; i < dim; i++) out[i] = acc[i] / vectors.length;
  return out;
}
