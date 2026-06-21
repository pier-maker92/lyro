// The TinyCLIP image tower exported to ONNX (single self-contained file, ~33MB).
// Metro bundles it as a binary asset (see metro.config.js assetExts).
// eslint-disable-next-line @typescript-eslint/no-require-imports
const tinyClipImageModel = require("../../assets/models/tinyclip_image.onnx");

export default tinyClipImageModel;
