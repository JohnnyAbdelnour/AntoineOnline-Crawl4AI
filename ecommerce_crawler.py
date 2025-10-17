import os
import sys
import psutil
import asyncio
from supabase import create_client, Client
from dotenv import load_dotenv

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
SUPABASE_TABLE_NAME = os.environ.get("SUPABASE_TABLE_NAME", "Data")

__location__ = os.path.dirname(os.path.abspath(__file__))
__output__ = os.path.join(__location__, "output")

# Append parent directory to system path
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(parent_dir)

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from crawl4ai.deep_crawling import BFSDeepCrawlStrategy
from crawl4ai.deep_crawling.filters import FilterChain, URLPatternFilter

async def crawl_ecommerce_site():
    print("\n=== Deep Crawling E-commerce Site with Streaming, Filtering, and Memory Check ===")

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

    # URL filtering to focus on products and categories.
    # Customize these patterns to match the URL structure of your target e-commerce site.
    filter_chain = FilterChain([
        URLPatternFilter(
            patterns=["*/cart", "*/account", "*/login"],  # Exclude irrelevant pages
            reverse=True
        ),
        URLPatternFilter(
            patterns=["*/product/*", "*/category/*"]  # Allow product and category pages
        )
    ])

    # Deep crawling strategy
    # - max_depth=0 means unlimited depth.
    # - max_pages is a safeguard to prevent crawling more than 1.1M pages.
    # - include_external=False keeps the crawler on the target domain.
    deep_crawl_strategy = BFSDeepCrawlStrategy(
        max_depth=0,  # Unlimited depth
        max_pages=1100000,
        include_external=False,
        filter_chain=filter_chain,
    )

    crawl_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        deep_crawl_strategy=deep_crawl_strategy,
        stream=True,  # Enable streaming
    )

    # Create the crawler instance
    crawler = AsyncWebCrawler(config=browser_config)
    await crawler.start()

    success_count = 0
    fail_count = 0
    try:
        log_memory(prefix="Before crawl: ")

        async for result in await crawler.arun(url=ECOMMERCE_TARGET_URL, config=crawl_config):
            if result.success:
                success_count += 1
                try:
                    client = get_supabase_client()
                    data, count = client.table(SUPABASE_TABLE_NAME).insert({"url": result.url, "content": result.markdown}).execute()
                except Exception as e:
                    print(f"Error inserting data for {result.url}: {e}")
            else:
                fail_count += 1
                print(f"Error crawling {result.url}: {result.error_message}")

            if (success_count + fail_count) % 100 == 0:
                log_memory(prefix=f"After {success_count + fail_count} pages: ")

        print(f"\nSummary:")
        print(f"  - Successfully crawled: {success_count}")
        print(f"  - Failed: {fail_count}")

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

    print(f"Starting to crawl {ECOMMERCE_TARGET_URL}")
    await crawl_ecommerce_site()

if __name__ == "__main__":
    asyncio.run(main())