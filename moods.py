MOODS = ["love", "adventure", "funny", "chill", "party"]

DEFAULT_QUERY_PROMPT = (
    "Retrieve song lyrics that match this visual scene, "
    "considering both visual imagery and emotional mood."
)

DOCUMENT_PROMPT = (
    "Represent song lyrics for retrieving matching visual scenes or videos. "
    "Capture the emotional mood, tone, and thematic imagery, including romantic, "
    "adventurous, humorous, relaxed, and celebratory qualities."
)

MOOD_QUERY_PROMPTS = {
    "love": (
        "Retrieve song lyrics that match this visual scene. "
        "Prioritize lyrics with a romantic mood: longing, devotion, intimacy, "
        "tenderness, passion, and heartfelt emotion."
    ),
    "adventure": (
        "Retrieve song lyrics that match this visual scene. "
        "Prioritize lyrics with an adventurous mood: exploration, freedom, "
        "epic journeys, bold action, and triumphant energy."
    ),
    "funny": (
        "Retrieve song lyrics that match this visual scene. "
        "Prioritize lyrics with a humorous mood: wit, absurdity, playful irony, "
        "comedy, and lighthearted fun."
    ),
    "chill": (
        "Retrieve song lyrics that match this visual scene. "
        "Prioritize lyrics with a relaxed mood: calm, ease, reflection, "
        "gentle warmth, and peaceful atmosphere."
    ),
    "party": (
        "Retrieve song lyrics that match this visual scene. "
        "Prioritize lyrics with a celebratory mood: high energy, dancing, "
        "excitement, nightlife, and hype."
    ),
}


def get_query_prompt(mood: str | None) -> str:
    if not mood:
        return DEFAULT_QUERY_PROMPT
    key = mood.lower().strip()
    return MOOD_QUERY_PROMPTS.get(
        key,
        f"Retrieve song lyrics that match this visual scene with a {mood} emotional tone.",
    )


def format_document(text: str) -> str:
    return f"{DOCUMENT_PROMPT}\n{text}"


def format_query(user_text: str, mood: str | None = None) -> str:
    return f"{get_query_prompt(mood)}\n{user_text}"
