# enhanced_scraper.py - Enhanced web scraping with better image extraction
import requests
from newspaper import Article
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re
from typing import Optional, List, Dict
import logging

logger = logging.getLogger(__name__)


class EnhancedArticle:
    """Enhanced article class with better image handling"""

    def __init__(self, url: str):
        self.url = url
        self.title = ""
        self.text = ""
        self.authors = []
        self.publish_date = None
        self.source_url = ""
        self.images = []
        self.top_image = ""
        self.meta_description = ""
        self.keywords = []

    def __repr__(self):
        return f"EnhancedArticle(title='{self.title[:50]}...', url='{self.url}')"


def scrape_article(url: str) -> EnhancedArticle:
    """Enhanced article scraping with better image extraction"""
    try:
        # Use newspaper3k as primary scraper
        article = Article(url)
        article.download()
        article.parse()

        # Create enhanced article object
        enhanced = EnhancedArticle(url)
        enhanced.title = article.title
        enhanced.text = article.text
        enhanced.authors = article.authors
        enhanced.publish_date = article.publish_date
        enhanced.source_url = article.source_url
        enhanced.meta_description = article.meta_description
        enhanced.keywords = article.keywords

        # Enhanced image extraction
        enhanced.images, enhanced.top_image = extract_images(url, article.html)

        # If newspaper didn't get a good image, try our enhanced method
        if not enhanced.top_image and article.top_image:
            enhanced.top_image = article.top_image

        return enhanced

    except Exception as e:
        logger.error(f"Error scraping article {url}: {e}")
        # Return minimal article object
        enhanced = EnhancedArticle(url)
        enhanced.title = "Error loading article"
        enhanced.text = f"Failed to scrape article: {str(e)}"
        return enhanced


def extract_images(url: str, html_content: str) -> tuple[List[str], str]:
    """Extract all images and determine the best top image"""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        base_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}"

        images = []
        potential_top_images = []

        # Find all img tags
        img_tags = soup.find_all('img')

        for img in img_tags:
            src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
            if not src:
                continue

            # Convert relative URLs to absolute
            if src.startswith('//'):
                src = f"https:{src}"
            elif src.startswith('/'):
                src = urljoin(base_url, src)
            elif not src.startswith('http'):
                src = urljoin(url, src)

            # Filter out small images, icons, etc.
            if is_valid_image(img, src):
                images.append(src)

                # Determine if this could be the main image
                if is_potential_top_image(img, src):
                    potential_top_images.append({
                        'url': src,
                        'score': calculate_image_score(img, src)
                    })

        # Also check for Open Graph and Twitter Card images
        og_image = get_meta_image(soup, 'og:image')
        twitter_image = get_meta_image(soup, 'twitter:image')

        if og_image:
            potential_top_images.append({'url': og_image, 'score': 100})
        if twitter_image:
            potential_top_images.append({'url': twitter_image, 'score': 90})

        # Select best top image
        top_image = ""
        if potential_top_images:
            best_image = max(potential_top_images, key=lambda x: x['score'])
            top_image = best_image['url']
        elif images:
            top_image = images[0]  # Fallback to first image
        logger.debug(f"Scraped meta_data: {article.meta_data}")
        logger.debug(f"Top image: {article.top_image}")
        logger.debug(f"Images: {list(article.images)[:3]}")

        return list(set(images)), top_image  # Remove duplicates

    except Exception as e:
        logger.error(f"Error extracting images from {url}: {e}")
        return [], ""


def is_valid_image(img_tag, src: str) -> bool:
    """Check if image is valid (not icon, not too small, etc.)"""
    try:
        # Skip common non-article images
        skip_patterns = [
            'icon', 'logo', 'avatar', 'profile', 'thumbnail',
            'ads', 'banner', 'header', 'footer', 'sidebar',
            'social', 'share', 'comment', 'widget'
        ]

        src_lower = src.lower()
        if any(pattern in src_lower for pattern in skip_patterns):
            return False

        # Check image dimensions if available
        width = img_tag.get('width')
        height = img_tag.get('height')

        if width and height:
            try:
                w, h = int(width), int(height)
                if w < 200 or h < 200:  # Skip small images
                    return False
            except ValueError:
                pass

        # Skip common icon file extensions
        if re.search(r'\.(ico|svg|gif)$', src_lower):
            return False

        return True

    except Exception:
        return False


