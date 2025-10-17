import os
import sys
import psutil
import asyncio
import json
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
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

__location__ = os.path.dirname(os.path.abspath(__file__))
__output__ = os.path.join(__location__, "output")

# Append parent directory to system path
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(parent_dir)

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode, LLMConfig, LLMExtractionStrategy
from crawl4ai.deep_crawling import BFSDeepCrawlStrategy
from crawl4ai.deep_crawling.filters import FilterChain, URLPatternFilter

# Pydantic model for product data extraction
class Product(BaseModel):
    name: str = Field(..., description="The name of the product")
    price: float = Field(..., description="The price of the product")
    description: Optional[str] = Field(None, description="The description of the product")
    sku: Optional[str] = Field(None, description="The SKU of the product")
    image_url: Optional[str] = Field(None, description="The URL of the product image")

async def crawl_and_extract():
    print("\n=== Deep Crawling and Extracting Products with Streaming and Batch Inserts ===")

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

    # LLM configuration
    llm_config = LLMConfig(
        provider="openai/gpt-4-turbo",
        api_token=OPENAI_API_KEY,
        temperature=0.0,
    )

    # Extraction strategy
    extraction_strategy = LLMExtractionStrategy(
        llm_config=llm_config,
        pydantic_model=Product,
        max_items=1,
    )

    # URL filtering to focus on product and category pages
    filter_chain = FilterChain([
        URLPatternFilter(
            patterns=["*/product/*", "*/category/*"],
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
        extraction_strategy=extraction_strategy,
        stream=True,
    )

    # Create the crawler instance
    crawler = AsyncWebCrawler(config=browser_config)
    await crawler.start()

    products_batch = []
    batch_size = 50
    success_count = 0
    fail_count = 0
    try:
        log_memory(prefix="Before crawl: ")

        async for result in await crawler.arun(url=ECOMMERCE_TARGET_URL, config=crawl_config):
            if result.success and result.extracted_content:
                try:
                    # Validate the extracted data against the Pydantic model
                    validated_product = Product(**json.loads(result.extracted_content)[0])
                    product_data = validated_product.dict()
                    product_data['url'] = result.url
                    products_batch.append(product_data)

                    if len(products_batch) >= batch_size:
                        client = get_supabase_client()
                        data, count = client.table(PRODUCTS_TABLE_NAME).insert(products_batch).execute()
                        success_count += len(products_batch)
                        print(f"Inserted batch of {len(products_batch)} products.")
                        products_batch = []

                except (json.JSONDecodeError, IndexError, ValidationError) as e:
                    print(f"Error validating or parsing extracted content for {result.url}: {e}")
                    fail_count += 1

            elif not result.success:
                print(f"Error crawling {result.url}: {result.error_message}")
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
        # Final memory log
        log_memory(prefix="Final: ")
        print(f"\nPeak memory usage (MB): {peak_memory // (1024 * 1024)}")

async def main():
    if not ECOMMERCE_TARGET_URL:
        print("ECOMMERCE_TARGET_URL environment variable is not set.")
        return
    if not OPENAI_API_KEY:
        print("OPENAI_API_KEY environment variable is not set.")
        return

    await crawl_and_extract()


if __name__ == "__main__":
    asyncio.run(main())