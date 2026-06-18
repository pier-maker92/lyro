# Lyra 🎶📸

Lyra is a multimodal retrieval system designed to find the perfect song lyrics that match the visual content of a video or image. By leveraging **llama-nemotron-embed-vl-1b-v2** (via `SentenceTransformer`) and **ChromaDB**, Lyra bridges the gap between visual scenes and lyrical context.

## 🚀 Features

- **Multimodal Search:** Pass an MP4 video or an image, and Lyra will find the lyrics that best describe the visual scene.
- **Smart Filtering:** Filter your search by `genre`, `artist`, or add a specific thematic `mood` (e.g., *love*, *fun*, *adventure*, *chill/relax*).

## 📦 Installation

Ensure you have a Python environment set up (e.g., using Conda), then install the required dependencies:

```bash
pip install -r requirements.txt
```

## 🛠️ Usage

### 1. Ingesting the Dataset
First, embed your lyrics dataset into the ChromaDB vector store. The script will automatically chunk the lyrics into individual stanzas.

```bash
# Basic usage (defaults to lyrics_dataset.jsonl with a batch size of 32)
python embed_lyrics.py

# Advanced usage
python embed_lyrics.py --input_file /path/to/dataset.jsonl --batch_size 64
```

### 2. Retrieving Lyrics
Once your database is populated, you can query it using a video or an image file.

```bash
# Basic query using a video
python retrieve.py path/to/video.mp4

# Advanced query with custom FPS sampling and mood/genre filters
python retrieve.py path/to/video.mp4 --fps 2 --mood "adventure" --genre "Dance"

# Query using an image
python retrieve.py path/to/image.jpg --mood "love" --top_k 10
```

## ⚙️ How it Works

1. **Embedding (`embed_lyrics.py`):** Parses the lyrics dataset, splits songs into stanzas, wraps them in a specific retrieval prompt, and encodes them using the `nvidia/llama-nemotron-embed-vl-1b-v2` model. The resulting vectors are stored persistently in ChromaDB.
2. **Retrieval (`retrieve.py`):** 
    - Uses `PyAV` to accurately decode and sample frames from a video file at the requested FPS (or loads a single image).
    - Downsamples frames to a standard 720p height to optimize memory usage.
    - Constructs a dynamic multimodal prompt (incorporating the requested `mood`).
    - Computes the visual embedding and queries ChromaDB using cosine similarity to return the top matching lyrics.
