import { ImageManipulator, SaveFormat } from "expo-image-manipulator";
import * as ImagePicker from "expo-image-picker";
import * as VideoThumbnails from "expo-video-thumbnails";
import { Platform } from "react-native";

export type MediaType = "image" | "video";

export interface PickedMedia {
  uri: string;
  type: MediaType;
  /** Preview frame (first sampled frame). */
  dataUrl: string;
  /** All sampled frames as JPEG data URLs (one for images, ~1fps for videos). */
  frames: string[];
}

const MAX_VIDEO_FRAMES = 8;

export class CameraPermissionError extends Error {
  constructor() {
    super("camera-permission-denied");
    this.name = "CameraPermissionError";
  }
}

export class VideoThumbnailError extends Error {
  constructor() {
    super("video-thumbnail-failed");
    this.name = "VideoThumbnailError";
  }
}

async function buildDataUrl(uri: string): Promise<string> {
  const context = ImageManipulator.manipulate(uri);
  context.resize({ height: 720 });
  const ref = await context.renderAsync();
  const result = await ref.saveAsync({
    compress: 0.7,
    format: SaveFormat.JPEG,
    base64: true,
  });
  return `data:image/jpeg;base64,${result.base64 ?? ""}`;
}

function frameCount(totalMs: number): number {
  // ~1fps, capped so long clips don't explode the embedding cost.
  return Math.min(MAX_VIDEO_FRAMES, Math.max(1, Math.floor(totalMs / 1000)));
}

function frameTimeMs(index: number, count: number, totalMs: number): number {
  // Evenly spaced including first (t=0) and last (t≈duration) frame.
  return count === 1 ? 0 : Math.round((index * (totalMs - 1)) / (count - 1));
}

async function buildNativeVideoFrames(
  uri: string,
  totalMs: number,
): Promise<string[]> {
  const count = frameCount(totalMs);
  const frames: string[] = [];
  for (let i = 0; i < count; i++) {
    try {
      const thumb = await VideoThumbnails.getThumbnailAsync(uri, {
        time: frameTimeMs(i, count, totalMs),
      });
      frames.push(await buildDataUrl(thumb.uri));
    } catch {
      // Skip a frame that fails to extract; keep the rest.
    }
  }
  if (frames.length === 0) throw new VideoThumbnailError();
  return frames;
}

// Browsers do not fire a `seeked` event when currentTime is already at the
// target, so resolve immediately in that case. A timeout guards against decoders
// that silently never emit `seeked`/`error` (otherwise the whole pick hangs).
function seekTo(
  video: HTMLVideoElement,
  seconds: number,
  timeoutMs = 4000,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const target = Math.max(0, seconds);
    if (Math.abs(video.currentTime - target) < 0.04) {
      resolve();
      return;
    }
    let timer: ReturnType<typeof setTimeout>;
    const cleanup = (): void => {
      clearTimeout(timer);
      video.removeEventListener("seeked", onSeeked);
      video.removeEventListener("error", onError);
    };
    const onSeeked = (): void => {
      cleanup();
      resolve();
    };
    const onError = (): void => {
      cleanup();
      reject(new VideoThumbnailError());
    };
    timer = setTimeout(onError, timeoutMs);
    video.addEventListener("seeked", onSeeked);
    video.addEventListener("error", onError);
    video.currentTime = target;
  });
}

function waitForVideoReady(
  video: HTMLVideoElement,
  timeoutMs = 8000,
): Promise<void> {
  return new Promise((resolve, reject) => {
    let timer: ReturnType<typeof setTimeout>;
    const cleanup = (): void => {
      clearTimeout(timer);
      video.removeEventListener("loadeddata", onLoaded);
      video.removeEventListener("error", onError);
    };
    const onLoaded = (): void => {
      cleanup();
      resolve();
    };
    const onError = (): void => {
      cleanup();
      reject(new VideoThumbnailError());
    };
    timer = setTimeout(onError, timeoutMs);
    if (video.readyState >= 2) {
      onLoaded();
      return;
    }
    video.addEventListener("loadeddata", onLoaded);
    video.addEventListener("error", onError);
  });
}

