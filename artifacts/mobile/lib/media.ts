import { ImageManipulator, SaveFormat } from "expo-image-manipulator";
import * as ImagePicker from "expo-image-picker";
import * as VideoThumbnails from "expo-video-thumbnails";

export type MediaType = "image" | "video";

export interface PickedMedia {
  uri: string;
  type: MediaType;
  dataUrl: string;
}

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

async function processAsset(
  asset: ImagePicker.ImagePickerAsset,
): Promise<PickedMedia> {
  const type: MediaType = asset.type === "video" ? "video" : "image";
  let frameUri = asset.uri;
  if (type === "video") {
    try {
      const thumb = await VideoThumbnails.getThumbnailAsync(asset.uri, {
        time: 1000,
      });
      frameUri = thumb.uri;
    } catch {
      throw new VideoThumbnailError();
    }
  }
  const dataUrl = await buildDataUrl(frameUri);
  return { uri: asset.uri, type, dataUrl };
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
