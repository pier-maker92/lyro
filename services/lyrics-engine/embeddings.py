"""OpenRouter multimodal embedding client.

Uses nvidia/llama-nemotron-embed-vl-1b-v2:free which embeds text and images
into the same 2048-dim vector space.
"""

import os

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/embeddings"
EMBED_MODEL = "nvidia/llama-nemotron-embed-vl-1b-v2:free"


def _api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    return key


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
    }


def _extract(payload: dict) -> list[float]:
    data = payload.get("data")
    if not data:
        raise RuntimeError(f"OpenRouter embedding error: {payload}")
    return data[0]["embedding"]


def embed_text(text: str) -> list[float]:
    """Synchronous text embedding (used by the seed script)."""
    body = {
        "model": EMBED_MODEL,
        "input": [{"content": [{"type": "text", "text": text}]}],
        "encoding_format": "float",
    }
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(OPENROUTER_URL, headers=_headers(), json=body)
        resp.raise_for_status()
        return _extract(resp.json())


async def embed_visual_query(
    client: httpx.AsyncClient, prompt: str, image_data_url: str
) -> list[float]:
    """Embed a mood prompt + image together into one mood-conditioned query vector."""
    body = {
        "model": EMBED_MODEL,
        "input": [
            {
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                ]
            }
        ],
        "encoding_format": "float",
    }
    resp = await client.post(OPENROUTER_URL, headers=_headers(), json=body)
    resp.raise_for_status()
    return _extract(resp.json())
