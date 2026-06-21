import numpy as np
import torch
from PIL import Image
from sentence_transformers import SentenceTransformer

from moods import format_document, format_query

MODEL_NAME = "nvidia/llama-nemotron-embed-vl-1b-v2"


def get_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def load_model(device: str | None = None, model_name: str | None = None) -> SentenceTransformer:
    device = device or get_device()
    model_name = model_name or MODEL_NAME
    model = SentenceTransformer(model_name, trust_remote_code=True, device=device)
    if "clip" in model_name.lower():
        model.max_seq_length = 77
    return model


def encode_documents(
    model: SentenceTransformer,
    texts: list[str],
    batch_size: int = 32,
    show_progress_bar: bool = False,
) -> np.ndarray:
    inputs = [format_document(text) for text in texts]
    if hasattr(model, "encode_document"):
        return model.encode_document(
            inputs,
            batch_size=batch_size,
            show_progress_bar=show_progress_bar,
        )
    return model.encode(
        inputs,
        batch_size=batch_size,
        show_progress_bar=show_progress_bar,
    )


def encode_visual_query(
    model: SentenceTransformer,
    images: Image.Image | list[Image.Image],
    user_text: str,
    mood: str | None = None,
) -> np.ndarray:
    query_text = format_query(user_text, mood)
    if isinstance(images, Image.Image):
        images = [images]

    if len(images) == 1:
        return model.encode_query([{"image": images[0], "text": query_text}])[0]

    frame_embeddings = [
        model.encode_query([{"image": image, "text": query_text}])[0]
        for image in images
    ]
    return np.mean(frame_embeddings, axis=0)
