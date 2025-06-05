from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel
from datetime import datetime
import traceback
import logging
import uvicorn
import asyncio
import os
import sys
from typing import Optional, List
from scraper import scrape_article
from summarizer import generate_summary
from firestore import add_news_item, fetch_news_items
from news_fetcher import NewsScheduler, NewsFetcher
from categorizer import classify_category_ollama


if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

app = FastAPI(title="PulseNews API", version="2.0.0")

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = None
background_task = None

# Initialize News API key from environment variable
NEWS_API_KEY = "8633ee394a324c9eab812808d981e0ea"


class ArticleURL(BaseModel):
    url: str


class SchedulerConfig(BaseModel):
    interval_minutes: int = 30
    news_api_key: str = None


# Category mapping for News API
CATEGORY_MAPPING = {
    'top': None,  # Top stories (no category filter)
    'technology': 'technology',
    'sports': 'sports',
    'health': 'health',
    'business': 'business',
    'entertainment': 'entertainment',
    'science': 'science'
}


@app.on_event("startup")
async def startup_event():
    """Initialize the news scheduler on app startup"""
    global scheduler
    logger.info("Starting PulseNews API...")

    scheduler = NewsScheduler(NEWS_API_KEY)
    # Auto-start news fetching on startup
    await start_news_fetching()


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on app shutdown"""
    global scheduler, background_task
    if scheduler:
        scheduler.stop_scheduler()
    if background_task:
        background_task.cancel()


@app.post("/scrape-and-summarize")
async def scrape_and_summarize(article_url: ArticleURL):
    """Original endpoint - scrape and summarize a single URL"""
    try:
        logger.debug(f"Received URL to scrape: {article_url.url}")

        article = scrape_article(article_url.url)
        logger.debug(
            f"Scraped article: Title='{article.title}', Authors={article.authors}, Publish Date={article.publish_date}")

        # Check scraped text before summarizing
        logger.debug(f"Scraped article text length: {len(article.text)}")
        logger.debug(f"Sample scraped text: {article.text[:300]}")

        summary = await generate_summary(article.text)
        logger.debug(f"Generated summary (first 150 chars): {summary[:150]}...")

        # Extract image if available
        image_url = None
        if hasattr(article, 'top_image') and article.top_image:
            image_url = article.top_image

        data = {
            "title": article.title,
            "summary": summary,
            "content": article.text[:1000],  # Store first 1000 chars
            "author": article.authors,
            "published_date": article.publish_date.isoformat() if article.publish_date else str(datetime.now()),
            "source": article.source_url or article_url.url,
            "url": article_url.url,
            "image_url": image_url,
            "created_at": datetime.now().isoformat(),
            "category": await classify_category_ollama(f"{article.title}\n\n{article.text[:1000]}")
        }

        logger.debug(f"Prepared data for Firestore: {data}")

        await add_news_item(data)
        logger.debug("Saved news item to Firestore successfully.")

        return {"message": "Success", "data": data}

    except Exception as e:
        logger.error("Error in /scrape-and-summarize endpoint:", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.post("/start-news-fetching")
async def start_news_fetching(config: SchedulerConfig = None):
    """Start automated news fetching"""
    global scheduler, background_task

    try:
        if background_task and not background_task.done():
            return {"message": "News fetching is already running"}

        if not scheduler:
            news_api_key = config.news_api_key if config else NEWS_API_KEY
            scheduler = NewsScheduler(news_api_key)

        interval = config.interval_minutes if config else 30
        background_task = await scheduler.start_scheduler(interval)

        return {
            "message": "News fetching started successfully",
            "interval_minutes": interval,
            "status": "running"
        }
    except Exception as e:
        logger.error(f"Error starting news fetching: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/stop-news-fetching")
async def stop_news_fetching():
    """Stop automated news fetching"""
    global scheduler, background_task

    try:
        if scheduler:
            scheduler.stop_scheduler()

        if background_task:
            background_task.cancel()
            background_task = None

        return {"message": "News fetching stopped successfully"}
    except Exception as e:
        logger.error(f"Error stopping news fetching: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/fetch-news-once")
async def fetch_news_once():
    """Manually trigger a single news fetch cycle"""
    try:
        fetcher = NewsFetcher(NEWS_API_KEY)
        articles = await fetcher.fetch_all_news()

        return {
            "message": "News fetch completed",
            "articles_processed": len(articles),
            "articles": articles[:5]  # Return first 5 as preview
        }
    except Exception as e:
        logger.error(f"Error in manual news fetch: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def is_valid_image_url(url: str) -> bool:
    """Check if the image URL is valid and not a placeholder"""
    if not url or not isinstance(url, str):
        return False

    url = url.strip()

    # Skip empty or invalid URLs
    if not url or url == 'null' or url == 'None':
        return False

    # Skip placeholder images
    if 'placeholder' in url.lower() or 'via.placeholder.com' in url:
        return False

    # Skip very short URLs that are likely invalid
    if len(url) < 10:
        return False

    # Check if URL has proper format
    if not url.startswith(('http://', 'https://')):
        return False

    # Check for common image extensions or image hosting domains
    image_indicators = [
        '.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp',
        'images.', 'img.', 'photo.', 'media.', 'cdn.',
        'amazonaws.com', 'cloudinary.com', 'imgix.net'
    ]

    return any(indicator in url.lower() for indicator in image_indicators)


@app.get("/api/news")
async def get_news(
        limit: int = Query(default=20, ge=1, le=100),
        page: int = Query(default=1, ge=1),
        category: Optional[str] = Query(default=None),
        source: Optional[str] = Query(default=None)
):
    """Get news items with pagination and filtering - only returns articles with valid images"""
    try:
        logger.debug(f"Fetching news: limit={limit}, page={page}, category={category}, source={source}")

        # Fetch more items to account for filtering (especially image filtering)
        # We need to fetch more since we'll filter out articles without images
        fetch_limit = limit * 4  # Fetch 4x more to account for filtering

        news_items = await fetch_news_items(fetch_limit)
        logger.debug(f"Fetched {len(news_items)} total items from database")

        # First, filter out articles without valid images
        articles_with_images = []
        for item in news_items:
            image_url = item.get('image_url')
            if is_valid_image_url(image_url):
                articles_with_images.append(item)

        logger.debug(f"Found {len(articles_with_images)} articles with valid images")

        # Apply category filter if specified
        if category and category.lower() != 'top':
            filtered_by_category = []
            category_lower = category.lower()

            # Enhanced category filtering based on multiple criteria
            for item in articles_with_images:
                item_matches_category = False

                # Check if item has a category field that matches
                item_category = item.get('category', '').lower()
                if item_category == category_lower:
                    item_matches_category = True

                # Check source-based category matching
                source_name = item.get('source', '').lower()
                if not item_matches_category:
                    if category_lower == 'technology':
                        tech_keywords = ['tech', 'technology', 'techcrunch', 'wired', 'verge', 'ars technica',
                                         'engadget']
                        item_matches_category = any(keyword in source_name for keyword in tech_keywords)
                    elif category_lower == 'sports':
                        sports_keywords = ['espn', 'sports', 'athletic', 'sport', 'nfl', 'nba', 'cricket']
                        item_matches_category = any(keyword in source_name for keyword in sports_keywords)
                    elif category_lower == 'business':
                        business_keywords = ['business', 'financial', 'bloomberg', 'reuters', 'wsj', 'fortune',
                                             'economic']
                        item_matches_category = any(keyword in source_name for keyword in business_keywords)
                    elif category_lower == 'health':
                        health_keywords = ['health', 'medical', 'medicine', 'wellness', 'healthcare']
                        item_matches_category = any(keyword in source_name for keyword in health_keywords)
                    elif category_lower == 'entertainment':
                        entertainment_keywords = ['entertainment', 'hollywood', 'variety', 'tmz', 'celebrity']
                        item_matches_category = any(keyword in source_name for keyword in entertainment_keywords)
                    elif category_lower == 'science':
                        science_keywords = ['science', 'scientific', 'nature', 'research', 'physics', 'biology', 'space', 'tech', 'lab', 'research']
                        item_matches_category = any(keyword in source_name for keyword in science_keywords)

                # Check title and content for category keywords if still no match
                if not item_matches_category:
                    title = item.get('title', '').lower()
                    summary = item.get('summary', '').lower()
                    content_to_check = f"{title} {summary}"

                    if category_lower == 'technology':
                        tech_content_keywords = ['technology', 'tech', 'software', 'app', 'digital', 'ai',
                                                 'artificial intelligence', 'computer', 'internet']
                        item_matches_category = any(keyword in content_to_check for keyword in tech_content_keywords)
                    elif category_lower == 'sports':
                        sports_content_keywords = ['sports', 'football', 'basketball', 'cricket', 'tennis', 'soccer',
                                                   'game', 'match', 'championship']
                        item_matches_category = any(keyword in content_to_check for keyword in sports_content_keywords)
                    elif category_lower == 'business':
                        business_content_keywords = ['business', 'economy', 'financial', 'money', 'market', 'stock',
                                                     'company', 'corporate']
                        item_matches_category = any(
                            keyword in content_to_check for keyword in business_content_keywords)
                    elif category_lower == 'health':
                        health_content_keywords = ['health', 'medical', 'medicine', 'doctor', 'hospital', 'disease',
                                                   'treatment', 'patient']
                        item_matches_category = any(keyword in content_to_check for keyword in health_content_keywords)
                    elif category_lower == 'entertainment':
                        entertainment_content_keywords = ['entertainment', 'movie', 'film', 'actor', 'actress',
                                                          'celebrity', 'music', 'concert']
                        item_matches_category = any(
                            keyword in content_to_check for keyword in entertainment_content_keywords)
                    elif category_lower == 'science':
                        science_content_keywords = ['science', 'research', 'study', 'discovery', 'experiment',
                                                    'scientist', 'physics', 'biology']
                        item_matches_category = any(keyword in content_to_check for keyword in science_content_keywords)

                if item_matches_category:
                    filtered_by_category.append(item)

            articles_with_images = filtered_by_category
            logger.debug(f"After category filtering ({category}): {len(articles_with_images)} articles")

        # Apply source filter if specified
        if source:
            articles_with_images = [
                item for item in articles_with_images
                if source.lower() in item.get('source', '').lower()
            ]
            logger.debug(f"After source filtering: {len(articles_with_images)} articles")

        # Apply pagination
        offset = (page - 1) * limit
        paginated_items = articles_with_images[offset:offset + limit]

        # Enhance news items
        enhanced_items = []
        for item in paginated_items:
            enhanced_item = enhance_news_item(item)
            enhanced_items.append(enhanced_item)

        logger.debug(f"Retrieved {len(enhanced_items)} news items for page {page}")

        return {
            "news": enhanced_items,
            "count": len(enhanced_items),
            "page": page,
            "limit": limit,
            "has_more": len(articles_with_images) > offset + limit,
            "total_available": len(articles_with_images),
            "category": category,
            "source_filter": source,
            "total_with_images": len(articles_with_images)
        }

    except Exception as e:
        logger.error("Error in /api/news endpoint:", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


def enhance_news_item(item: dict) -> dict:
    """Enhance news item with better image handling and formatting"""
    enhanced = item.copy()

    # Improve image URL handling - only keep if valid
    image_url = item.get('image_url')
    if is_valid_image_url(image_url):
        # Validate and fix image URL
        if not image_url.startswith(('http://', 'https://')):
            if image_url.startswith('//'):
                enhanced['image_url'] = f"https:{image_url}"
            else:
                enhanced['image_url'] = f"https://{image_url}"
        else:
            enhanced['image_url'] = image_url
    else:
        # Don't include items without valid images
        enhanced['image_url'] = None

    # Ensure required fields exist
    enhanced['id'] = item.get('id', item.get('url_hash', str(hash(item.get('url', '')))))
    enhanced['description'] = item.get('summary', item.get('content', 'No description available')[:200])

    # Format publish date
    pub_date = item.get('published_date')
    if pub_date:
        try:
            if isinstance(pub_date, str):
                enhanced['publishedAt'] = pub_date
            else:
                enhanced['publishedAt'] = pub_date.isoformat()
        except:
            enhanced['publishedAt'] = datetime.now().isoformat()
    else:
        enhanced['publishedAt'] = datetime.now().isoformat()

    return enhanced


@app.get("/api/news/category/{category}")
async def get_news_by_category(
        category: str,
        limit: int = Query(default=20, ge=1, le=100),
        page: int = Query(default=1, ge=1)
):
    """Get news by specific category - only returns articles with valid images"""
    try:
        # Use the main news endpoint with category filter
        return await get_news(limit=limit, page=page, category=category)
    except Exception as e:
        logger.error(f"Error fetching news for category {category}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/news/sources")
async def get_news_sources():
    """Get list of available news sources"""
    try:
        from news_fetcher import RSSFeedFetcher

        rss_sources = list(RSSFeedFetcher.RSS_FEEDS.keys())

        return {
            "rss_sources": rss_sources,
            "news_api_available": bool(NEWS_API_KEY),
            "total_sources": len(rss_sources),
            "categories": list(CATEGORY_MAPPING.keys())
        }
    except Exception as e:
        logger.error("Error getting news sources:", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/scheduler/status")
async def scheduler_status():
    """Get current scheduler status"""
    global scheduler, background_task

    is_running = background_task and not background_task.done() if background_task else False

    return {
        "scheduler_initialized": scheduler is not None,
        "is_running": is_running,
        "news_api_configured": bool(NEWS_API_KEY),
        "task_status": str(background_task._state) if background_task else "No task"
    }


@app.get("/debug/firestore")
async def debug_firestore():
    """Debug endpoint for Firestore connection"""
    try:
        from firestore import db, collection_name

        # Get collection info
        docs = list(db.collection(collection_name).stream())
        doc_count = len(docs)

        sample_docs = []
        for doc in docs[:3]:  # First 3 docs
            sample_docs.append({"id": doc.id, "data": doc.to_dict()})

        return {
            "collection_name": collection_name,
            "document_count": doc_count,
            "sample_documents": sample_docs,
            "credentials_path": os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "Not set")
        }
    except Exception as e:
        logger.error("Error in debug endpoint:", exc_info=True)
        return {"error": str(e), "type": str(type(e))}


@app.get("/")
async def root():
    """API root endpoint"""
    logger.info("Root endpoint accessed successfully")
    return {
        "message": "Welcome to PulseNews API",
        "version": "2.0.0",
        "status": "running",
        "timestamp": datetime.now().isoformat(),
        "endpoints": {
            "news": "/api/news - Get latest news with pagination (images only)",
            "news_by_category": "/api/news/category/{category} - Get news by category (images only)",
            "manual_scrape": "/scrape-and-summarize - Scrape single URL",
            "start_auto_fetch": "/start-news-fetching - Start automated fetching",
            "stop_auto_fetch": "/stop-news-fetching - Stop automated fetching",
            "fetch_once": "/fetch-news-once - Manual fetch cycle",
            "sources": "/news/sources - Available news sources",
            "scheduler_status": "/scheduler/status - Check scheduler status"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0"
    }


# Add this to run the server
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8090, reload=True)