// Default (typecheck) runtime. At bundle time Metro resolves the platform-specific
// implementation instead: runtime.web.ts on web, runtime.native.ts on iOS/Android.
// This stub only exists so TypeScript can resolve `./runtime` and is never executed.

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export async function embedImages(_dataUrls: string[]): Promise<Float32Array[]> {
  throw new Error("embedImages: no platform runtime loaded");
}
