import os
import json
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
import google.generativeai as genai
import nltk
from nltk import data
from nltk.sentiment.vader import SentimentIntensityAnalyzer
import spacy
from pymongo import MongoClient # Import MongoClient
from datetime import datetime # To store timestamps
import uuid # To generate unique conversation IDs if needed

# --- NLTK Setup ---
# ... (keep your existing NLTK setup)
try:
    sid = SentimentIntensityAnalyzer()
except LookupError:
    print("Downloading VADER lexicon...")
    nltk.download('vader_lexicon')
    sid = SentimentIntensityAnalyzer()

try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    print("Downloading Punkt tokenizer...")
    nltk.download('punkt')


# --- SpaCy Setup ---
# ... (keep your existing SpaCy setup)
NLP_SPACY = None
try:
    NLP_SPACY = spacy.load('en_core_web_sm')
    print("SpaCy 'en_core_web_sm' model loaded successfully.")
except OSError:
    print("SpaCy 'en_core_web_sm' model not found. Please run:")
    print("python -m spacy download en_core_web_sm")


load_dotenv()

app = Flask(__name__)

# --- Configuration (Gemini, Customers, Company Name) ---
# ... (keep your existing Gemini, CUSTOMERS_DATA, YOUR_COMPANY_NAME)
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

gemini_model = genai.GenerativeModel( # ... your model config
    model_name="gemini-1.5-flash-latest",
    safety_settings=[
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    ],
    generation_config={
        "temperature": 0.7, "top_p": 1, "top_k": 1, "max_output_tokens": 2048,
    }
)
CUSTOMERS_DATA = {
    "101": {"name": "Alice Wonderland", "amount_due": "150.75", "currency": "USD", "loan_info": "Personal Loan #PL7890", "last_contact_outcome": "Promised to pay next week.", "due_date": "2024-07-15"},
    "102": {"name": "Bob The Builder", "amount_due": "320.50", "currency": "USD", "loan_info": "Credit Card Account ending 1234", "last_contact_outcome": "Stated difficulty paying.", "due_date": "2024-07-10"},
    "103": {"name": "Charlie Brown", "amount_due": "85.00", "currency": "USD", "loan_info": "Overdue Invoice #INV2024-005", "last_contact_outcome": "No answer.", "due_date": "2024-06-30"}
}
YOUR_COMPANY_NAME = "Asset Telematics."


# --- MongoDB Setup ---
MONGO_URI = os.getenv("MONGO_URI")
mongo_client = None
db = None
conversations_collection = None

try:
    if not MONGO_URI:
        print("MONGO_URI not found in .env file. Skipping MongoDB integration.")
    else:
        mongo_client = MongoClient(MONGO_URI,serverSelectionTimeoutMS=3000)
        # Pymongo will create the DB and collection if they don't exist on first write.
        # Let's use the DB name from the URI or a default if not specified there.
        # If your URI is 'mongodb://localhost:27017/' without a db name, client.get_database() is better.
        # If your URI is 'mongodb://localhost:27017/chat_app_db', then client.chat_app_db works.
        # Let's try to parse it or use a default.
        db_name_from_uri = MONGO_URI.split('/')[-1].split('?')[0] if '/' in MONGO_URI else 'chat_app_db'
        db = mongo_client[db_name_from_uri if db_name_from_uri else 'chat_app_db']

        conversations_collection = db["conversations"]
        # Test connection
        mongo_client.admin.command('ping')
        print(f"Successfully connected to MongoDB! Using database: {db.name}, collection: {conversations_collection.name}")
except Exception as e:
    print(f"Error connecting to MongoDB: {e}")
    mongo_client = None # Ensure it's None if connection failed
    conversations_collection = None


# --- NLP Utilities ---
# ... (keep get_sentiment and extract_entities_spacy)
def get_sentiment(text):
    scores = sid.polarity_scores(text)
    compound = scores['compound']
    if compound >= 0.05: return "positive"
    elif compound <= -0.05: return "negative"
    else: return "neutral"

def extract_entities_spacy(text):
    if not NLP_SPACY: return {}
    doc = NLP_SPACY(text)
    entities = {}
    for ent in doc.ents:
        if ent.label_ not in entities: entities[ent.label_] = []
        entities[ent.label_].append(ent.text)
    return entities

