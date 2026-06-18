"""OpenRouter multimodal embedding client.

Uses nvidia/llama-nemotron-embed-vl-1b-v2:free which embeds text and images
into the same 2048-dim vector space.
"""

import asyncio
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


async def embed_text_async(
    client: httpx.AsyncClient,
    text: str,
    semaphore: asyncio.Semaphore | None = None,
) -> list[float]:
    """Async text-only embedding (used to embed the 5 mood descriptions)."""
    body = {
        "model": EMBED_MODEL,
        "input": [{"content": [{"type": "text", "text": text}]}],
        "encoding_format": "float",
    }
    if semaphore is not None:
        async with semaphore:
            resp = await client.post(OPENROUTER_URL, headers=_headers(), json=body)
    else:
        resp = await client.post(OPENROUTER_URL, headers=_headers(), json=body)
    resp.raise_for_status()
    return _extract(resp.json())


async def embed_visual_query(
    client: httpx.AsyncClient,
    prompt: str,
    image_data_url: str,
    semaphore: asyncio.Semaphore | None = None,
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
    if semaphore is not None:
        async with semaphore:
            resp = await client.post(OPENROUTER_URL, headers=_headers(), json=body)
    else:
        resp = await client.post(OPENROUTER_URL, headers=_headers(), json=body)
    resp.raise_for_status()
    return _extract(resp.json())


def _average(vectors: list[list[float]]) -> list[float]:
    """Element-wise mean of equal-length embedding vectors."""
    if not vectors:
        raise ValueError("cannot average an empty list of vectors")
    if len(vectors) == 1:
        return vectors[0]
    count = len(vectors)
    dim = len(vectors[0])
    return [sum(vec[i] for vec in vectors) / count for i in range(dim)]


async def embed_visual_frames(
    client: httpx.AsyncClient,
    prompt: str,
    image_data_urls: list[str],
    semaphore: asyncio.Semaphore | None = None,
) -> list[float]:
    """Embed every frame for a mood prompt, then average into one query vector."""
    vectors = await asyncio.gather(
        *[
            embed_visual_query(client, prompt, url, semaphore)
            for url in image_data_urls
        ]
    )
    return _average(list(vectors))
