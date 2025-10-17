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
PRODUCT_URL_PATTERN = os.environ.get("PRODUCT_URL_PATTERN", "/product/")
CSS_SELECTOR_BASE = os.environ.get("CSS_SELECTOR_BASE", "body")
CSS_SELECTOR_NAME = os.environ.get("CSS_SELECTOR_NAME", "h1.title")
CSS_SELECTOR_PRICE = os.environ.get("CSS_SELECTOR_PRICE", "div.product-price")
CSS_SELECTOR_DESCRIPTION = os.environ.get("CSS_SELECTOR_DESCRIPTION", "h2.text")
CSS_SELECTOR_IMAGE_URL = os.environ.get("CSS_SELECTOR_IMAGE_URL", "div.main-image img")
URLS_FILE = "product_urls.txt"

__location__ = os.path.dirname(os.path.abspath(__file__))
__output__ = os.path.join(__location__, "output")

# Append parent directory to system path
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(parent_dir)

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode, JsonCssExtractionStrategy
from crawl4ai.deep_crawling import BFSDeepCrawlStrategy
from crawl4ai.deep_crawling.filters import FilterChain, URLPatternFilter

# Pydantic model for product data extraction
class Product(BaseModel):
    name: str = Field(..., description="The name of the product")
    price: float = Field(..., description="The price of the product")
    description: Optional[str] = Field(None, description="The description of the product")
    image_url: Optional[str] = Field(None, description="The URL of the product image")

async def discover_product_urls():
    print("\n=== Discovering Product URLs ===")

    # We'll keep track of peak memory usage across all tasks
    peak_memory = 0
    process = psutil.Process(os.getpid())

    def log_memory(prefix: str = ""):
        nonlocal peak_memory
        current_mem = process.memory_info().rss  # in bytes
        if current_mem > peak_memory:
            peak_memory = current_mem
        print(f"{prefix} Current Memory: {current_mem // (1024 * 1024)} MB, Peak: {peak_memory // (1024 * 1024)} MB")

    # Minimal browser config
    browser_config = BrowserConfig(
        headless=True,
        verbose=False,
        extra_args=["--disable-gpu", "--disable-dev-shm-usage", "--no-sandbox"],
    )

    # URL filtering to focus on valid HTTP/HTTPS links
    filter_chain = FilterChain([
        URLPatternFilter(
            patterns=["http://*", "https://*"],
        )
    ])

    # Deep crawling strategy
    deep_crawl_strategy = BFSDeepCrawlStrategy(
        max_depth=10,  # Limit depth to 10 to avoid infinite loops, but still get deep enough
        max_pages=1100000,
        include_external=False,
        filter_chain=filter_chain,
    )

    crawl_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        deep_crawl_strategy=deep_crawl_strategy,
        stream=True,
        page_timeout=120000,
    )

    # Create the crawler instance
    crawler = AsyncWebCrawler(config=browser_config)
    await crawler.start()

    product_urls = set()
    try:
        log_memory(prefix="Before crawl: ")

        async for result in await crawler.arun(url=ECOMMERCE_TARGET_URL, config=crawl_config):
            if result.success and PRODUCT_URL_PATTERN in result.url:
                product_urls.add(result.url)

        print(f"\nFound {len(product_urls)} unique product URLs.")

        with open(URLS_FILE, "w") as f:
            for url in product_urls:
                f.write(f"{url}\n")
        print(f"Saved product URLs to {URLS_FILE}")

    finally:
        print("\nClosing crawler...")
        await crawler.close()
        # Final memory log
        log_memory(prefix="Final: ")
        print(f"\nPeak memory usage (MB): {peak_memory // (1024 * 1024)}")

async def extract_product_data():
    print("\n=== Extracting Product Data ===")

    if not os.path.exists(URLS_FILE):
        print(f"Error: {URLS_FILE} not found. Please run the 'discover' mode first.")
        return

    with open(URLS_FILE, "r") as f:
        urls = [line.strip() for line in f.readlines()]

    print(f"Found {len(urls)} URLs to process.")

    # CSS selectors for product data
    extraction_schema = {
        "baseSelector": CSS_SELECTOR_BASE,
        "fields": [
            {"name": "name", "selector": CSS_SELECTOR_NAME, "type": "text"},
            {"name": "price", "selector": CSS_SELECTOR_PRICE, "type": "text"},
            {"name": "description", "selector": CSS_SELECTOR_DESCRIPTION, "type": "text"},
            {"name": "image_url", "selector": CSS_SELECTOR_IMAGE_URL, "type": "attribute", "attribute": "src"}
        ]
    }

    # Extraction strategy
    extraction_strategy = JsonCssExtractionStrategy(schema=extraction_schema)

    crawl_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        extraction_strategy=extraction_strategy,
    )

    # Create the crawler instance
    crawler = AsyncWebCrawler()
    await crawler.start()

    products_batch = []
    batch_size = 50
    success_count = 0
    fail_count = 0
    try:
        for url in urls:
            result = await crawler.arun(url=url, config=crawl_config)
            if result.success and result.extracted_content:
                try:
                    # Validate the extracted data against the Pydantic model
                    product_data = json.loads(result.extracted_content)[0]
                    # The price is extracted as a string like "3.57 USD", so we need to parse it
                    if 'price' in product_data and isinstance(product_data['price'], str):
                        product_data['price'] = float(product_data['price'].replace('USD', '').strip())

                    validated_product = Product(**product_data)
                    product_data_validated = validated_product.dict()
                    product_data_validated['url'] = url
                    products_batch.append(product_data_validated)

                    if len(products_batch) >= batch_size:
                        client = get_supabase_client()
                        data, count = client.table(PRODUCTS_TABLE_NAME).insert(products_batch).execute()
                        success_count += len(products_batch)
                        print(f"Inserted batch of {len(products_batch)} products.")
                        products_batch = []

                except (json.JSONDecodeError, IndexError, ValidationError, ValueError) as e:
                    print(f"Error validating or parsing extracted content for {url}: {e}")
                    fail_count += 1

            elif not result.success:
                print(f"Error crawling {url}: {result.error_message}")
                fail_count += 1

        # Insert any remaining products in the last batch
        if products_batch:
            client = get_supabase_client()
            data, count = client.table(PRODUCTS_TABLE_NAME).insert(products_batch).execute()
            success_count += len(products_batch)
            print(f"Inserted final batch of {len(products_batch)} products.")

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
        await extract_product_data()


if __name__ == "__main__":
    asyncio.run(main())