# --- Prompt Generation (Using your more autonomous version) ---
def get_initial_system_prompt(customer_id, user_sentiment_hint=None, extracted_entities_hint=None):
    customer = CUSTOMERS_DATA.get(str(customer_id))
    if not customer:
        return "You are a helpful AI assistant. The user selected an invalid customer ID."

    sentiment_instruction = ""
    if user_sentiment_hint == "negative":
        sentiment_instruction = "The customer seems to be feeling negative or stressed. Be extra patient, empathetic, and reassuring. Acknowledge their difficulty directly."
    elif user_sentiment_hint == "positive":
        sentiment_instruction = "The customer seems to be feeling positive. Maintain a warm and collaborative tone."

    entity_awareness_instruction = ""
    if extracted_entities_hint and extracted_entities_hint != {}: # Check if not empty
        entity_awareness_instruction = f"The user's message mentioned: {json.dumps(extracted_entities_hint)}. Use this to understand their specific request (e.g., a date or amount they proposed)."

    payment_options_rules = f"""
    Your Allowed Actions & Payment Negotiation Rules:
    - Your primary goal is to secure payment for the outstanding amount of {customer['amount_due']} {customer['currency']} for {customer['loan_info']}.
    - You ARE AUTHORIZED to propose the following if the customer expresses difficulty paying by the due date ({customer['due_date']}):
        1. A short extension: "I can offer you a one-time extension of up to 7 days from the original due date ({customer['due_date']}). Would paying by [calculate new date] work for you?"
        2. Split payment: "If it helps, we could potentially split the payment of {customer['amount_due']} into two equal installments. The first would be due within 7 days, and the second 7 days after that. Is this something you'd like to consider?"
        3. Promise to pay full amount later: "If you need a bit more time for the full amount, what specific date within the next 10 days could you commit to paying {customer['amount_due']}?"
    - If the customer proposes a date or plan that fits these rules, you can tentatively accept it. For example: "Okay, I can note your commitment to pay {customer['amount_due']} by [customer's proposed date, if within 10 days]. I'll update our records with this promise to pay."
    - If the customer proposes something outside these rules (e.g., wants a discount, a much longer extension, or a very small partial payment), you should state: "I understand that might be your preference, but the options I can currently offer are [re-iterate allowed options briefly]. If these don't work, I can make a note of your situation, and a specialist from our team will review your account for any other possibilities and contact you."
    - DO NOT make up new payment plans or agree to terms outside of these explicit rules.
    - After a customer agrees to a specific plan YOU proposed or a date they proposed (that fits your rules), confirm it clearly: "Great, so to confirm, you'll be making a payment of [amount] by [date]. I've made a note of this in your account. Please ensure the payment is made by then to keep your account in good standing."
    - If the user asks HOW to pay, you can say: "You can make a payment through our online portal at [YourCompanyWebsite.com/pay] or by calling us at [YourPhoneNumber]."
    """ # Shortened for brevity, use your full prompt

    return f"""
    You are "FinBot", an AI collections agent... (rest of your detailed prompt) ...
    {sentiment_instruction}
    {entity_awareness_instruction}
    Customer Details (For your context ONLY):
    - Name: {customer['name']}
    - Amount Due: {customer['amount_due']} {customer['currency']}
    - Regarding: {customer['loan_info']}
    - Due Date: {customer['due_date']}
    - Last Contact Outcome: {customer['last_contact_outcome']}
    {payment_options_rules}
    Conversation Flow: ...
    Initial Interaction Example: ...
    Your first response after the user's initial message should directly address the collection and try to guide them towards one of your allowed solutions.
    BE VERY CLEAR about amounts and dates when confirming.
    """
# --- Function to Save Conversation Turn ---
def save_conversation_turn(customer_id, role, message_text, sentiment=None, entities=None, conversation_id=None):
    if conversations_collection is None:
        print("MongoDB not configured. Skipping save")



    # We'll generate a new conversation_id for each request for simplicity now.
    # For true session tracking, this ID would need to be managed across requests.
    if conversation_id is None:
        # A simple way to group turns related to one customer session (though not strictly a "session")
        # You might want a more robust session ID generated on the client or first interaction
        conversation_id = str(uuid.uuid4()) # Generates a unique ID for this turn/interaction


    turn_data = {
        "conversation_id": conversation_id, # Helps group a sequence of user/bot messages if managed
        "customer_id": str(customer_id),
        "role": role,  # "user" or "model"
        "message": message_text,
        "timestamp": datetime.utcnow() # Store time in UTC
    }
    if sentiment:
        turn_data["sentiment"] = sentiment
    if entities:
        turn_data["entities"] = entities

    try:
        insert_result = conversations_collection.insert_one(turn_data)
        print(f"Saved to MongoDB with id: {insert_result.inserted_id}")
    except Exception as e:
        print(f"Error saving to MongoDB: {e}")


@app.route('/')
def index():
    return render_template('index.html', customers=CUSTOMERS_DATA)


