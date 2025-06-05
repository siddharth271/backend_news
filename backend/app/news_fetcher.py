# news_fetcher.py - Automated news fetching from multiple sources
import asyncio
import aiohttp
import hashlib
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass
import feedparser
from bs4 import BeautifulSoup
from newspaper import Article
from categorizer import classify_category_ollama

import requests

from firestore import add_news_item, fetch_news_items
from summarizer import generate_summary

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class NewsItem:
    title: str
    content: str
    url: str
    source: str
    published_date: datetime
    image_url: Optional[str] = None
    authors: List[str] = None


class NewsAPIClient:
    """News API integration"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://newsapi.org/v2"

    async def fetch_top_headlines(self, country='us', category=None, page_size=20) -> List[NewsItem]:
        """Fetch top headlines from News API"""
        url = f"{self.base_url}/top-headlines"
        params = {
            'apiKey': self.api_key,
            'country': country,
            'pageSize': page_size
        }
        if category:
            params['category'] = category

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, params=params) as response:
                    data = await response.json()

                    if data.get('status') == 'ok':
                        articles = []
                        for article in data.get('articles', []):
                            if article.get('title') and article.get('url'):
                                # Get full content using newspaper
                                content = await self._get_full_content(article['url'])

                                # Ensure image URL is valid
                                image_url = article.get('urlToImage')
                                if image_url and not image_url.startswith(('http://', 'https://')):
                                    image_url = None

                                articles.append(NewsItem(
                                    title=article['title'],
                                    content=content or article.get('description', ''),
                                    url=article['url'],
                                    source=article.get('source', {}).get('name', 'Unknown'),
                                    published_date=datetime.fromisoformat(
                                        article['publishedAt'].replace('Z', '+00:00')),
                                    image_url=image_url,
                                    authors=[article.get('author')] if article.get('author') else []
                                ))
                        return articles
                    else:
                        logger.error(f"News API error: {data.get('message')}")
                        return []
            except Exception as e:
                logger.error(f"Error fetching from News API: {e}")
                return []

    async def _get_full_content(self, url: str) -> str:
        """Get full article content using newspaper"""
        try:
            article = Article(url)
            article.download()
            article.parse()
            return article.text
        except:
            return ""


class RSSFeedFetcher:
    """RSS feed integration for various news sources"""

    RSS_FEEDS = {
        'BBC': 'http://feeds.bbci.co.uk/news/rss.xml',
        'CNN': 'http://rss.cnn.com/rss/edition.rss',
        'Reuters': 'https://reuters.com/rssFeed/topNews',
        'The Guardian': 'https://www.theguardian.com/world/rss',
        'The Hindu': 'https://www.thehindu.com/news/national/feeder/default.rss',
        'The Hindu International':'https://www.thehindu.com/news/international/feeder/default.rss' ,
        'Associated Press': 'https://feeds.apnews.com/rss/apf-topnews',
        'NDTV': 'https://feeds.feedburner.com/ndtvnews-top-stories',
        'Hindustan Times': 'https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml'
    }

    async def fetch_from_rss(self, source_name: str = None) -> List[NewsItem]:
        """Fetch articles from RSS feeds"""
        feeds_to_fetch = {source_name: self.RSS_FEEDS[source_name]} if source_name else self.RSS_FEEDS
        all_articles = []

        for source, feed_url in feeds_to_fetch.items():
            try:
                logger.info(f"Fetching RSS from {source}...")

                # Parse RSS feed
                feed = feedparser.parse(feed_url)

                for entry in feed.entries[:10]:  # Limit to 10 per source
                    # Get full content
                    content = await self._extract_content(entry.link)

                    # Extract image
                    image_url = self._extract_image(entry, content)

                    published_date = datetime.now()
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        published_date = datetime(*entry.published_parsed[:6])

                    all_articles.append(NewsItem(
                        title=entry.title,
                        content=content or entry.get('summary', ''),
                        url=entry.link,
                        source=source,
                        published_date=published_date,
                        image_url=image_url,
                        authors=[]
                    ))

            except Exception as e:
                logger.error(f"Error fetching RSS from {source}: {e}")
                continue

        return all_articles

    async def _extract_content(self, url: str) -> str:
        """Extract full article content"""
        try:
            article = Article(url)
            article.download()
            article.parse()
            return article.text
        except Exception as e:
            logger.debug(f"Failed to extract content from {url}: {e}")
            return ""

    def _extract_image(self, entry, content: str) -> Optional[str]:
        """Extract image URL from RSS entry or content"""
        # Try from RSS entry first
        if hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
            return entry.media_thumbnail[0]['url']

        if hasattr(entry, 'media_content') and entry.media_content:
            return entry.media_content[0]['url']

        # Try parsing from entry summary
        if hasattr(entry, 'summary'):
            soup = BeautifulSoup(entry.summary, 'html.parser')
            img = soup.find('img')
            if img and img.get('src'):
                return img['src']

        return None


class NewsFetcher:
    """Main news fetcher orchestrator"""

    def __init__(self, news_api_key: str = None):
        self.news_api = NewsAPIClient(news_api_key) if news_api_key else None
        self.rss_fetcher = RSSFeedFetcher()
        self.processed_urls = set()

    async def fetch_all_news(self) -> List[Dict]:
        """Fetch news from all sources and process"""
        all_articles = []

        # Fetch from RSS feeds
        logger.info("Fetching from RSS feeds...")
        rss_articles = await self.rss_fetcher.fetch_from_rss()
        all_articles.extend(rss_articles)

        # Fetch from News API if available
        if self.news_api:
            logger.info("Fetching from News API...")
            api_articles = await self.news_api.fetch_top_headlines()
            all_articles.extend(api_articles)

        # Remove duplicates and process
        unique_articles = self._remove_duplicates(all_articles)
        processed_articles = await self._process_articles(unique_articles)

        return processed_articles

    def _remove_duplicates(self, articles: List[NewsItem]) -> List[NewsItem]:
        """Remove duplicate articles based on URL and title similarity"""
        seen_urls = set()
        seen_titles = set()
        unique_articles = []

        for article in articles:
            # Skip if URL already processed
            if article.url in seen_urls:
                continue

            # Create title hash for similarity check
            title_hash = hashlib.md5(article.title.lower().encode()).hexdigest()
            if title_hash in seen_titles:
                continue

            seen_urls.add(article.url)
            seen_titles.add(title_hash)
            unique_articles.append(article)

        return unique_articles

    async def _process_articles(self, articles: List[NewsItem]) -> List[Dict]:
        """Process articles: summarize and prepare for storage"""
        processed = []

        for article in articles:
            try:
                # Skip if already processed
                if article.url in self.processed_urls:
                    continue

                # Generate summary
                summary = await generate_summary(article.content)

                # Prepare data for Firestore
                category = await classify_category_ollama(f"{article.title}\n\n{article.content[:1000]}")

                data = {
                    "title": article.title,
                    "summary": summary,
                    "content": article.content[:1000],
                    "author": article.authors or [],
                    "published_date": article.published_date.isoformat(),
                    "source": article.source,
                    "url": article.url,
                    "image_url": article.image_url,
                    "category": category,
                    "created_at": datetime.now().isoformat(),
                    "url_hash": hashlib.md5(article.url.encode()).hexdigest()
                }

                # Save to Firestore
                await add_news_item(data)
                processed.append(data)
                self.processed_urls.add(article.url)

                logger.info(f"Processed: {article.title[:50]}...")

            except Exception as e:
                logger.error(f"Error processing article {article.url}: {e}")
                continue

        return processed

    async def continuous_fetch(self, interval_minutes: int = 30):
        """Continuously fetch news at specified intervals"""
        logger.info(f"Starting continuous news fetching every {interval_minutes} minutes...")

        while True:
            try:
                logger.info("Starting news fetch cycle...")
                articles = await self.fetch_all_news()
                logger.info(f"Processed {len(articles)} new articles")

                # Wait for next cycle
                await asyncio.sleep(interval_minutes * 60)

            except Exception as e:
                logger.error(f"Error in continuous fetch cycle: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes before retrying


# Scheduler integration
class NewsScheduler:
    """Background task scheduler for news fetching"""

    def __init__(self, news_api_key: str = None):
        self.fetcher = NewsFetcher(news_api_key)
        self.running = False

    async def start_scheduler(self, interval_minutes: int = 30):
        """Start the background news fetching"""
        if self.running:
            logger.warning("Scheduler already running")
            return

        self.running = True
        logger.info("Starting news scheduler...")

        # Create background task
        task = asyncio.create_task(self.fetcher.continuous_fetch(interval_minutes))
        return task

    def stop_scheduler(self):
        """Stop the background news fetching"""
        self.running = False


# Usage example
async def main():
    """Test the news fetcher"""
    # Initialize with your News API key (optional)
    news_api_key = "YOUR_NEWS_API_KEY_HERE"  # Get from https://newsapi.org

    fetcher = NewsFetcher(news_api_key)

    # Fetch news once
    articles = await fetcher.fetch_all_news()
    print(f"Fetched and processed {len(articles)} articles")

    # Or start continuous fetching
    # await fetcher.continuous_fetch(interval_minutes=30)


if __name__ == "__main__":
    asyncio.run(main())