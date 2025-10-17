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
OLLAMA_API_KEY = os.environ.get("OLLAMA_API_KEY")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gpt-oss:20b-cloud")
PRODUCTS_TABLE_NAME = os.environ.get("PRODUCTS_TABLE_NAME", "products")

# Initialize Supabase client
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Check for Ollama API key
if not OLLAMA_API_KEY:
    raise ValueError("The OLLAMA_API_KEY environment variable must be set for Ollama Cloud.")

# Initialize Ollama client for Cloud service
client = ollama.Client(
    host="https://ollama.com",
    headers={'Authorization': f'Bearer {OLLAMA_API_KEY}'}
)

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
        prompt = f"Context: {context}\\n\\n<customer_query>{question}</customer_query>"

        # Get the response from the LLM
        response = client.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": """You are Najjar Online's dedicated customer support AI agent. Your primary responsibility is to provide accurate and professional product information by querying the Supabase database and formatting responses appropriately.

INPUT:
<customer_query>[[customer_query]]</customer_query>

Follow this systematic process for every customer interaction:

1. QUERY ANALYSIS
- Extract key product details from the customer query
- Identify relevant search parameters
- Note any missing information
- Develop an efficient database search strategy

2. DATABASE OPERATIONS
- Query the products table using provided configuration
- Extract all relevant product information
- Document any information gaps

3. RESPONSE CONSTRUCTION
Format your response using this markdown structure:
```markdown
[Professional greeting]
[Direct answer addressing the query]
[Detailed product information from database]
[Relevant additional context]
[Professional closing]
```

4. SPECIAL SCENARIOS

When Information is Missing:
- Request specific missing details
- Provide an example of required information
- Confirm Arabeezi text acceptance

When Information is Unavailable:
- Offer professional apology
- Explain the limitation
- Suggest alternative assistance

For Out-of-Scope Requests:
- Provide clear, professional explanation
- Direct to appropriate resources

MANDATORY REQUIREMENTS:
1. Only provide database-verified information
2. Maintain consistently professional language
3. Use specified markdown formatting
4. Ensure 100% information accuracy
5. Keep responses clear and concise
6. Focus on product-specific details
7. Accept and process Arabeezi text input

VERIFICATION CHECKLIST:
Before sending any response, verify:
- Database information accuracy
- Complete query address
- Professional tone maintenance
- Correct markdown formatting
- Response completeness

Remember: Every response must be:
- Verified against the database
- Professionally formatted
- Clear and helpful
- Accurate and complete

Never provide information that hasn't been verified through the database. Always maintain a professional, helpful tone while ensuring accuracy and clarity in all communications.   Jump Logic/Success Prompt: When the response is relevant to the user's query, directly addresses their intent, or appropriately moves the conversation forward—such as by asking clarifying questions or requesting additional information—it should offer a clear, complete, and contextually appropriate resolution. If further action is required, the response includes timely and relevant follow-up such as next steps, useful links, or confirmations. Throughout the exchange, the assistant remains consistent with prior context, handles any limitations gracefully, and ensures that the user’s needs are met or clearly identifies what is required to proceed."""},
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