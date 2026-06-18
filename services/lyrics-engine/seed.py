"""Seed the local ChromaDB catalog from catalog.json.

Embeds each lyric stanza with OpenRouter (same model used for queries) and stores
it in the `song_lyrics_min` collection so visual queries can retrieve them.
"""

import json
import os

import chromadb

from embeddings import embed_text

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "lyrics_catalog_db")
CATALOG_PATH = os.path.join(BASE_DIR, "catalog.json")
COLLECTION_NAME = "song_lyrics_min"


def main() -> None:
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    client = chromadb.PersistentClient(path=DB_PATH)
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = client.create_collection(
        COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
    )

    ids: list[str] = []
    embeddings: list[list[float]] = []
    documents: list[str] = []
    metadatas: list[dict] = []

    for i, song in enumerate(catalog):
        stanza = song["stanza"]
        print(f"[{i + 1}/{len(catalog)}] embedding {song['track_id']} ...")
        vector = embed_text(stanza)
        ids.append(f"{song['track_id']}_0")
        embeddings.append(vector)
        documents.append(stanza)
        metadatas.append(
            {
                "track_id": song["track_id"],
                "track_name": song["track_name"],
                "artist_name": song["artist_name"],
                "mood": song.get("mood", ""),
                "stanza": stanza,
            }
        )

    collection.add(
        ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas
    )
    print(f"Seeded {collection.count()} stanzas into '{COLLECTION_NAME}'.")


if __name__ == "__main__":
    main()
