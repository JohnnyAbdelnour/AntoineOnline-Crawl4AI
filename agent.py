import os
import json
import uuid
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import ollama
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

# Get Supabase and Ollama credentials from environment variables
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_API_KEY = os.environ.get("OLLAMA_API_KEY")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama2")
PRODUCTS_TABLE_NAME = os.environ.get("PRODUCTS_TABLE_NAME", "products")

# Initialize Supabase client
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Initialize Ollama client
headers = {}
if OLLAMA_API_KEY:
    headers['Authorization'] = f'Bearer {OLLAMA_API_KEY}'
client = ollama.Client(host=OLLAMA_HOST, headers=headers)

# In-memory store for chat histories
chat_histories = {}

class ChatRequest(BaseModel):
    question: str
    session_id: str = None

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    with open("static/index.html") as f:
        return HTMLResponse(content=f.read(), status_code=200)

@app.post("/ask", response_class=JSONResponse)
async def ask(request: ChatRequest):
    """Handle the form submission and respond to the user's question."""
    try:
        session_id = request.session_id
        if not session_id or session_id not in chat_histories:
            session_id = str(uuid.uuid4())
            chat_histories[session_id] = []
            # Add system prompt for new sessions
            chat_histories[session_id].append({"role": "system", "content": """You are Najjar Online's dedicated customer support AI agent. Your primary responsibility is to provide accurate and professional product information by querying the Supabase database and formatting responses appropriately.

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

Never provide information that hasn't been verified through the database. Always maintain a professional, helpful tone while ensuring accuracy and clarity in all communications.   Jump Logic/Success Prompt: When the response is relevant to the user's query, directly addresses their intent, or appropriately moves the conversation forward—such as by asking clarifying questions or requesting additional information—it should offer a clear, complete, and contextually appropriate resolution. If further action is required, the response includes timely and relevant follow-up such as next steps, useful links, or confirmations. Throughout the exchange, the assistant remains consistent with prior context, handles any limitations gracefully, and ensures that the user’s needs are met or clearly identifies what is required to proceed."""})

        question = request.question
        chat_histories[session_id].append({"role": "user", "content": question})

        # Check if Supabase client is initialized
        if not supabase:
            return JSONResponse(content={"history": chat_histories[session_id], "session_id": session_id})

        # Use the LLM to generate a search query
        search_query_prompt = f"Based on the following customer query, what is the most likely product they are looking for? Customer query: {question}. Respond with only the product name."
        search_response = client.chat(model=OLLAMA_MODEL, messages=[{"role": "user", "content": search_query_prompt}])
        search_query = search_response['message']['content'].strip()

        # Search for the product in the database
        response = supabase.table(PRODUCTS_TABLE_NAME).select("*").text_search('name', search_query).execute()
        products = response.data

        # Check if we got any products
        if not products:
            chat_histories[session_id].append({"role": "assistant", "content": "I could not find any products matching your query. Could you please be more specific?"})
            return JSONResponse(content={"history": chat_histories[session_id], "session_id": session_id})

        # Prepare the context for the LLM
        context_parts = []
        for p in products:
            context_parts.append(f"Product: {p['name']}, Price: {p['price']}, Description: {p['description']}, Image_URL: {p['image_url']}")
        context = " ".join(context_parts)

        # Create a prompt for the LLM
        prompt = f"Context: {context}\\n\\n<customer_query>{question}</customer_query>"

        # Get the response from the LLM
        response = client.chat(
            model=OLLAMA_MODEL,
            messages=chat_histories[session_id] + [{"role": "user", "content": prompt}]
        )
        raw_answer = response['message']['content']

        # Parse the markdown response
        sections = {}
        current_section = None
        for line in raw_answer.split('\n'):
            line = line.strip()
            if line.startswith('[') and line.endswith(']'):
                current_section = line[1:-1].lower().replace(' ', '_')
                sections[current_section] = []
            elif current_section:
                sections[current_section].append(line)

        chat_histories[session_id].append({"role": "assistant", "content": sections})

        return JSONResponse(content={"history": chat_histories[session_id], "session_id": session_id})

    except Exception as e:
        return JSONResponse(content={"response": f"An error occurred: {e}", "session_id": session_id})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)