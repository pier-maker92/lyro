"""Mood definitions and query prompts (per product spec)."""

MOODS = ["love", "adventure", "funny", "chill", "party"]

DEFAULT_QUERY_PROMPT = "Retrieve song lyrics that visually match this scene."

MOOD_QUERY_PROMPTS = {
    "love": "Retrieve song lyrics that match this visual scene. Prioritize lyrics with a romantic mood: longing, devotion, intimacy, tenderness, passion, and heartfelt emotion.",
    "adventure": "Retrieve song lyrics that match this visual scene. Prioritize lyrics with an adventurous mood: exploration, freedom, epic journeys, bold action, and triumphant energy.",
    "funny": "Retrieve song lyrics that match this visual scene. Prioritize lyrics with a humorous mood: wit, absurdity, playful irony, comedy, and lighthearted fun.",
    "chill": "Retrieve song lyrics that match this visual scene. Prioritize lyrics with a relaxed mood: calm, ease, reflection, gentle warmth, and peaceful atmosphere.",
    "party": "Retrieve song lyrics that match this visual scene. Prioritize lyrics with a celebratory mood: high energy, dancing, excitement, nightlife, and hype.",
}


# Short descriptions used to embed each mood into the catalog's vector space.
# The retrieved lyric embeddings are clustered by cosine similarity to these.
MOOD_TEXTS = {
    "love": "Romantic love lyrics: longing, devotion, intimacy, tenderness, passion, and heartfelt emotion.",
    "adventure": "Adventurous lyrics: exploration, freedom, epic journeys, bold action, and triumphant energy.",
    "funny": "Humorous lyrics: wit, absurdity, playful irony, comedy, and lighthearted fun.",
    "chill": "Relaxed lyrics: calm, ease, reflection, gentle warmth, and a peaceful atmosphere.",
    "party": "Celebratory party lyrics: high energy, dancing, excitement, nightlife, and hype.",
}


def get_query_prompt(mood: str | None) -> str:
    if not mood:
        return DEFAULT_QUERY_PROMPT
    return MOOD_QUERY_PROMPTS.get(
        mood.lower().strip(),
        f"Retrieve song lyrics that match this visual scene with a {mood} emotional tone.",
    )
