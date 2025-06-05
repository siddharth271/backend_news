# categorizer.py
import logging
import httpx

logger = logging.getLogger(__name__)

CATEGORY_LABELS = [
    "technology",
    "sports",
    "health",
    "business",
    "entertainment",
    "science",
    "general"
]

async def classify_category_ollama(text: str) -> str:
    """
    Use Ollama (llama2:7b-chat) to classify the text into a news category.
    """
    try:
        prompt = f"""
You are a news classifier.
Your task is to classify a news article into exactly one of these categories:
{", ".join(CATEGORY_LABELS)}.

Article:
{text}

Respond only with the category name from the list.
"""

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "llama2:7b-chat",
                    "prompt": prompt.strip(),
                    "stream": False
                },
                timeout=20
            )
            result = response.json()
            output = result.get("response", "").strip().lower()

            # Return clean category if it's valid
            for label in CATEGORY_LABELS:
                if label in output:
                    return label
            return "general"

    except Exception as e:
        logger.error(f"Error classifying category with Ollama: {e}")
        return "general"
