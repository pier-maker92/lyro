"""Visual-to-Lyrics retrieval engine.

FastAPI service that embeds an uploaded image (mood-agnostic, purely visual) with
a local TinyCLIP model, then queries a local ChromaDB catalog of song lyrics for
the top candidates. The mood is precomputed and stored in each stanza's metadata,
so the response exposes a ``best`` ordering (pure visual distance) plus a dynamic
bucket per mood that was actually retrieved.
"""

import asyncio
import os
from contextlib import asynccontextmanager

import chromadb
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from embeddings import embed_frames, get_model
from musixmatch import TrackData, fetch_track

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "TinyCLAPdb")
COLLECTION_NAME = "song_lyrics_min"
# Number of candidates pulled from Chroma
CANDIDATE_K = 100
MAX_FRAMES = 8

# Catalog filters: English, clean (non-explicit) lyrics, 25–150 characters.
LENGTH_BINS = ["25-50", "50-75", "75-100", "100-125", "125-150"]
WHERE_FILTER = {
    "$and": [
        {"language": "en"},
        {"length_bin": {"$in": LENGTH_BINS}},
        {"explicit": 0},
    ]
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm the TinyCLIP model so the first request isn't slow.
    await asyncio.to_thread(get_model)
    yield


app = FastAPI(title="Lyrics Engine", lifespan=lifespan)
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
    in the id; the metadata carries ``genre``/``language``/``length_bin``/``mood``.
    track_id itself is numeric, so we split on the last ``_stanza_`` separator.
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

    # One purely-visual query vector, embedded locally with TinyCLIP. The CPU
    # work runs off the event loop so concurrent requests aren't blocked.
    try:
        query_vector = await asyncio.to_thread(embed_frames, frames)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"Could not decode frames: {exc}"
        ) from exc

    # Pull the top candidates: English, clean, 25–150 char lyrics.
    result = collection.query(
        query_embeddings=[query_vector],
        n_results=CANDIDATE_K,
        where=WHERE_FILTER,
        include=["distances", "metadatas"],
    )

    ids = (result.get("ids") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]

    # Candidates come back in ascending visual-distance order, so the first time
    # we see a track_id is its closest stanza. Dedup to ONE stanza per track —
    # the response must never show two stanzas from the same track. "best" is then
    # the unique tracks in distance order; moods are buckets over the same picks.
    best_picks: list[tuple[str, int, float, str]] = []
    per_mood_picks: dict[str, list[tuple[str, int, float, str]]] = {}
    seen_tracks: set[str] = set()

    for embedding_id, dist, meta in zip(ids, distances, metadatas):
        track_id, stanza_index = _parse_embedding_id(str(embedding_id))
        if track_id in seen_tracks:
            continue
        seen_tracks.add(track_id)

        mood = str(meta.get("mood") or "Unknown") if meta else "Unknown"

        pick = (track_id, stanza_index, float(dist), mood)
        best_picks.append(pick)
        per_mood_picks.setdefault(mood, []).append(pick)

    needed = list(seen_tracks)

    # Resolve lyrics/artist/title from Musixmatch. A single unavailable track
    # must not sink the whole response, so failures are dropped per-track.
    async with httpx.AsyncClient(timeout=120.0) as client:
        fetched = await asyncio.gather(
            *[fetch_track(client, track_id) for track_id in needed],
            return_exceptions=True,
        )

    tracks: dict[str, TrackData] = {
        track_id: data
        for track_id, data in zip(needed, fetched)
        if isinstance(data, TrackData)
    }

    def _to_matches(picks) -> list[LyricMatch]:
        matches: list[LyricMatch] = []
        for track_id, stanza_index, distance, _ in picks:
            data = tracks.get(track_id)
            if data is None:
                continue
            matches.append(
                LyricMatch(
                    lyric=_stanza_at(data.lyrics, stanza_index),
                    artist=data.artist,
                    track=data.track,
                    distance=distance,
                )
            )
        return matches

    best_matches = _to_matches(best_picks)
    if not best_matches:
        raise HTTPException(
            status_code=502,
            detail="Musixmatch returned no usable lyrics for any candidate",
        )

    # Build mood buckets first, then order by their ACTUAL returned lyric counts
    # (after dropping tracks Musixmatch could not resolve), not the raw Chroma hits.
    mood_buckets = [
        (mood, matches)
        for mood, picks in per_mood_picks.items()
        if (matches := _to_matches(picks))
    ]
    mood_buckets.sort(key=lambda kv: len(kv[1]), reverse=True)

    # "best" leads; mood buckets follow ordered by how many lyrics each holds.
    response: dict[str, list[LyricMatch]] = {"best": best_matches}
    for mood, matches in mood_buckets:
        response[mood] = matches

    return response
