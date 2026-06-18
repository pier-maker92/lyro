import argparse
import chromadb
import av
from PIL import Image

from embedding import encode_visual_query, get_device, load_model
from moods import MOODS
from mxm import MusixmatchClient


def load_first_video_frame(video_path, target_height=720):
    container = av.open(video_path)
    for frame in container.decode(video=0):
        img = frame.to_image()
        w, h = img.size
        if h > target_height:
            new_w = int((target_height / h) * w)
            img = img.resize((new_w, target_height), Image.Resampling.LANCZOS)
        return img
    raise ValueError(f"No video frames found in {video_path}")


def get_track_id(chunk_id: str, metadata: dict) -> str:
    track_id = metadata.get("track_id")
    if track_id:
        return str(track_id)
    if "_stanza_" in chunk_id:
        return chunk_id.rsplit("_stanza_", 1)[0]
    return chunk_id


def main():
    parser = argparse.ArgumentParser(
        description="Retrieve song lyrics based on a video or image query."
    )
    parser.add_argument(
        "query_path", type=str, help="Path to the video or image file (e.g., query.mp4)"
    )
    parser.add_argument("--genre", type=str, default=None, help="Filter by genre")
    parser.add_argument(
        "--artist", type=str, default=None, help="Filter by artist name"
    )
    parser.add_argument(
        "--mood",
        type=str,
        default=None,
        choices=MOODS,
        help=f"Thematic mood for lyrics matching ({', '.join(MOODS)})",
    )
    parser.add_argument(
        "--top_k", type=int, default=5, help="Number of results to retrieve"
    )
    args = parser.parse_args()

    device = get_device()
    print(f"Loading SentenceTransformer model on {device}...")
    model = load_model(device)

    print("Embedding query...")
    is_video = args.query_path.lower().endswith(
        (".mp4", ".avi", ".mov", ".mkv", ".webm")
    )

    if is_video:
        print(f"Extracting first frame from video: {args.query_path}")
        media_data = load_first_video_frame(args.query_path)
    else:
        media_data = Image.open(args.query_path)
        w, h = media_data.size
        if h > 720:
            new_w = int((720 / h) * w)
            media_data = media_data.resize((new_w, 720), Image.Resampling.LANCZOS)

    user_text = "Match these visuals to song lyrics:"
    if args.mood:
        print(f"Using mood: {args.mood}")

    query_embedding = encode_visual_query(
        model, media_data, user_text=user_text, mood=args.mood
    ).tolist()

    print("Connecting to ChromaDB...")
    client = chromadb.PersistentClient(path="./lyrics_catalog_db")
    collection = client.get_collection(name="song_lyrics_min")

    # Build the where clause for metadata filtering
    where_conditions = []
    if args.genre:
        where_conditions.append({"genre": args.genre})
    if args.artist:
        where_conditions.append({"artist_name": args.artist})

    where_clause = None
    if len(where_conditions) > 1:
        where_clause = {"$and": where_conditions}
    elif len(where_conditions) == 1:
        where_clause = where_conditions[0]

    print("Searching for matches...")
    # Execute the search with a larger top_k to allow for deduplication
    search_k = args.top_k * 5
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=search_k,
        where=where_clause,
        include=["metadatas", "distances"],
    )

    print("\n--- Search Results ---")
    if not results["ids"] or not results["ids"][0]:
        print("No results found.")
        return

    unique_results = []
    seen_tracks = set()

    for i in range(len(results["ids"][0])):
        chunk_id = results["ids"][0][i]
        metadata = results["metadatas"][0][i]
        track_id = get_track_id(chunk_id, metadata)

        if track_id not in seen_tracks:
            seen_tracks.add(track_id)
            unique_results.append(
                {
                    "id": chunk_id,
                    "distance": results["distances"][0][i],
                    "metadata": metadata,
                }
            )

            # Stop once we have top_k unique tracks
            if len(unique_results) == args.top_k:
                break

    try:
        mxm_client = MusixmatchClient()
    except ValueError as e:
        print(f"Warning: {e}")
        mxm_client = None

    for i, res in enumerate(unique_results):
        track_id = get_track_id(res["id"], res["metadata"])
        details = (
            mxm_client.fetch_match_details(track_id, res["id"])
            if mxm_client
            else {}
        )

        print(f"\nMatch {i+1}:")
        print(f"  ID:       {res['id']}")
        print(f"  Distance: {res['distance']:.4f}")
        print(f"  Artist:   {details.get('artist_name') or 'Unknown'}")
        print(f"  Song:     {details.get('track_name') or 'Unknown'}")
        print(f"  Genre:    {res['metadata'].get('genre', 'Unknown')}")
        print(f"  Track ID: {track_id}")

        stanza = details.get("stanza")
        if stanza:
            lyrics_snippet = stanza.replace("\n", " / ")
            print(f"  Lyrics:   {lyrics_snippet}")
        else:
            print("  Lyrics:   (unavailable)")


if __name__ == "__main__":
    main()
