import os
import sys
import psutil
import asyncio
import json
import argparse
from supabase import create_client, Client
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError
from typing import Optional, List

load_dotenv()

# Supabase connection details
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = None

def get_supabase_client():
    global supabase
    if supabase is None:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    return supabase

# E-commerce target URL
ECOMMERCE_TARGET_URL = os.environ.get("ECOMMERCE_TARGET_URL")
PRODUCTS_TABLE_NAME = os.environ.get("PRODUCTS_TABLE_NAME", "products")
PRODUCT_URL_PATTERN = os.environ.get("PRODUCT_URL_PATTERN", "/events/")
URLS_FILE = "product_urls.txt"

__location__ = os.path.dirname(os.path.abspath(__file__))
__output__ = os.path.join(__location__, "output")

# Append parent directory to system path
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(parent_dir)

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode, JsonCssExtractionStrategy
from crawl4ai.deep_crawling import BFSDeepCrawlStrategy
from crawl4ai.deep_crawling.filters import FilterChain, URLPatternFilter
from bs4 import BeautifulSoup

# Pydantic model for event data extraction
class Category(BaseModel):
    category_name: str = Field(..., description="The name of the category")
    category_price: float = Field(..., description="The price of the category")

class Event(BaseModel):
    event_name: str = Field(..., description="The name of the event")
    categories: List[Category] = Field(..., description="A list of categories for the event")
    description: Optional[str] = Field(None, description="The description of the event")
    image_url: Optional[str] = Field(None, description="The URL of the event image")
    organizer_name: Optional[str] = Field(None, description="The name of the event organizer")

async def discover_product_urls():
    print("\n=== Discovering Product URLs ===")
    browser_config = BrowserConfig(
        headless=True,
        verbose=False,
        extra_args=["--disable-gpu", "--disable-dev-shm-usage", "--no-sandbox"],
    )
    crawler = AsyncWebCrawler(config=browser_config)
    await crawler.start()
    result = await crawler.arun(url=ECOMMERCE_TARGET_URL, config=CrawlerRunConfig(cache_mode=CacheMode.BYPASS))
    await crawler.close()

    if not result.success:
        print(f"Error crawling {ECOMMERCE_TARGET_URL}: {result.error_message}")
        return

    soup = BeautifulSoup(result.html, 'html.parser')
    script_tag = soup.find('script', {'id': '__NEXT_DATA__'})
    if not script_tag:
        print("Could not find the __NEXT_DATA__ script tag.")
        return

    json_data = json.loads(script_tag.string)
    product_urls = set()

    base_url = ECOMMERCE_TARGET_URL.strip('/')

    # Correctly navigate the JSON structure to find event items
    try:
        blocks = json_data.get('props', {}).get('pageProps', {}).get('homepageData', {}).get('blocks', [])
        for block in blocks:
            if 'items' in block:
                for item in block['items']:
                    if 'slug' in item and 'id' in item:
                        # Construct the full URL, ensuring no double slashes
                        product_url_path = PRODUCT_URL_PATTERN.strip('/')
                        event_path = f"/{product_url_path}/{item['id']}/{item['slug']}"
                        full_url = f"{base_url}{event_path}"
                        product_urls.add(full_url)
    except (KeyError, TypeError) as e:
        print(f"Error navigating JSON data: {e}")
        return

    print(f"\nFound {len(product_urls)} unique product URLs.")
    with open(URLS_FILE, "w") as f:
        for url in product_urls:
            f.write(f"{url}\n")
    print(f"Saved product URLs to {URLS_FILE}")

async def extract_event_data():
    print("\n=== Extracting Event Data ===")

    if not os.path.exists(URLS_FILE):
        print(f"Error: {URLS_FILE} not found. Please run the 'discover' mode first.")
        return

    with open(URLS_FILE, "r") as f:
        urls = [line.strip() for line in f.readlines() if line.strip()]

    print(f"Found {len(urls)} URLs to process.")

    crawler = AsyncWebCrawler()
    await crawler.start()

    events_batch = []
    batch_size = 50
    success_count = 0
    fail_count = 0
    try:
        for url in urls:
            result = await crawler.arun(url=url, config=CrawlerRunConfig(cache_mode=CacheMode.BYPASS))
            if result.success and result.html:
                try:
                    soup = BeautifulSoup(result.html, 'html.parser')
                    script_tag = soup.find('script', {'id': '__NEXT_DATA__'})
                    if not script_tag:
                        print(f"Warning: No __NEXT_DATA__ script tag found for {url}, skipping.")
                        fail_count += 1
                        continue

                    json_data = json.loads(script_tag.string)
                    product_data = json_data.get('props', {}).get('pageProps', {}).get('product', {})

                    event_name = product_data.get('name')
                    description = product_data.get('text')
                    image_url = product_data.get('media', {}).get('image')
                    organizer_name = product_data.get('organizer', {}).get('name')

                    categories = []
                    for cat in product_data.get('categories', []):
                        category_name = cat.get('name')
                        category_price = cat.get('price', {}).get('USD', {}).get('amount')
                        if category_name and category_price is not None:
                            categories.append({"category_name": category_name, "category_price": category_price})

                    if not event_name or not categories:
                        print(f"Warning: Missing essential data for {url}, skipping.")
                        fail_count += 1
                        continue

                    event_data = {
                        "event_name": event_name,
                        "categories": categories,
                        "description": description,
                        "image_url": image_url,
                        "organizer_name": organizer_name
                    }

                    validated_event = Event(**event_data)
                    event_data_validated = validated_event.model_dump()
                    event_data_validated['url'] = url
                    events_batch.append(event_data_validated)

                    if len(events_batch) >= batch_size:
                        client = get_supabase_client()
                        unique_events = {p['event_name']: p for p in events_batch}.values()
                        data, count = client.table(PRODUCTS_TABLE_NAME).upsert(list(unique_events), on_conflict='event_name').execute()
                        success_count += len(unique_events)
                        print(f"Upserted batch of {len(unique_events)} events.")
                        events_batch = []

                except (json.JSONDecodeError, KeyError, ValidationError) as e:
                    print(f"Error processing data for {url}: {e}")
                    fail_count += 1
            elif not result.success:
                print(f"Error crawling {url}: {result.error_message}")
                fail_count += 1

        if events_batch:
            client = get_supabase_client()
            unique_events = {p['event_name']: p for p in events_batch}.values()
            data, count = client.table(PRODUCTS_TABLE_NAME).upsert(list(unique_events), on_conflict='event_name').execute()
            success_count += len(unique_events)
            print(f"Upserted final batch of {len(unique_events)} events.")

        print(f"\nSummary:")
        print(f"  - Successfully extracted and stored: {success_count}")
        print(f"  - Failed or no data: {fail_count}")

    finally:
        print("\nClosing crawler...")
        await crawler.close()

async def main():
    parser = argparse.ArgumentParser(description="E-commerce product crawler and extractor.")
    parser.add_argument("mode", choices=["discover", "extract"], help="The mode to run the script in.")
    args = parser.parse_args()

    if args.mode == "discover":
        if not ECOMMERCE_TARGET_URL:
            print("ECOMMERCE_TARGET_URL environment variable is not set.")
            return
        await discover_product_urls()
    elif args.mode == "extract":
        await extract_event_data()


if __name__ == "__main__":
    asyncio.run(main())