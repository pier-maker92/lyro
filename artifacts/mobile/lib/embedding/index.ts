// On-device TinyCLIP image embedding. The client computes the 512-dim query
// vector and sends only that to the server (which does Chroma search only).
import { averageVectors } from "./preprocess";
import { embedImages } from "./runtime";

export const EMBEDDING_DIM = 512;

/**
 * Embed one or more frames (JPEG/PNG data URLs) into a single 512-dim query
 * vector. For multiple frames (video) the per-frame vectors are averaged.
 */
export async function embedFrames(frames: string[]): Promise<number[]> {
  if (!frames || frames.length === 0) {
    throw new Error("no frames to embed");
  }
  const vectors = await embedImages(frames);
  if (vectors.length === 0) {
    throw new Error("embedding produced no vectors");
  }
  const result =
    vectors.length === 1 ? Array.from(vectors[0]) : averageVectors(vectors);
  if (result.length !== EMBEDDING_DIM) {
    throw new Error(
      `unexpected embedding dim ${result.length}, expected ${EMBEDDING_DIM}`,
    );
  }
  return result;
}
