import os
import json
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()  # Load environment variables from .env

app = Flask(__name__)

# --- Configuration ---
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GOOGLE_API_KEY not found in .env file. Please set it.")

genai.configure(api_key=GEMINI_API_KEY)

# For this example, using gemini-1.5-flash-latest for speed and cost-effectiveness
# For more complex reasoning, gemini-1.5-pro-latest might be better but slower/pricier.
gemini_model = genai.GenerativeModel(
    model_name="gemini-1.5-flash-latest",
    # Good to have some safety settings, adjust as needed for debt collection context
    safety_settings=[
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        # Potentially less restrictive if needed
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    ],
    generation_config={
        "temperature": 0.7,  # Controls randomness: lower is more deterministic
        "top_p": 1,
        "top_k": 1,
        "max_output_tokens": 2048,  # Max length of the bot's response
    }
)

# --- Simulated Campaign Manager / CRM ---
# In a real system, this would come from a database or CRM API
CUSTOMERS_DATA = {
    "101": {
        "name": "Alice Wonderland",
        "amount_due": "150.75",
        "currency": "USD",
        "loan_info": "Personal Loan #PL7890",
        "last_contact_outcome": "Promised to pay next week.",
        "due_date": "2024-07-15"
    },
    "102": {
        "name": "Bob The Builder",
        "amount_due": "320.50",
        "currency": "USD",
        "loan_info": "Credit Card Account ending 1234",
        "last_contact_outcome": "Stated difficulty paying.",
        "due_date": "2024-07-10"
    },
    "103": {
        "name": "Charlie Brown",
        "amount_due": "85.00",
        "currency": "USD",
        "loan_info": "Overdue Invoice #INV2024-005",
        "last_contact_outcome": "No answer.",
        "due_date": "2024-06-30"
    }
}

YOUR_COMPANY_NAME = "Asset Telematics."  # Your company name

def get_initial_system_prompt(customer_id):
    customer = CUSTOMERS_DATA.get(str(customer_id))
    if not customer:
        # A concise error for an invalid customer ID, potentially with an Arabic touch if appropriate
        # For system internal errors, usually best to keep it in the primary language of development (English)
        return f"""You are a helpful AI assistant. The user selected an invalid customer ID. Please inform them concisely."""

    return f"""
    You are "FinBot", an exceptionally understanding, patient, and empathetic AI financial support agent from {YOUR_COMPANY_NAME}.
    Your primary goal is to connect with the customer warmly, understand their situation regarding their overdue payment, and collaboratively find a supportive solution.
    **Your communication style MUST BE VERY CONCISE and to the point, often just one or two short sentences. Use fluent, natural English. You may also incorporate simple, common Arabic greetings or pleasantries where natural and appropriate, especially at the beginning or end of a polite interaction.**

    **Core Persona & Communication Mandate:**
    - **Empathy & Brevity:** Acknowledge feelings briefly (e.g., "I understand this is tough," "I hear you."). Then, move to the point.
    - **Clear & Direct:** State information or questions clearly and concisely.
    - **Natural Language:** Fluent English. Avoid jargon.
    - **Arabic Pleasantries (Optional & Contextual):**
        - Greeting: "Marhaba" (Hello) or "Ahlan" (Welcome) can be used initially with an English greeting.
        - Thanks: "Shukran" (Thank you).
        - Inshallah (If God wills): Use very sparingly and only if the customer uses similar phrasing or context implies future uncertainty.
        - Example combined greeting: "Marhaba {customer['name']}, this is FinBot. How are you today?"
    - **Positive & Reassuring Tone:** Even when concise, your tone should be supportive.

    **Customer Details (For your context, do not repeat all of this unless necessary):**
    - Name: {customer['name']}
    - Amount Due: {customer['amount_due']} {customer['currency']}
    - Regarding: {customer['loan_info']}

    **Conversation Flow & Objectives (Respond CONCISELY to each):**
    1.  **Warm Opening & Feeling Check:**
        - Your Greeting (already initiated by JS): "Hello, I'm FinBot from {YOUR_COMPANY_NAME}. I understand you're {customer['name']}. How are you feeling today?"
        - Your response to their feeling: Acknowledge briefly. E.g., "I'm sorry to hear that." or "Good to know."
    2.  **Gentle Introduction to Topic (One Liner):** "I'm calling about your {customer['loan_info']} account, regarding the overdue amount of {customer['amount_due']} {customer['currency']}."
    3.  **Understanding their Situation (Concise Question):** "Is everything okay regarding this payment?" or "What's the situation with this payment?"
    4.  **Problem-Solving (Brief Options):**
        - Willing to pay: "Great. Pay in full, or a plan?"
        - Cannot pay full: "Understandable. What payment amount works for you regularly?"
    5.  **Disputes (Short Inquiry):** "Okay, noted. What's the concern with the charge?"
    6.  **Cannot Pay (Brief & Empathetic):** "I understand. When might things improve for a payment?"
    7.  **Wrong Number (Polite & Short):** "My apologies! I'll update our records. Shukran."
    8.  **Stop Calling / DNC (Acknowledge & Confirm):** "Understood. I'll mark your account for no further calls. Shukran."
    9.  **Compliance:** Maintain professionalism. No threats. Concise.

    **Your Initial Response (after the user's first message to your greeting):**
    The user has just responded to your initial greeting which was: "Hello, I'm FinBot from {YOUR_COMPANY_NAME}. I understand you're {customer['name']}. How are you feeling today?"
    Now, analyze their response. **Reply with ONE or TWO short, empathetic sentences in fluent English, acknowledging their feeling if expressed. You can start with an Arabic greeting like "Marhaba" or "Ahlan" if you haven't already used one in this turn and it feels natural.** Then, transition smoothly to the reason for the call as per point 2 in the Conversation Flow.
    For example, if user says "I'm stressed": "Ahlan {customer['name']}, I'm sorry to hear you're stressed. I'm calling about your {customer['loan_info']} account, regarding the overdue {customer['amount_due']}."
    If user says "I'm fine": "Marhaba {customer['name']}, good to hear. I'm calling about your {customer['loan_info']} account, regarding the overdue {customer['amount_due']}."
    """



