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
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Najjar Online - AI Assistant</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background-color: #f0f2f5;
            margin: 0;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
        }}
        .chat-container {{
            width: 100%;
            max-width: 400px;
            height: 95vh;
            max-height: 800px;
            display: flex;
            flex-direction: column;
            background-color: #ffffff;
            border-radius: 20px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
            overflow: hidden;
        }}
        .chat-header {{
            background-color: #007bff;
            color: white;
            padding: 15px;
            text-align: center;
            font-size: 1.2em;
            font-weight: 500;
        }}
        .chat-body {{
            flex-grow: 1;
            padding: 20px;
            overflow-y: auto;
        }}
        .chat-footer {{
            padding: 10px;
            border-top: 1px solid #e0e0e0;
            background-color: #f8f9fa;
        }}
        .chat-footer form {{
            display: flex;
        }}
        .chat-footer input[type="text"] {{
            flex-grow: 1;
            border: 1px solid #ced4da;
            border-radius: 20px;
            padding: 10px 15px;
            font-size: 1em;
            outline: none;
        }}
        .chat-footer button {{
            background-color: #007bff;
            color: white;
            border: none;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            margin-left: 10px;
            cursor: pointer;
            font-size: 1.2em;
        }}
        .response-area {{
            margin-top: 20px;
        }}
        .product-info {{
            border: 1px solid #e0e0e0;
            border-radius: 10px;
            padding: 15px;
            margin-top: 15px;
        }}
        .product-info h3 {{
            margin-top: 0;
        }}
        .product-info img {{
            max-width: 100%;
            border-radius: 10px;
            margin-top: 10px;
        }}
        ul {{
            list-style-type: none;
            padding: 0;
        }}
        li {{
            margin-bottom: 5px;
        }}
        strong {{
            font-weight: 500;
        }}
    </style>
</head>
<body>
    <div class="chat-container">
        <div class="chat-header">
            Najjar Online AI Assistant
        </div>
        <div class="chat-body">
            <div class="response-area">
                {response}
            </div>
        </div>
        <div class="chat-footer">
            <form action="/" method="post">
                <input type="text" name="question" placeholder="Type your message...">
                <button type="submit">&#10148;</button>
            </form>
        </div>
    </div>
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
        context = " ".join([f"Product: {p['name']}, Price: {p['price']}, Description: {p['description']}, Image_URL: {p['image_url']}" for p in products])

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
        raw_answer = response['message']['content']

        # Parse the markdown response
        sections = {}
        current_section = None
        for line in raw_answer.split('\\n'):
            line = line.strip()
            if line.startswith('[') and line.endswith(']'):
                current_section = line[1:-1].lower().replace(' ', '_')
                sections[current_section] = []
            elif current_section:
                sections[current_section].append(line)

        # Build the HTML response
        html_response = ""
        if 'professional_greeting' in sections:
            html_response += f"<p>{' '.join(sections['professional_greeting'])}</p>"

        if 'direct_answer_addressing_the_query' in sections:
            html_response += f"<p>{' '.join(sections['direct_answer_addressing_the_query'])}</p>"

        if 'detailed_product_information_from_database' in sections:
            html_response += "<div class='product-info'>"
            # This is a simplified parsing. A more robust solution would handle various markdown elements.
            for item in sections['detailed_product_information_from_database']:
                if 'Image URL:' in item:
                    img_url = item.split('Image URL:')[1].strip()
                    html_response += f'<img src="{img_url}" alt="Product Image">'
                else:
                    html_response += f"<p>{item}</p>"
            html_response += "</div>"

        if 'relevant_additional_context' in sections:
            html_response += f"<p>{' '.join(sections['relevant_additional_context'])}</p>"

        if 'professional_closing' in sections:
            html_response += f"<p>{' '.join(sections['professional_closing'])}</p>"

        return html_form.format(response=html_response)

    except Exception as e:
        return html_form.format(response=f"An error occurred: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)