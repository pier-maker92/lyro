"""Visual-to-Lyrics retrieval engine.

FastAPI service that embeds an uploaded image (mood-agnostic) with OpenRouter,
queries a local ChromaDB catalog of song lyrics for the top candidates, then
clusters those candidates into the 5 moods by cosine similarity between each
retrieved lyric embedding and the precomputed embedding of each mood.
"""

import asyncio
import math
import os

import chromadb
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from embeddings import embed_text_async, embed_visual_frames
from moods import DEFAULT_QUERY_PROMPT, MOOD_TEXTS, MOODS
from musixmatch import MusixmatchError, fetch_track

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lyrics_catalog_db")
COLLECTION_NAME = "song_lyrics_min"
# Number of mood-agnostic candidates pulled from Chroma before clustering.
CANDIDATE_K = 25
RESULTS_PER_MOOD = 5
MAX_FRAMES = 8
EMBED_CONCURRENCY = 6

# The 5 mood embeddings are identical across requests, so compute them once.
_mood_embeddings: dict[str, list[float]] | None = None
_mood_lock = asyncio.Lock()

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
    except Exception as exc:  # collection missing
        raise HTTPException(
            status_code=503,
            detail=(
                f"Lyrics catalog collection '{COLLECTION_NAME}' not found at "
                f"{DB_PATH}. Install the real ChromaDB."
            ),
        ) from exc


class AnalyzeRequest(BaseModel):
    frames: list[str]


class LyricMatch(BaseModel):
    lyric: str
    artist: str
    track: str
    distance: float


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


def _parse_embedding_id(embedding_id: str) -> tuple[str, int]:
    """Split a catalog embedding id ``{track_id}_stanza_{j}`` into its parts.

    The user's real ChromaDB encodes the Musixmatch track_id plus the stanza index
    in the id; the metadata only carries ``genre``/``language``. track_id itself is
    numeric, so we split on the last ``_stanza_`` separator.
    """
    marker = "_stanza_"
    idx = embedding_id.rfind(marker)
    if idx == -1:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected embedding id format: {embedding_id!r}",
        )
    track_id = embedding_id[:idx]
    stanza_part = embedding_id[idx + len(marker) :]
    try:
        stanza_index = int(stanza_part)
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected stanza index in id: {embedding_id!r}",
        ) from exc
    return track_id, stanza_index


def _cosine(a, b) -> float:
    """Cosine similarity between two equal-length embedding vectors."""
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        x = float(x)
        y = float(y)
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


async def _get_mood_embeddings(client: httpx.AsyncClient) -> dict[str, list[float]]:
    """Embed the 5 mood descriptions once and cache them for later requests."""
    global _mood_embeddings
    if _mood_embeddings is not None:
        return _mood_embeddings
    async with _mood_lock:
        if _mood_embeddings is not None:
            return _mood_embeddings
        vectors = await asyncio.gather(
            *[embed_text_async(client, MOOD_TEXTS[mood]) for mood in MOODS]
        )
        _mood_embeddings = dict(zip(MOODS, vectors))
    return _mood_embeddings


def _stanza_at(lyrics: str, index: int) -> str:
    """Return the stanza at ``index`` (stanzas are separated by blank lines)."""
    stanzas = [s.strip() for s in lyrics.split("\n\n") if s.strip()]
    if not stanzas:
        raise HTTPException(
            status_code=502, detail="Musixmatch returned lyrics with no stanzas"
        )
    if index < 0 or index >= len(stanzas):
        # The stanza index came from the user's embedding pipeline; if Musixmatch
        # lyrics have fewer stanzas, clamp to the last one rather than dropping the
        # match. (The Musixmatch call itself still fails loudly elsewhere.)
        index = len(stanzas) - 1
    return stanzas[index]


@app.post("/analyze")
async def analyze(req: AnalyzeRequest) -> dict[str, list[LyricMatch]]:
    frames = [f for f in req.frames if isinstance(f, str) and f.startswith("data:")]
    if not frames:
        raise HTTPException(
            status_code=400, detail="frames must contain at least one data URL"
        )
    if len(frames) > MAX_FRAMES:
        # Sample evenly across the clip (including first and last frame) so we
        # keep ~1fps coverage without exploding the number of embedding calls.
        last = len(frames) - 1
        frames = [
            frames[round(i * last / (MAX_FRAMES - 1))] for i in range(MAX_FRAMES)
        ]

    collection = _collection()
    semaphore = asyncio.Semaphore(EMBED_CONCURRENCY)

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            # One mood-agnostic visual query vector + the cached mood embeddings.
            query_vector, mood_vectors = await asyncio.gather(
                embed_visual_frames(client, DEFAULT_QUERY_PROMPT, frames, semaphore),
                _get_mood_embeddings(client),
            )
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Embedding provider error: {exc.response.status_code}",
            ) from exc

        # Pull the top mood-agnostic candidates, keeping their embeddings so we can
        # cluster them by similarity to each mood.
        result = collection.query(
            query_embeddings=[query_vector],
            n_results=CANDIDATE_K,
            include=["distances", "embeddings"],
        )
        ids = (result.get("ids") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        embeddings = (result.get("embeddings") or [[]])[0]

        # Cluster each unique candidate track into the mood it is closest to.
        per_mood_picks: dict[str, list[tuple[str, int, float, float]]] = {
            mood: [] for mood in MOODS
        }
        seen_tracks: set[str] = set()
        for embedding_id, dist, emb in zip(ids, distances, embeddings):
            track_id, stanza_index = _parse_embedding_id(str(embedding_id))
            if track_id in seen_tracks:
                continue
            seen_tracks.add(track_id)
            best_mood = MOODS[0]
            best_sim = -2.0
            for mood in MOODS:
                sim = _cosine(emb, mood_vectors[mood])
                if sim > best_sim:
                    best_sim = sim
                    best_mood = mood
            per_mood_picks[best_mood].append(
                (track_id, stanza_index, float(dist), best_sim)
            )

        # Most on-mood first within each cluster, capped per mood.
        for mood in MOODS:
            per_mood_picks[mood].sort(key=lambda t: t[3], reverse=True)
            per_mood_picks[mood] = per_mood_picks[mood][:RESULTS_PER_MOOD]

        needed = list(
            {
                track_id
                for picks in per_mood_picks.values()
                for track_id, _, _, _ in picks
            }
        )
        try:
            fetched = await asyncio.gather(
                *[fetch_track(client, track_id) for track_id in needed]
            )
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Musixmatch request failed: {exc.response.status_code}",
            ) from exc
        except MusixmatchError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    tracks = dict(zip(needed, fetched))

    response: dict[str, list[LyricMatch]] = {}
    for mood, picks in per_mood_picks.items():
        matches: list[LyricMatch] = []
        for track_id, stanza_index, distance, _sim in picks:
            data = tracks[track_id]
            matches.append(
                LyricMatch(
                    lyric=_stanza_at(data.lyrics, stanza_index),
                    artist=data.artist,
                    track=data.track,
                    distance=distance,
                )
            )
        response[mood] = matches
    return response
