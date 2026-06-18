import argparse
import json
import chromadb
from tqdm import tqdm

from embedding import encode_documents, get_device, load_model


def read_concatenated_json(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    decoder = json.JSONDecoder()
    pos = 0
    while pos < len(content):
        # Skip whitespace
        while pos < len(content) and content[pos].isspace():
            pos += 1
        if pos >= len(content):
            break
        obj, end_pos = decoder.raw_decode(content, pos)
        yield obj
        pos = end_pos


def main():
    parser = argparse.ArgumentParser(description="Embed lyrics into ChromaDB.")
    parser.add_argument(
        "--batch_size", type=int, default=32, help="Batch size for embedding processing"
    )
    parser.add_argument(
        "--input_file",
        type=str,
        default="/Users/software/lyra/lyrics_dataset.jsonl",
        help="Path to the JSON/JSONL dataset file",
    )
    args = parser.parse_args()

    device = get_device()
    print(f"Loading SentenceTransformer model on {device}...")
    model = load_model(device)

    print("Initializing ChromaDB...")
    client = chromadb.PersistentClient(path="./lyrics_catalog_db")
    collection = client.get_or_create_collection(
        name="song_lyrics_min", metadata={"hnsw:space": "cosine"}
    )

    print(f"Collecting all stanzas from {args.input_file}...")

    all_stanzas = []
    all_ids = []
    all_metadatas = []

    # First pass: collect everything into memory
    for i, track_data in enumerate(
        tqdm(read_concatenated_json(args.input_file), desc="Reading dataset")
    ):
        try:
            artist_name = track_data.get("artist_name", "")
            if not artist_name and "track_data" in track_data:
                artist_name = track_data["track_data"].get("artist_name", "")

            # Extract genre
            genre = "Unknown"
            try:
                genre_list = track_data["track_data"]["primary_genres"][
                    "music_genre_list"
                ]
                if genre_list:
                    genre = genre_list[0]["music_genre"]["music_genre_name"]
            except (KeyError, IndexError, TypeError):
                pass

            lyrics_txt = track_data.get("lyrics_txt", "")
            if not lyrics_txt:
                continue

            track_id = str(track_data.get("track_id", f"unknown_{i}"))

            # Split lyrics by double newlines (\n\n)
            stanzas = [s.strip() for s in lyrics_txt.split("\n\n") if s.strip()]

            for j, stanza in enumerate(stanzas):
                chunk_id = f"{track_id}_stanza_{j}"

                all_stanzas.append(stanza)
                all_ids.append(chunk_id)
                all_metadatas.append(
                    {
                        "artist_name": artist_name,
                        "genre": genre,
                        "track_id": track_id,
                        "stanza_index": j,
                    }
                )

        except Exception as e:
            print(f"Error processing track {i}: {e}")
            continue

    total_chunks = len(all_stanzas)
    print(f"Total stanzas collected: {total_chunks}")

    print(f"Embedding and inserting in batches of {args.batch_size}...")

    # Second pass: iterate with user-specified batch_size
    for i in tqdm(range(0, total_chunks, args.batch_size), desc="Embedding batches"):
        batch_stanzas = all_stanzas[i : i + args.batch_size]
        batch_ids = all_ids[i : i + args.batch_size]
        batch_metadatas = all_metadatas[i : i + args.batch_size]

        embeddings = encode_documents(
            model,
            batch_stanzas,
            batch_size=args.batch_size,
            show_progress_bar=False,
        ).tolist()

        collection.add(
            ids=batch_ids,
            embeddings=embeddings,
            metadatas=batch_metadatas,
        )

    print(f"\nSuccessfully processed and added tracks to the database.")
    print(f"Total chunks in DB: {collection.count()}")


if __name__ == "__main__":
    main()
