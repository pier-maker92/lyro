import argparse
import json
import re

import chromadb
import numpy as np
from tqdm import tqdm

from embedding import encode_documents, get_device, load_model
from moods import MOODS, apply_affinity, top_mood


def clean_stanza(text: str) -> str:
    """Rimuove il testo tra parentesi e normalizza gli spazi."""
    text = re.sub(r'\(.*?\)', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def is_too_repetitive(text: str) -> bool:
    """Determina se una stanza è troppo ripetitiva (es. solo vocalizzi o troppe parole ripetute)."""
    words = text.lower().split()
    if not words:
        return True

    clean_words = [re.sub(r'[^\w\s]', '', w) for w in words]
    clean_words = [w for w in clean_words if w]

    if not clean_words:
        return True

    unique_clean = set(clean_words)
    vocalizations = {'oh', 'ah', 'la', 'na', 'eh', 'yeah', 'ooh', 'hey', 'uh', 'da', 'doo', 'dum', 'eeeh'}

    if all(w in vocalizations for w in unique_clean):
        return True

    vocal_count = sum(1 for w in clean_words if w in vocalizations)
    if len(clean_words) > 3 and vocal_count / len(clean_words) >= 0.6:
        return True

    unique_ratio = len(unique_clean) / len(clean_words)
    if len(clean_words) >= 6 and unique_ratio < 0.3:
        return True

    return False


def get_length_bin(text: str) -> str:
    """Calcola il bin della lunghezza in caratteri con step 25."""
    length = len(text)
    if length >= 150:
        return ">150"
    lower = (length // 25) * 25
    upper = lower + 25
    return f"{lower}-{upper}"


def read_concatenated_json(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def embed_mood_anchors(model) -> dict[str, np.ndarray]:
    """Embed all 20 mood keyword prompts once and return name→vector."""
    print("Embedding mood anchors...")
    mood_names = list(MOODS.keys())
    mood_texts = [m["keywords"] for m in MOODS.values()]
    vectors = encode_documents(model, mood_texts, batch_size=len(mood_texts))
    return {name: vectors[i] for i, name in enumerate(mood_names)}


def assign_mood(
    stanza_vec: np.ndarray,
    mood_anchors: dict[str, np.ndarray],
    genre: str,
) -> str:
    raw_scores = {
        mood: cosine_similarity(stanza_vec, anchor)
        for mood, anchor in mood_anchors.items()
    }
    weighted = apply_affinity(raw_scores, genre)
    return top_mood(weighted)


def main():
    parser = argparse.ArgumentParser(description="Embed lyrics into ChromaDB.")
    parser.add_argument(
        "--batch_size", type=int, default=8, help="Batch size for embedding processing"
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

    mood_anchors = embed_mood_anchors(model)

    print("Initializing ChromaDB...")
    client = chromadb.PersistentClient(path="./lyrics_catalog_db")
    collection = client.get_or_create_collection(
        name="song_lyrics_min", metadata={"hnsw:space": "cosine"}
    )

    print(f"Collecting all stanzas from {args.input_file}...")

    all_stanzas = []
    all_ids = []
    all_metadatas = []
    seen_ids = set()

    # First pass: collect everything into memory
    for i, track_data in enumerate(
        tqdm(read_concatenated_json(args.input_file), desc="Reading dataset")
    ):
        try:
            # Extract genre
            genre = "Unknown"
            try:
                genre_list = track_data["track_data"]["primary_genres"]["music_genre_list"]
                if genre_list:
                    genre = genre_list[0]["music_genre"]["music_genre_name_extended"]
            except (KeyError, IndexError, TypeError):
                pass

            # Extract language
            language = "Unknown"
            try:
                language = track_data["lyrics_data"]["lyrics"]["lyrics_language"]
            except (KeyError, TypeError):
                pass

            lyrics_txt = track_data.get("lyrics_txt", "")
            if not lyrics_txt:
                continue

            track_id = str(track_data.get("track_id", f"unknown_{i}"))

            # Split lyrics by double newlines (\n\n)
            stanzas = [s.strip() for s in lyrics_txt.split("\n\n") if s.strip()]

            for j, stanza in enumerate(stanzas):
                chunk_id = f"{track_id}_stanza_{j}"

                if chunk_id in seen_ids:
                    continue
                seen_ids.add(chunk_id)

                cleaned_stanza = clean_stanza(stanza)
                
                # Scarta se vuota o troppo ripetitiva
                if not cleaned_stanza or is_too_repetitive(cleaned_stanza):
                    continue

                length_bin = get_length_bin(cleaned_stanza)

                all_stanzas.append(cleaned_stanza)
                all_ids.append(chunk_id)
                all_metadatas.append(
                    {
                        "genre": genre,
                        "language": language,
                        "length_bin": length_bin,
                    }
                )

        except Exception as e:
            print(f"Error processing track {i}: {e}")
            continue

    total_chunks = len(all_stanzas)
    print(f"Total stanzas collected: {total_chunks}")

    print(f"Embedding all stanzas (batch_size={args.batch_size})...")

    # Second pass: Embed all stanzas at once to utilize SentenceTransformer optimizations
    embeddings = encode_documents(
        model,
        all_stanzas,
        batch_size=args.batch_size,
        show_progress_bar=True,
    )

    print("Assigning moods to stanzas...")
    for j, (vec, meta) in enumerate(tqdm(zip(embeddings, all_metadatas), total=total_chunks, desc="Assigning moods")):
        mood = assign_mood(vec, mood_anchors, meta["genre"])
        all_metadatas[j]["mood"] = mood

    embeddings_list = embeddings.tolist()

    print("Inserting into database...")
    db_batch_size = 5000
    for i in tqdm(range(0, total_chunks, db_batch_size), desc="Inserting batches"):
        collection.add(
            ids=all_ids[i : i + db_batch_size],
            embeddings=embeddings_list[i : i + db_batch_size],
            metadatas=all_metadatas[i : i + db_batch_size],
        )

    print(f"\nSuccessfully processed and added tracks to the database.")
    print(f"Total chunks in DB: {collection.count()}")


if __name__ == "__main__":
    main()
