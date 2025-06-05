import os
from google.cloud import firestore
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import hashlib

# Point to the downloaded service account key file
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "../credentials/firebase-adminsdk.json"

db = firestore.Client()
collection_name = "news_summaries"


async def add_news_item(data: dict) -> bool:
    """Add a news item to Firestore with duplicate checking"""
    try:
        # Create URL hash for duplicate detection
        url_hash = hashlib.md5(data['url'].encode()).hexdigest()
        data['url_hash'] = url_hash

        # Check if this URL already exists
        existing = db.collection(collection_name) \
            .where("url_hash", "==", url_hash) \
            .limit(1) \
            .stream()

        if list(existing):
            print(f"Article already exists: {data['title'][:50]}...")
            return False

        # Add timestamp if not present
        if 'created_at' not in data:
            data['created_at'] = datetime.now().isoformat()

        # Add the document
        db.collection(collection_name).add(data)
        return True

    except Exception as e:
        print(f"Error adding news item: {e}")
        return False


async def fetch_news_items(limit: int = 20, source: str = None, hours_back: int = None) -> List[Dict]:
    """Fetch news items with optional filtering"""
    try:
        query = db.collection(collection_name)

        # Filter by source if specified
        if source:
            query = query.where("source", "==", source)

        # Filter by time if specified
        if hours_back:
            cutoff_time = datetime.now() - timedelta(hours=hours_back)
            query = query.where("created_at", ">=", cutoff_time.isoformat())

        # Order by created date and limit
        docs = query.order_by("created_at", direction=firestore.Query.DESCENDING) \
            .limit(limit) \
            .stream()

        return [{"id": doc.id, **doc.to_dict()} for doc in docs]

    except Exception as e:
        print(f"Error fetching news items: {e}")
        return []


async def get_news_by_source(source: str, limit: int = 10) -> List[Dict]:
    """Get news items from a specific source"""
    return await fetch_news_items(limit=limit, source=source)


async def get_recent_news(hours: int = 24, limit: int = 50) -> List[Dict]:
    """Get news items from the last N hours"""
    return await fetch_news_items(limit=limit, hours_back=hours)


async def search_news(keyword: str, limit: int = 20) -> List[Dict]:
    """Search news items by keyword in title or summary"""
    try:
        # Firestore doesn't support full-text search, so we'll do basic filtering
        # For production, consider using Algolia or Elasticsearch
        all_docs = db.collection(collection_name) \
            .order_by("created_at", direction=firestore.Query.DESCENDING) \
            .limit(100) \
            .stream()

        keyword_lower = keyword.lower()
        matching_docs = []

        for doc in all_docs:
            doc_data = doc.to_dict()
            title = doc_data.get('title', '').lower()
            summary = doc_data.get('summary', '').lower()

            if keyword_lower in title or keyword_lower in summary:
                matching_docs.append({"id": doc.id, **doc_data})

                if len(matching_docs) >= limit:
                    break

        return matching_docs

    except Exception as e:
        print(f"Error searching news: {e}")
        return []


async def get_news_stats() -> Dict:
    """Get statistics about the news collection"""
    try:
        # Get total count
        all_docs = list(db.collection(collection_name).stream())
        total_count = len(all_docs)

        # Get count by source
        source_counts = {}
        recent_articles = 0
        cutoff_time = datetime.now() - timedelta(hours=24)

        for doc in all_docs:
            doc_data = doc.to_dict()

            # Count by source
            source = doc_data.get('source', 'Unknown')
            source_counts[source] = source_counts.get(source, 0) + 1

            # Count recent articles
            created_at = doc_data.get('created_at')
            if created_at:
                try:
                    created_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    if created_date > cutoff_time:
                        recent_articles += 1
                except:
                    pass

        return {
            "total_articles": total_count,
            "articles_last_24h": recent_articles,
            "sources": source_counts,
            "top_sources": sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        }

    except Exception as e:
        print(f"Error getting stats: {e}")
        return {}


async def cleanup_old_articles(days_old: int = 30) -> int:
    """Remove articles older than specified days"""
    try:
        cutoff_date = datetime.now() - timedelta(days=days_old)

        old_docs = db.collection(collection_name) \
            .where("created_at", "<", cutoff_date.isoformat()) \
            .stream()

        deleted_count = 0
        for doc in old_docs:
            doc.reference.delete()
            deleted_count += 1

        return deleted_count

    except Exception as e:
        print(f"Error cleaning up old articles: {e}")
        return 0


# Utility functions for the frontend
async def get_trending_topics(limit: int = 10) -> List[Dict]:
    """Get trending topics based on keyword frequency"""
    try:
        recent_docs = await get_recent_news(hours=24, limit=100)

        # Simple keyword extraction (for production, use proper NLP)
        word_counts = {}
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is',
                      'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
                      'could', 'should'}

        for doc in recent_docs:
            title = doc.get('title', '').lower()
            words = [word.strip('.,!?;:"()[]') for word in title.split()]

            for word in words:
                if len(word) > 3 and word not in stop_words:
                    word_counts[word] = word_counts.get(word, 0) + 1

        # Return top trending words
        trending = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)[:limit]
        return [{"keyword": word, "count": count} for word, count in trending]

    except Exception as e:
        print(f"Error getting trending topics: {e}")
        return []