@app.route('/chat', methods=['POST'])
def chat_endpoint():
    # ... (keep global NLP_SPACY if needed, or ensure it's passed/accessible)
    try:
        data = request.get_json()
        user_message_text = data.get('message')
        conversation_history_client = data.get('history', []) # Client-side history
        customer_id = data.get('customerId')
        # Optional: Client could send a session_id if you implement session management
        # current_conversation_id = data.get('conversationId', str(uuid.uuid4())) # Generate if not provided

        if not user_message_text or not customer_id:
            return jsonify({"error": "Missing message or customerId"}), 400

        # --- NLTK Sentiment Analysis of User Input ---
        user_sentiment = get_sentiment(user_message_text)
        print(f"User Sentiment (NLTK VADER): {user_sentiment} for message: '{user_message_text}'")

        # --- SpaCy Named Entity Recognition ---
        extracted_entities = {}
        if NLP_SPACY:
            extracted_entities = extract_entities_spacy(user_message_text)
            print(f"Extracted Entities (SpaCy): {extracted_entities} for message: '{user_message_text}'")

        # --- Save User Message to MongoDB ---
        # For now, let's generate a simple interaction_id for this pair of user/bot messages
        interaction_id_for_db = str(uuid.uuid4())
        save_conversation_turn(
            customer_id=customer_id,
            role="user",
            message_text=user_message_text,
            sentiment=user_sentiment,
            entities=extracted_entities,
            conversation_id=interaction_id_for_db # Use the same ID for the bot's response in this turn
        )

        customer = CUSTOMERS_DATA.get(str(customer_id))
        if not customer:
            return jsonify({"error": "Invalid customerId"}), 400

        system_prompt_text = get_initial_system_prompt(
            customer_id,
            user_sentiment_hint=user_sentiment,
            extracted_entities_hint=extracted_entities
        )

        # ... (Your existing logic for building gemini_history with the system_prompt_text) ...
        # (Ensure this logic is correct as per previous discussions)
        temp_history_for_gemini = []
        current_turn_context_parts = [{'text': system_prompt_text}]
        if not conversation_history_client:
            temp_history_for_gemini.append({'role': 'user', 'parts': current_turn_context_parts})
        else:
            temp_history_for_gemini.append({'role': 'user', 'parts': current_turn_context_parts})
            for item in conversation_history_client:
                is_system_prompt_like = 'You are "FinBot"' in item['parts'][0]['text'] and item['role'] == 'user'
                if not is_system_prompt_like:
                    temp_history_for_gemini.append(item)
        temp_history_for_gemini.append({'role': 'user', 'parts': [{'text': user_message_text}]})

        final_gemini_history = []
        if temp_history_for_gemini:
            final_gemini_history.append(temp_history_for_gemini[0])
            for i in range(1, len(temp_history_for_gemini)):
                if temp_history_for_gemini[i]['role'] != final_gemini_history[-1]['role']:
                    final_gemini_history.append(temp_history_for_gemini[i])
                else:
                    final_gemini_history[-1]['parts'][0]['text'] += "\n" + temp_history_for_gemini[i]['parts'][0]['text']

        if not final_gemini_history or final_gemini_history[-1]['role'] != 'user':
             return jsonify({"error": "Invalid history structure for Gemini"}), 500

        chat_session = gemini_model.start_chat(history=final_gemini_history[:-1])
        response = chat_session.send_message(final_gemini_history[-1]['parts'][0]['text'])
        bot_response_text = response.text

        # --- Save Bot Response to MongoDB ---
        save_conversation_turn(
            customer_id=customer_id,
            role="model", # Or "bot", "assistant" - be consistent
            message_text=bot_response_text,
            conversation_id=interaction_id_for_db # Use the same ID as the user message for this turn
        )

        # Consider returning the conversation_id to the client if it needs to manage session state
        # return jsonify({"response": bot_response_text, "conversationId": current_conversation_id})
        return jsonify({"response": bot_response_text})

    except Exception as e:
        print(f"Error in /chat: {e}")
        import traceback
        traceback.print_exc()
        # ... (your existing error handling for Gemini) ...
        if hasattr(e, 'response') and hasattr(e.response, 'prompt_feedback') and e.response.prompt_feedback.block_reason:
            return jsonify({"error": f"Message blocked by API: {e.response.prompt_feedback.block_reason}"}), 500
        if "SAFETY" in str(e).upper():
             return jsonify({"error": "Content blocked due to safety settings."}), 500
        return jsonify({"error": f"An internal error occurred: {str(e)}"}), 500


if __name__ == '__main__':
    # ... (your NLTK and SpaCy resource checks) ...
    try:
        sid_test = SentimentIntensityAnalyzer()
        nltk.data.find('tokenizers/punkt')
        print("NLTK resources found.")
    except LookupError as e:
        print(f"NLTK resource missing: {e}")
        # exit()

    if NLP_SPACY is None:
        print("SpaCy model 'en_core_web_sm' not loaded. Some NLP features might be limited.")
        # exit() # Optionally exit

    if conversations_collection is None:
        print("Warning: MongoDB is not connected. Conversation logging will be skipped.")

    else:
        # You could add an else here if you want to confirm connection,
        # but it's already printed in the try/except block during setup.
        pass

    app.run(debug=True, port=5000)