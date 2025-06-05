# config.py - Configuration settings
import os
from typing import Dict, List


class Config:
    """Application configuration"""

    # News API Configuration
    NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")  # Get from https://newsapi.org
    NEWS_API_BASE_URL = "https://newsapi.org/v2"

    # Firestore Configuration
    GOOGLE_APPLICATION_CREDENTIALS = os.getenv(
        "GOOGLE_APPLICATION_CREDENTIALS",
        "../credentials/firebase-adminsdk.json"
    )
    FIRESTORE_COLLECTION = "news_summaries"

    # Ollama Configuration
    OLLAMA_MODEL = "llama2:7b-chat"
    SUMMARY_MAX_LENGTH = 50  # words
    CONTENT_MAX_LENGTH = 2000  # characters

    # Fetching Configuration
    DEFAULT_FETCH_INTERVAL = 30  # minutes
    MAX_ARTICLES_PER_SOURCE = 10
    MAX_ARTICLES_PER_CYCLE = 50

    # RSS Feed Sources
    RSS_SOURCES = {
        'BBC': 'http://feeds.bbci.co.uk/news/rss.xml',
        'CNN': 'http://rss.cnn.com/rss/edition.rss',
        'Reuters': 'https://reuters.com/rssFeed/topNews',
        'TechCrunch': 'https://techcrunch.com/feed/',
        'The Guardian': 'https://www.theguardian.com/world/rss',
        'NPR': 'https://feeds.npr.org/1001/rss.xml',
        'Associated Press': 'https://feeds.apnews.com/rss/apf-topnews',
        'Hacker News': 'https://hnrss.org/frontpage',
        'Wired': 'https://www.wired.com/feed/rss',
        'Ars Technica': 'http://feeds.arstechnica.com/arstechnica/index'
    }

    # News Categories for News API
    NEWS_CATEGORIES = [
        'general', 'business', 'entertainment', 'health',
        'science', 'sports', 'technology'
    ]

    # Countries for News API
    NEWS_COUNTRIES = ['us', 'gb', 'ca', 'au', 'in']

    # Logging Configuration
    LOG_LEVEL = "INFO"
    LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


# Environment setup function
def setup_environment():
    """Setup environment variables and validate configuration"""

    # Set Google credentials if not already set
    if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = Config.GOOGLE_APPLICATION_CREDENTIALS

    # Validate required configurations
    required_files = [Config.GOOGLE_APPLICATION_CREDENTIALS]
    missing_files = [f for f in required_files if not os.path.exists(f)]

    if missing_files:
        print("⚠️  Missing required files:")
        for file in missing_files:
            print(f"   - {file}")
        print("Please ensure all required files are in place.")
        return False

    print("✅ Environment setup complete")
    return True


# requirements.txt content
REQUIREMENTS = """
fastapi==0.104.1
uvicorn[standard]==0.24.0
google-cloud-firestore==2.13.1
newspaper3k==0.2.8
beautifulsoup4==4.12.2
aiohttp==3.9.0
feedparser==6.0.10
requests==2.31.0
python-multipart==0.0.6
pydantic==2.5.0
asyncio==3.4.3
hashlib3==2.0.1
python-dotenv==1.0.0
""".strip()

# .env template
ENV_TEMPLATE = """
# News API Key (optional but recommended)
# Get your free API key from: https://newsapi.org
NEWS_API_KEY=your_news_api_key_here

# Google Cloud Firestore Credentials Path
GOOGLE_APPLICATION_CREDENTIALS=../credentials/firebase-adminsdk.json

# Ollama Configuration
OLLAMA_MODEL=llama2:7b-chat

# Fetching Configuration
DEFAULT_FETCH_INTERVAL=30
LOG_LEVEL=INFO

# Optional: Custom RSS Sources (comma-separated)
# CUSTOM_RSS_SOURCES=https://example.com/rss1,https://example.com/rss2
""".strip()

if __name__ == "__main__":
    # Create requirements.txt
    with open("requirements.txt", "w") as f:
        f.write(REQUIREMENTS)
    print("✅ Created requirements.txt")

    # Create .env template
    with open(".env.template", "w") as f:
        f.write(ENV_TEMPLATE)
    print("✅ Created .env.template")

    # Setup environment
    setup_environment()