def is_potential_top_image(img_tag, src: str) -> bool:
    """Check if image could be the main article image"""
    try:
        # Check for article-related classes or IDs
        article_indicators = [
            'article', 'content', 'main', 'hero', 'featured',
            'lead', 'primary', 'story', 'news'
        ]

        class_str = ' '.join(img_tag.get('class', [])).lower()
        id_str = img_tag.get('id', '').lower()
        alt_str = img_tag.get('alt', '').lower()

        # Higher score for images with article-related attributes
        return any(indicator in class_str or indicator in id_str or indicator in alt_str
                   for indicator in article_indicators)

    except Exception:
        return False


def calculate_image_score(img_tag, src: str) -> int:
    """Calculate a score for image relevance"""
    score = 0

    try:
        # Base score
        score += 10

        # Check dimensions
        width = img_tag.get('width')
        height = img_tag.get('height')

        if width and height:
            try:
                w, h = int(width), int(height)
                if w >= 400 and h >= 300:
                    score += 30
                elif w >= 300 and h >= 200:
                    score += 20
                elif w >= 200 and h >= 150:
                    score += 10
            except ValueError:
                pass

        # Check for article-related attributes
        class_str = ' '.join(img_tag.get('class', [])).lower()
        id_str = img_tag.get('id', '').lower()
        alt_str = img_tag.get('alt', '').lower()

        article_indicators = [
            'article', 'content', 'main', 'hero', 'featured',
            'lead', 'primary', 'story', 'news'
        ]

        for indicator in article_indicators:
            if indicator in class_str:
                score += 25
            if indicator in id_str:
                score += 20
            if indicator in alt_str:
                score += 15

        # Bonus for certain file types
        if src.lower().endswith(('.jpg', '.jpeg', '.png')):
            score += 5

        return score

    except Exception:
        return 0


def get_meta_image(soup, property_name: str) -> Optional[str]:
    """Extract image from meta tags"""
    try:
        meta_tag = soup.find('meta', property=property_name) or \
                   soup.find('meta', attrs={'name': property_name})

        if meta_tag:
            return meta_tag.get('content')
        return None

    except Exception:
        return None


def get_article_metadata(url: str) -> Dict:
    """Extract additional metadata from article"""
    try:
        response = requests.get(url, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        soup = BeautifulSoup(response.content, 'html.parser')

        metadata = {}

        # Extract Open Graph data
        og_tags = soup.find_all('meta', property=lambda x: x and x.startswith('og:'))
        for tag in og_tags:
            property_name = tag.get('property', '').replace('og:', '')
            content = tag.get('content', '')
            if property_name and content:
                metadata[f'og_{property_name}'] = content

        # Extract Twitter Card data
        twitter_tags = soup.find_all('meta', attrs={'name': lambda x: x and x.startswith('twitter:')})
        for tag in twitter_tags:
            name = tag.get('name', '').replace('twitter:', '')
            content = tag.get('content', '')
            if name and content:
                metadata[f'twitter_{name}'] = content

        # Extract other useful meta tags
        meta_tags = {
            'description': soup.find('meta', attrs={'name': 'description'}),
            'keywords': soup.find('meta', attrs={'name': 'keywords'}),
            'author': soup.find('meta', attrs={'name': 'author'}),
            'publish_date': soup.find('meta', property='article:published_time'),
        }

        for key, tag in meta_tags.items():
            if tag:
                metadata[key] = tag.get('content', '')

        return metadata

    except Exception as e:
        logger.error(f"Error extracting metadata from {url}: {e}")
        return {}


# For backward compatibility with your existing code
def scrape_article_simple(url: str) -> Article:
    """Simple scraping function for backward compatibility"""
    article = Article(url)
    article.download()
    article.parse()
    return article


if __name__ == "__main__":
    # Test the enhanced scraper
    test_url = "https://www.bbc.com/news"
    article = scrape_article(test_url)
    print(f"Title: {article.title}")
    print(f"Authors: {article.authors}")
    print(f"Top Image: {article.top_image}")
    print(f"Total Images: {len(article.images)}")
    print(f"Text Length: {len(article.text)}")