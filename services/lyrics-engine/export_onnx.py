"""Dev-only: export the TinyCLIP image tower to ONNX and build golden fixtures.

Run ONCE while the heavy ML stack (sentence-transformers/torch/transformers/pillow)
is still installed. Produces:
  - artifacts/mobile/assets/models/tinyclip_image.onnx  (image tower: pixel_values -> 512-dim)
  - services/lyrics-engine/fixtures/<name>.png          (sample images)
  - services/lyrics-engine/fixtures/golden.json         ({name, embedding[512]} per image)

The golden vectors are the reference for BOTH the server smoke test (POST a vector)
and the client parity test (on-device vector vs golden, cosine >= 0.98).

NOT a runtime dependency. After this runs and parity is confirmed, the ML stack is
removed from the server (see pyproject.toml / task 10).
"""

import json
import os

import numpy as np
import torch
from PIL import Image, ImageDraw
from sentence_transformers import SentenceTransformer

MODEL_NAME = "wkcn/TinyCLIP-ViT-8M-16-Text-3M-YFCC15M"
HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures")
ONNX_OUT = os.path.join(
    HERE, "..", "..", "artifacts", "mobile", "assets", "models", "tinyclip_image.onnx"
)


def make_images() -> dict[str, Image.Image]:
    """A diverse set of deterministic synthetic images (varied sizes/content).

    PNG (lossless) so the browser/native decoder sees identical pixels to PIL;
    the only parity difference left is the bicubic resize implementation.
    """
    rng = np.random.default_rng(1234)
    images: dict[str, Image.Image] = {}

    # Solid-ish color blocks with shapes
    palette = [
        (220, 40, 40),
        (40, 160, 220),
        (60, 200, 90),
        (240, 200, 40),
        (160, 60, 200),
    ]
    for i, color in enumerate(palette):
        w, h = (400, 300) if i % 2 == 0 else (320, 480)
        img = Image.new("RGB", (w, h), color)
        d = ImageDraw.Draw(img)
        d.ellipse([w * 0.2, h * 0.2, w * 0.8, h * 0.8], fill=(255, 255, 255))
        d.rectangle([w * 0.35, h * 0.35, w * 0.65, h * 0.65], fill=color)
        images[f"shape_{i}"] = img

    # Gradients
    for i in range(4):
        w, h = 360, 360
        arr = np.zeros((h, w, 3), dtype=np.uint8)
        gx = np.linspace(0, 255, w, dtype=np.uint8)
        gy = np.linspace(0, 255, h, dtype=np.uint8)
        arr[:, :, i % 3] = gx[None, :]
        arr[:, :, (i + 1) % 3] = gy[:, None]
        images[f"gradient_{i}"] = Image.fromarray(arr)

    # Structured noise (varied sizes, including non-square)
    for i, (w, h) in enumerate([(500, 280), (256, 256), (300, 533), (640, 360)]):
        base = rng.integers(0, 255, size=(h // 8, w // 8, 3), dtype=np.uint8)
        big = np.repeat(np.repeat(base, 8, axis=0), 8, axis=1)[:h, :w]
        images[f"noise_{i}"] = Image.fromarray(big)

    # Two near-flat tones (edge cases)
    images["dark"] = Image.new("RGB", (300, 300), (10, 10, 14))
    images["light"] = Image.new("RGB", (300, 300), (245, 245, 240))
    return images


class ImageTower(torch.nn.Module):
    """pixel_values (N,3,224,224) -> image features (N,512), unnormalized."""

    def __init__(self, clip_model: torch.nn.Module) -> None:
        super().__init__()
        self.clip = clip_model

    def forward(self, pixel_values: torch.Tensor) -> torch.Tensor:
        out = self.clip.get_image_features(pixel_values=pixel_values)
        return out.pooler_output


def main() -> None:
    os.makedirs(FIXTURES, exist_ok=True)
    os.makedirs(os.path.dirname(ONNX_OUT), exist_ok=True)

    st = SentenceTransformer(MODEL_NAME)
    clip = st._modules["0"]
    hf_model = clip.model
    image_processor = clip.processor.image_processor

    images = make_images()

    # Golden vectors via sentence-transformers encode (the catalog encoder).
    golden = []
    for name, img in images.items():
        path = os.path.join(FIXTURES, f"{name}.png")
        img.save(path)
        vec = np.asarray(st.encode(img), dtype=np.float32)
        golden.append({"name": name, "embedding": vec.tolist()})
    with open(os.path.join(FIXTURES, "golden.json"), "w") as f:
        json.dump(golden, f)
    print(f"Wrote {len(golden)} golden fixtures to {FIXTURES}")

    # Export the image tower to ONNX.
    tower = ImageTower(hf_model).eval()
    sample = image_processor(images=[next(iter(images.values()))], return_tensors="pt")[
        "pixel_values"
    ]
    with torch.no_grad():
        torch.onnx.export(
            tower,
            (sample,),
            ONNX_OUT,
            input_names=["pixel_values"],
            output_names=["image_embeds"],
            dynamic_axes={
                "pixel_values": {0: "batch"},
                "image_embeds": {0: "batch"},
            },
            opset_version=17,
            do_constant_folding=True,
        )
    # Consolidate external weights into a single self-contained .onnx file so the
    # mobile app bundles ONE asset (onnxruntime-web / -react-native load it directly).
    import onnx

    consolidated = onnx.load(ONNX_OUT, load_external_data=True)
    onnx.save_model(consolidated, ONNX_OUT, save_as_external_data=False)
    data_sidecar = ONNX_OUT + ".data"
    if os.path.exists(data_sidecar):
        os.remove(data_sidecar)
    print(f"Exported ONNX image tower to {os.path.abspath(ONNX_OUT)}")

    # Verify ONNX parity vs golden (Python).
    import onnxruntime as ort

    sess = ort.InferenceSession(ONNX_OUT, providers=["CPUExecutionProvider"])
    worst = 1.0
    for entry in golden:
        name = entry["name"]
        gold = np.asarray(entry["embedding"], dtype=np.float32)
        pv = image_processor(images=[images[name]], return_tensors="pt")[
            "pixel_values"
        ].numpy()
        out = sess.run(["image_embeds"], {"pixel_values": pv})[0][0]
        cos = float(
            np.dot(gold, out) / (np.linalg.norm(gold) * np.linalg.norm(out) + 1e-9)
        )
        worst = min(worst, cos)
        print(f"  {name:12s} cos={cos:.6f} norm={np.linalg.norm(out):.3f}")
    print(f"Worst ONNX-vs-golden cosine: {worst:.6f}")
    assert worst > 0.999, "ONNX export does not match sentence-transformers"
    print("ONNX parity OK")


if __name__ == "__main__":
    main()
