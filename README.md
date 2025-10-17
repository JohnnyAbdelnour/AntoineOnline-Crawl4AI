# AntoineOnline-Crawl4AI

This script, `crawl_docs_FAST.py`, is a web crawler designed to fetch documentation from a specified sitemap and store the content in a Supabase database.

## Setup

1.  **Install Dependencies:**
    Install the required Python libraries using the `requirements.txt` file:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Create Environment File:**
    Create a file named `.env` in the root directory of the project. This file will store your Supabase credentials.

3.  **Add Supabase Credentials:**
    Add your Supabase project URL and anon key to the `.env` file as follows:
    ```
    SUPABASE_URL="https://hgethecbuzslslclgsyz.supabase.co"
    SUPABASE_KEY="YOUR_SUPABASE_ANON_KEY"
    ```
    Replace `"YOUR_SUPABASE_ANON_KEY"` with the anon key you provided.

## Usage

Once the setup is complete, you can run the script from your terminal:

```bash
python crawl_docs_FAST.py
```