import argparse
import json
import chromadb
import torch
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

def read_concatenated_json(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
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
    parser.add_argument("--batch_size", type=int, default=32, help="Batch size for embedding processing")
    parser.add_argument("--input_file", type=str, default="/workspace/lyra/lyrics_dataset.jsonl", help="Path to the JSON/JSONL dataset file")
    args = parser.parse_args()

    device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"Loading SentenceTransformer model on {device}...")
    # Load the multimodal embedding model as requested
    model = SentenceTransformer("Qwen/Qwen3-VL-Embedding-2B", trust_remote_code=True, device=device)

    print("Initializing ChromaDB...")
    client = chromadb.PersistentClient(path="./lyrics_catalog_db")
    collection = client.get_or_create_collection(
        name="song_lyrics",
        metadata={"hnsw:space": "cosine"}
    )

    print(f"Collecting all stanzas from {args.input_file}...")
    
    all_prompts = []
    all_ids = []
    all_metadatas = []
    all_documents = []

    # First pass: collect everything into memory
    seen_track_ids = set()
    for i, track_data in enumerate(tqdm(read_concatenated_json(args.input_file), desc="Reading dataset")):
        try:
            artist_name = track_data.get("artist_name", "")
            if not artist_name and "track_data" in track_data:
                artist_name = track_data["track_data"].get("artist_name", "")

            # Extract genre
            genre = "Unknown"
            try:
                genre_list = track_data["track_data"]["primary_genres"]["music_genre_list"]
                if genre_list:
                    genre = genre_list[0]["music_genre"]["music_genre_name"]
            except (KeyError, IndexError, TypeError):
                pass
            
            lyrics_txt = track_data.get("lyrics_txt", "")
            if not lyrics_txt:
                continue
                
            track_id = str(track_data.get("track_id", f"unknown_{i}"))
            if track_id in seen_track_ids:
                continue
            seen_track_ids.add(track_id)
            
            # Split lyrics by double newlines (\n\n)
            stanzas = [s.strip() for s in lyrics_txt.split('\n\n') if s.strip()]
            
            for j, stanza in enumerate(stanzas):
                chunk_id = f"{track_id}_stanza_{j}"
                
                # Setup prompt as requested
                lyric_prompt = f"Represent the following song lyrics for retrieving matching visual scenes or videos: {stanza}"
                
                all_prompts.append(lyric_prompt)
                all_ids.append(chunk_id)
                all_documents.append(stanza)
                all_metadatas.append({
                    "artist_name": artist_name,
                    "genre": genre,
                    "track_id": track_id,
                    "stanza_index": j
                })
                    
        except Exception as e:
            print(f"Error processing track {i}: {e}")
            continue

    total_chunks = len(all_prompts)
    print(f"Total stanzas collected: {total_chunks}")
    
    print(f"Embedding and inserting in batches of {args.batch_size}...")
    
    # Second pass: iterate with user-specified batch_size
    for i in tqdm(range(0, total_chunks, args.batch_size), desc="Embedding batches"):
        batch_prompts = all_prompts[i : i + args.batch_size]
        batch_ids = all_ids[i : i + args.batch_size]
        batch_documents = all_documents[i : i + args.batch_size]
        batch_metadatas = all_metadatas[i : i + args.batch_size]
        
        # Calculate embeddings for the batch
        embeddings = model.encode(batch_prompts, batch_size=args.batch_size, show_progress_bar=False).tolist()
        
        # Insert batch into ChromaDB
        collection.add(
            ids=batch_ids,
            embeddings=embeddings,
            metadatas=batch_metadatas,
            documents=batch_documents
        )

    print(f"\nSuccessfully processed and added tracks to the database.")
    print(f"Total chunks in DB: {collection.count()}")

if __name__ == "__main__":
    main()