async function buildWebVideoFrames(
  uri: string,
  durationHintMs: number | undefined,
): Promise<string[]> {
  const video = document.createElement("video");
  video.src = uri;
  video.muted = true;
  video.playsInline = true;
  video.preload = "auto";
  video.crossOrigin = "anonymous";

  try {
    await waitForVideoReady(video);

    const totalMs =
      Number.isFinite(video.duration) && video.duration > 0
        ? video.duration * 1000
        : durationHintMs && durationHintMs > 0
          ? durationHintMs
          : 1000;
    const count = frameCount(totalMs);

    const srcH = video.videoHeight || 720;
    const srcW = video.videoWidth || 1280;
    const scale = Math.min(1, 720 / srcH);
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(srcW * scale));
    canvas.height = Math.max(1, Math.round(srcH * scale));
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new VideoThumbnailError();

    const frames: string[] = [];
    for (let i = 0; i < count; i++) {
      try {
        await seekTo(video, frameTimeMs(i, count, totalMs) / 1000);
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        frames.push(canvas.toDataURL("image/jpeg", 0.7));
      } catch {
        // Skip a frame that fails to extract; keep the rest.
      }
    }
    if (frames.length === 0) throw new VideoThumbnailError();
    return frames;
  } finally {
    // Release the decoder/memory for repeated picks.
    video.pause();
    video.removeAttribute("src");
    video.load();
  }
}

async function buildVideoFrames(
  uri: string,
  durationMs: number | undefined,
): Promise<string[]> {
  const total = durationMs && durationMs > 0 ? durationMs : 1000;
  if (Platform.OS === "web") {
    return buildWebVideoFrames(uri, durationMs);
  }
  return buildNativeVideoFrames(uri, total);
}

// expo-image-picker does not reliably set `asset.type` to "video" on web, so
// fall back to the MIME type and file extension before defaulting to image.
// Misrouting a video into the image path makes ImageManipulator hang silently.
function detectMediaType(asset: ImagePicker.ImagePickerAsset): MediaType {
  if (asset.type === "video") return "video";
  if (asset.type === "image") return "image";
  const mime = asset.mimeType?.toLowerCase() ?? "";
  if (mime.startsWith("video/")) return "video";
  if (mime.startsWith("image/")) return "image";
  const name = (asset.fileName ?? asset.uri ?? "").toLowerCase();
  if (/\.(mp4|mov|webm|m4v|avi|mkv|3gp|ogv|qt)(\?|#|$)/.test(name)) {
    return "video";
  }
  return "image";
}

async function processAsset(
  asset: ImagePicker.ImagePickerAsset,
): Promise<PickedMedia> {
  const type: MediaType = detectMediaType(asset);
  const frames =
    type === "video"
      ? await buildVideoFrames(asset.uri, asset.duration ?? undefined)
      : [await buildDataUrl(asset.uri)];
  return { uri: asset.uri, type, dataUrl: frames[0], frames };
}

export async function pickFromLibrary(): Promise<PickedMedia | null> {
  const res = await ImagePicker.launchImageLibraryAsync({
    mediaTypes: ["images", "videos"],
    quality: 0.9,
  });
  if (res.canceled || !res.assets?.length) return null;
  return processAsset(res.assets[0]);
}

export async function captureFromCamera(): Promise<PickedMedia | null> {
  const perm = await ImagePicker.requestCameraPermissionsAsync();
  if (!perm.granted) throw new CameraPermissionError();
  const res = await ImagePicker.launchCameraAsync({
    mediaTypes: ["images", "videos"],
    quality: 0.9,
  });
  if (res.canceled || !res.assets?.length) return null;
  return processAsset(res.assets[0]);
}
