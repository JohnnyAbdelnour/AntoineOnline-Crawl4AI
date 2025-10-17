import os
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
import ollama
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI()

# Get Supabase and Ollama credentials from environment variables
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama2")
PRODUCTS_TABLE_NAME = os.environ.get("PRODUCTS_TABLE_NAME", "products")

# Initialize Supabase client
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Check for Ollama Host
if not OLLAMA_HOST:
    raise ValueError("The OLLAMA_HOST environment variable must be set.")

# Initialize Ollama client
# Note: The Ollama Python library typically connects to a running Ollama instance.
# The user needs to provide the host URL for their Ollama service.
client = ollama.Client(host=OLLAMA_HOST)

# HTML for the web form
html_form = """
<!DOCTYPE html>
<html>
<head>
    <title>AI Agent</title>
</head>
<body>
    <h1>Ask the AI Agent</h1>
    <form action="/" method="post">
        <input type="text" name="question" style="width: 300px;" />
        <button type="submit">Ask</button>
    </form>
    <h2>Answer:</h2>
    <p>{response}</p>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Display the form."""
    return html_form.format(response="")

@app.post("/", response_class=HTMLResponse)
async def ask_agent(question: str = Form(...)):
    """Handle the form submission and respond to the user's question."""
    try:
        # Check if Supabase client is initialized
        if not supabase:
            return html_form.format(response="Supabase client is not initialized. Please check your environment variables.")

        # Fetch product data from Supabase
        response = supabase.table(PRODUCTS_TABLE_NAME).select("*").execute()
        products = response.data

        # Check if we got any products
        if not products:
            return html_form.format(response="No product data found in the database.")

        # Prepare the context for the LLM
        context = " ".join([f"Product: {p['name']}, Price: {p['price']}, Description: {p['description']}" for p in products])

        # Create a prompt for the LLM
        prompt = f"Context: {context}\\n\\nQuestion: {question}\\n\\nAnswer:"

        # Get the response from the LLM
        response = client.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that answers questions based on the provided context about e-commerce products."},
                {"role": "user", "content": prompt}
            ]
        )
        answer = response['message']['content']

        return html_form.format(response=answer)

    except Exception as e:
        return html_form.format(response=f"An error occurred: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)