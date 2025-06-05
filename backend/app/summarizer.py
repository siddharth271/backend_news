import asyncio
import requests
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)


def fetch_article_text(url: str) -> str:
    """Fetch the article text from the given URL."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        res = requests.get(url, timeout=10, headers=headers)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')

        # Extract article content more thoroughly
        article_content = []

        # Try multiple selectors for article content
        content_selectors = ['article', '.article-content', '.story-content', '.post-content']
        for selector in content_selectors:
            content = soup.select_one(selector)
            if content:
                paragraphs = content.find_all('p')
                break
        else:
            # Fallback to all paragraphs if no article container found
            paragraphs = soup.find_all('p')

        for p in paragraphs:
            # Skip navigation, author bios, etc.
            if len(p.get_text(strip=True)) > 50:  # Only substantial paragraphs
                article_content.append(p.get_text(strip=True))

        return "\n\n".join(article_content)

    except Exception as e:
        logger.error(f"Error fetching article text: {str(e)}")
        return ""


async def generate_summary(text: str) -> str:
    """Generate a summary of the given text."""
    if not text:
        return "No content available to summarize."

    # Use a simpler extractive summarization as fallback
    try:
        sentences = text.split('.')
        if len(sentences) <= 3:
            return text

        # Take first 2 sentences and last sentence
        summary = '. '.join(sentences[:2] + [sentences[-1]]) + '.'
        return summary.strip()

    except Exception as e:
        logger.error(f"Error generating summary: {str(e)}")
        return text[:200] + "..."  # Fallback to truncation


async def summarize_url(url: str) -> str:
    """Full pipeline: fetch article text from URL and generate summary."""
    article_text = fetch_article_text(url)
    if not article_text:
        return "Could not fetch article content."

    summary = await generate_summary(article_text)
    return summary