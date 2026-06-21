const { getDefaultConfig } = require("expo/metro-config");

const config = getDefaultConfig(__dirname);

// Bundle the TinyCLIP ONNX image tower (and the .ort/.wasm runtime files) as
// binary assets so the model can be loaded on-device / in the web preview.
config.resolver.assetExts.push("onnx", "ort");

module.exports = config;
