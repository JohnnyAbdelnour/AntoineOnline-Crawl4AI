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

# System prompt for the AI agent
SYSTEM_PROMPT = """You are Najjar Online's dedicated customer support AI agent. Your primary responsibility is to provide accurate and professional product information by querying the Supabase database and formatting responses appropriately.

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

Never provide information that hasn't been verified through the database. Always maintain a professional, helpful tone while ensuring accuracy and clarity in all communications.   Jump Logic/Success Prompt: When the response is relevant to the user's query, directly addresses their intent, or appropriately moves the conversation forward—such as by asking clarifying questions or requesting additional information—it should offer a clear, complete, and contextually appropriate resolution. If further action is required, the response includes timely and relevant follow-up such as next steps, useful links, or confirmations. Throughout the exchange, the assistant remains consistent with prior context, handles any limitations gracefully, and ensures that the user’s needs are met or clearly identifies what is required to proceed."""


class ChatRequest(BaseModel):
    question: str
    session_id: str = None

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    with open("static/index.html") as f:
        return HTMLResponse(content=f.read(), status_code=200)

@app.post("/ask", response_class=JSONResponse)
async def ask(request: ChatRequest):
    session_id = request.session_id
    question = request.question

    try:
        # Initialize session and history if it's new
        if not session_id or session_id not in chat_histories:
            session_id = str(uuid.uuid4())
            chat_histories[session_id] = [{"role": "system", "content": SYSTEM_PROMPT}]

        # Add user's question to the history
        chat_histories[session_id].append({"role": "user", "content": question})

        # Check for Supabase client
        if not supabase:
            error_message = "I'm having trouble connecting to the database. Please try again later."
            chat_histories[session_id].append({"role": "assistant", "content": error_message})
            return JSONResponse(content={"history": chat_histories[session_id], "session_id": session_id})

        # Step 1: Use LLM to generate a search query from the user's question
        search_prompt = f"Extract the most relevant product search terms from the following query. Respond with only the search terms, separated by ' | ' for a text search. Query: '{question}'"
        search_response = client.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": search_prompt}]
        )
        search_query = search_response['message']['content'].strip()

        # Step 2: Search for products in the database
        db_response = supabase.table(PRODUCTS_TABLE_NAME).select("*").text_search('name', search_query, config='english').execute()
        products = db_response.data

        # Handle case where no products are found
        if not products:
            answer = "I'm sorry, I couldn't find any products matching your description. Could you please try rephrasing your query or being more specific?"
            chat_histories[session_id].append({"role": "assistant", "content": answer})
            return JSONResponse(content={"history": chat_histories[session_id], "session_id": session_id})

        # Step 3: Prepare context and generate the final response
        context_parts = []
        for p in products:
            product_info = f"Product: {p.get('name', 'N/A')}, Price: {p.get('price', 'N/A')}, Description: {p.get('description', 'N/A')}"
            context_parts.append(product_info)
        context = "\n".join(context_parts)

        final_prompt = f"Based on the following information from our database, please answer the customer's question. Adhere strictly to the persona and formatting rules from the system prompt.\n\nDatabase Information:\n{context}\n\nCustomer Question:\n{question}"

        # Use the existing history (with system prompt) and the new context-aware prompt
        messages_for_llm = chat_histories[session_id][:-1]  # All history except the last user message
        messages_for_llm.append({"role": "user", "content": final_prompt})

        # Get the final response from the LLM
        final_response = client.chat(
            model=OLLAMA_MODEL,
            messages=messages_for_llm
        )
        answer = final_response['message']['content']

        # Add the assistant's answer to the history
        chat_histories[session_id].append({"role": "assistant", "content": answer})

        return JSONResponse(content={"history": chat_histories[session_id], "session_id": session_id})

    except Exception as e:
        # Ensure session_id is initialized for error response
        if 'session_id' not in locals() or not session_id:
            session_id = str(uuid.uuid4())

        error_message = f"An unexpected error occurred: {str(e)}. Please try again."
        # Avoid adding to a non-existent history
        if session_id not in chat_histories:
            chat_histories[session_id] = []

        chat_histories[session_id].append({"role": "assistant", "content": error_message})

        return JSONResponse(content={"history": chat_histories[session_id], "session_id": session_id}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)