@app.route('/')
def index():
    return render_template('index.html', customers=CUSTOMERS_DATA)


@app.route('/chat', methods=['POST'])
def chat_endpoint():
    try:
        data = request.get_json()
        user_message_text = data.get('message')
        conversation_history_client = data.get('history', [])  # History from client
        customer_id = data.get('customerId')

        if not user_message_text or not customer_id:
            return jsonify({"error": "Missing message or customerId"}), 400

        customer = CUSTOMERS_DATA.get(str(customer_id))
        if not customer:
            return jsonify({"error": "Invalid customerId"}), 400

        # Construct full history for Gemini
        # The system prompt is the very first "user" role message in the history for Gemini
        # The model's first visible message is the first "model" role message.

        # If client history is empty or just the initial bot message, start fresh with system prompt.
        # Otherwise, append the new user message to the client's history.

        gemini_history = []
        system_prompt_text = get_initial_system_prompt(customer_id)

        if not conversation_history_client or len(
                conversation_history_client) <= 1:  # Only initial bot message or empty
            gemini_history.append({'role': 'user', 'parts': [{'text': system_prompt_text}]})
            # If client sent initial bot message in history, add it.
            # This assumes the client's history[0] is the initial bot message if present.
            if conversation_history_client and conversation_history_client[0]['role'] == 'model':
                gemini_history.append(conversation_history_client[0])
        else:
            # Rebuild history, ensuring system prompt is first 'user' part
            gemini_history.append({'role': 'user', 'parts': [{'text': system_prompt_text}]})
            # Add the rest of the client history, skipping any initial system prompt it might have sent
            for item in conversation_history_client:
                if item['role'] == 'model' or (
                        item['role'] == 'user' and item['parts'][0]['text'] != system_prompt_text):
                    gemini_history.append(item)

        # Add the current user message
        gemini_history.append({'role': 'user', 'parts': [{'text': user_message_text}]})

        # Debug: print history being sent to Gemini
        # print("--- History for Gemini ---")
        # for item in gemini_history:
        #     print(f"{item['role']}: {item['parts'][0]['text'][:100]}...") # Print first 100 chars
        # print("--------------------------")

        chat_session = gemini_model.start_chat(
            history=gemini_history[:-1])  # Start chat with history *before* current user msg
        response = chat_session.send_message(gemini_history[-1]['parts'][0]['text'])  # Send current user message

        bot_response_text = response.text

        # print(f"Gemini Response: {bot_response_text}")

        return jsonify({"response": bot_response_text})

    except Exception as e:
        print(f"Error in /chat: {e}")
        # Check for specific Gemini API block reasons
        if hasattr(e, 'response') and hasattr(e.response,
                                              'prompt_feedback') and e.response.prompt_feedback.block_reason:
            return jsonify({"error": f"Message blocked by API: {e.response.prompt_feedback.block_reason}"}), 500
        if "SAFETY" in str(e).upper():  # Catch general safety blocks
            return jsonify({"error": "Content blocked due to safety settings."}), 500
        return jsonify({"error": f"An internal error occurred: {str(e)}"}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000)  # Default Flask port is 5000
