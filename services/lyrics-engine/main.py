"""Visual-to-Lyrics retrieval engine.

FastAPI service that embeds an uploaded image (conditioned on each mood prompt)
with OpenRouter, queries a local ChromaDB catalog of song lyrics, and returns the
top unique matches per mood.
"""

import asyncio
import os

import chromadb
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from embeddings import embed_visual_query
from moods import MOODS, get_query_prompt

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lyrics_catalog_db")
COLLECTION_NAME = "song_lyrics_min"
TOP_K = 15
RESULTS_PER_MOOD = 5

app = FastAPI(title="Lyrics Engine")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_client = chromadb.PersistentClient(path=DB_PATH)


def _collection():
    try:
        return _client.get_collection(COLLECTION_NAME)
    except Exception as exc:  # collection not seeded yet
        raise HTTPException(
            status_code=503,
            detail="Lyrics catalog is not seeded. Run seed.py first.",
        ) from exc


class AnalyzeRequest(BaseModel):
    imageDataUrl: str


class LyricMatch(BaseModel):
    lyric: str
    artist: str
    track: str
    distance: float


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


def _dedupe(query_result) -> list[LyricMatch]:
    metadatas = (query_result.get("metadatas") or [[]])[0]
    distances = (query_result.get("distances") or [[]])[0]
    seen: set[str] = set()
    matches: list[LyricMatch] = []
    for meta, dist in zip(metadatas, distances):
        track_id = str(meta.get("track_id", ""))
        if track_id in seen:
            continue
        seen.add(track_id)
        matches.append(
            LyricMatch(
                lyric=str(meta.get("stanza", "")),
                artist=str(meta.get("artist_name", "")),
                track=str(meta.get("track_name", "")),
                distance=float(dist),
            )
        )
        if len(matches) >= RESULTS_PER_MOOD:
            break
    return matches


@app.post("/analyze")
async def analyze(req: AnalyzeRequest) -> dict[str, list[LyricMatch]]:
    image = req.imageDataUrl
    if not image or not image.startswith("data:"):
        raise HTTPException(status_code=400, detail="imageDataUrl must be a data URL")

    collection = _collection()

    async with httpx.AsyncClient(timeout=90.0) as client:
        try:
            vectors = await asyncio.gather(
                *[
                    embed_visual_query(client, get_query_prompt(mood), image)
                    for mood in MOODS
                ]
            )
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Embedding provider error: {exc.response.status_code}",
            ) from exc

    response: dict[str, list[LyricMatch]] = {}
    for mood, vector in zip(MOODS, vectors):
        result = collection.query(
            query_embeddings=[vector],
            n_results=TOP_K,
            include=["metadatas", "distances"],
        )
        response[mood] = _dedupe(result)
    return response
