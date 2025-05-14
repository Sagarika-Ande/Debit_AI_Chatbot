import os
import google.generativeai as genai
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
import json

# --- New Imports for STT/TTS ---
import speech_recognition as sr
import pyttsx3
import base64
import io
from pydub import AudioSegment  # For audio conversion

load_dotenv()

# --- Configure Gemini API ---
try:
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel('gemini-1.5-flash')  # Or your preferred model
except Exception as e:
    print(f"Error configuring Gemini: {e}")
    model = None

# --- Initialize TTS Engine ---
try:
    tts_engine = pyttsx3.init()
    voices = tts_engine.getProperty('voices')
    # You might want to select a specific voice if available
    # For example, find a US English female voice
    selected_voice = None
    for voice in voices:
        if "english" in voice.name.lower() and "united states" in voice.name.lower() and voice.gender == 'female':
            selected_voice = voice.id
            break
        elif "zira" in voice.name.lower():  # Common Windows voice
            selected_voice = voice.id
            break
        elif "samantha" in voice.name.lower():  # Common macOS voice
            selected_voice = voice.id
            break
    if selected_voice:
        tts_engine.setProperty('voice', selected_voice)
    tts_engine.setProperty('rate', 140)  # Adjust speed
    tts_engine.setProperty('volume', 0.9)  # Adjust volume
except Exception as e:
    print(f"Error initializing TTS engine: {e}")
    tts_engine = None

app = Flask(__name__)

# --- Customer Data (same as before) ---
# ... (Keep your customer_data dictionary here) ...
customer_data = {
    "CUST001": {
        "name": "Alice Wonderland",
        "outstanding_balance": 1250.75,
        "last_payment_date": "2023-04-15",
        "payment_due_date": "2023-05-20",
        "account_status": "active",
        "notes": "Inquired about payment plan options last month. Prefers email communication.",
        "sentiment_history": ["neutral", "slightly_anxious"]
    },
    "CUST002": {
        "name": "Bob The Builder",
        "outstanding_balance": 0.00,
        "last_payment_date": "2023-05-01",
        "payment_due_date": "N/A",
        "account_status": "paid_in_full",
        "notes": "Long-term customer, always pays on time. Expressed interest in new services.",
        "sentiment_history": ["positive", "neutral"]
    },
    "CUST003": {
        "name": "Charlie Brown",
        "outstanding_balance": 300.50,
        "last_payment_date": "2023-03-10",
        "payment_due_date": "2023-04-05",
        "account_status": "overdue",
        "notes": "Has been sent two reminder notices. Previously mentioned temporary financial hardship.",
        "sentiment_history": ["anxious", "frustrated", "anxious"]
    }
}
YOUR_COMPANY_NAME = "Asset Telematics"


def get_system_prompt(customer_id):
    customer = customer_data.get(customer_id)
    if not customer:
        return f"You are FinBot, a friendly and empathetic AI collections agent from {YOUR_COMPANY_NAME}. The user has selected an invalid customer ID. Apologize and ask them to select a valid customer."

    # Refined prompt
    prompt = f"""
    You are FinBot, an advanced, empathetic, and highly skilled AI collections agent from {YOUR_COMPANY_NAME}.
    Your primary goal is to understand the customer's situation, remind them of their outstanding balance, and collaboratively find a resolution, such as making a payment or setting up a payment plan.
    You are currently speaking with {customer['name']}.

    Customer Details:
    - Name: {customer['name']}
    - Outstanding Balance: ${customer['outstanding_balance']:.2f}
    - Last Payment Date: {customer['last_payment_date']}
    - Payment Due Date: {customer['payment_due_date']}
    - Account Status: {customer['account_status']}
    - Internal Notes: {customer['notes']}
    - Recent Sentiment: {', '.join(customer['sentiment_history'][-2:]) if customer['sentiment_history'] else 'N/A'}

    Your Interaction Style:
    1.  Empathetic & Understanding: Always start by acknowledging the customer's feelings if they express any hardship or emotion. Use phrases like "I understand this can be a difficult situation," or "I appreciate you sharing that with me."
    2.  Clear & Concise: Provide information clearly, especially regarding balances and dates.
    3.  Solution-Oriented: Proactively suggest solutions like payment plans if the customer indicates difficulty paying the full amount.
    4.  Professional & Polite: Maintain a professional tone. Never be accusatory or aggressive.
    5.  Information Gathering (Subtle): If the customer is hesitant, try to understand the reason for non-payment without being intrusive. For example, "Is there anything preventing you from making a payment at this time?"
    6.  Maintain Context: Refer to previous parts of the conversation. Your memory (the chat history) is provided.
    7.  Call to Action: Gently guide the conversation towards a resolution (payment, payment plan).
    8.  Do NOT Hallucinate: Only use the information provided about the customer. Do not invent new services, policies, or details not present in their record or your company's general knowledge.
    9.  Company Name: When relevant, mention you are from {YOUR_COMPANY_NAME}.
    10. Brevity: Keep responses reasonably concise, aiming for 1-3 sentences unless more detail is essential. Avoid long monologues.
    11. First Interaction: Your first message in any new conversation with a selected customer should be: "Hello, I'm FinBot from {YOUR_COMPANY_NAME}. I understand you're {customer['name']}. How are you feeling today?"

    Conversation Flow Example:
    - If customer says they can't pay: "I understand things can be tight sometimes. We might be able to set up a payment plan. Would that be helpful?"
    - If customer is angry: "I hear your frustration, and I want to help resolve this. Let's see what we can do."
    - If customer agrees to pay: "That's great to hear! You can make a payment of ${customer['outstanding_balance']:.2f} through our online portal or I can guide you through other options. Which do you prefer?"

    Your responses should be plain text. Do not use markdown.
    """
    return prompt


@app.route('/')
def index():
    return render_template('index.html', customers=customer_data, company_name=YOUR_COMPANY_NAME)


@app.route('/chat', methods=['POST'])
def chat():
    if not model:
        return jsonify({"error": "Generative AI model not initialized"}), 500
    if not tts_engine:
        return jsonify({"error": "TTS engine not initialized"}), 500

    data = request.json
    user_message = data.get('message')
    history = data.get('history', [])
    customer_id = data.get('customerId')

    if not user_message or not customer_id:
        return jsonify({"error": "Missing message or customerId"}), 400

    system_prompt_text = get_system_prompt(customer_id)

    # Construct messages for Gemini, including system prompt and history
    # The system prompt is now handled by `system_instruction` parameter for `GenerativeModel`
    # However, for `start_chat`, we can prepend it or use it as the first model message if user starts.
    # For simplicity, let's adapt to the typical chat history format.

    # The initial greeting from the bot is part of the history sent by the client
    # So, history already contains:
    # 1. {role: "model", parts: [{text: "Hello, I'm FinBot..."}]}
    # 2. {role: "user", parts: [{text: user's_first_response}]}
    # ... and so on.

    # For Gemini, system instructions are best set at model initialization or `start_chat`
    # Let's ensure the history is correctly formatted
    formatted_history = []
    for item in history:
        # Ensure 'parts' is a list of dictionaries with a 'text' key
        if isinstance(item.get('parts'), list) and \
                all(isinstance(part, dict) and 'text' in part for part in item['parts']):
            formatted_history.append({'role': item['role'], 'parts': item['parts']})
        elif isinstance(item.get('parts'), str):  # Older format, adapt
            formatted_history.append({'role': item['role'], 'parts': [{'text': item['parts']}]})

    try:
        # Start a chat session with the existing history and system instruction
        # Note: System instruction might be better applied when model is initialized for overall behavior.
        # For per-chat context, including it in the history as a special first message or
        # using model.generate_content with system_instruction param is often preferred.
        # Since Gemini's `start_chat` takes `history`, we build on that.
        # The system prompt is quite long; ensure it's effectively used.
        # One way is to prepend it as a model utterance that the user doesn't see but sets context.
        # Or, if model supports it, a dedicated system message.

        # Current approach: System prompt is for context setting, client sends initial bot message.
        # We'll pass the full context (system prompt + history + new message)

        chat_session = model.start_chat(history=formatted_history)
        # The system prompt needs to be "told" to the model.
        # One way: prepend it to the user's message or treat it as an initial system-level turn.
        # For this example, we are providing a very detailed system prompt.
        # Let's make it the first "model" turn in the mind of the AI if not explicitly supported as system instruction in start_chat.
        # The current `get_system_prompt` is more of a full context document.

        # The initial greeting is already in history from client.
        # We should feed the system prompt to the model.
        # The `system_instruction` parameter in `GenerativeModel` is good for this.
        # Re-initialize model with system instruction for this customer
        # This is not ideal for every call, but for demonstration:

        _model = genai.GenerativeModel(
            'gemini-1.5-flash',  # or your chosen model
            system_instruction=system_prompt_text
        )
        chat_session = _model.start_chat(history=formatted_history)  # history should NOT include system prompt now

        response = chat_session.send_message(user_message)
        bot_response_text = response.text

        # --- TTS ---
        audio_bytes_io = io.BytesIO()
        tts_engine.save_to_file(bot_response_text, audio_bytes_io)  # pyttsx3 can't save directly to BytesIO

        # Workaround for pyttsx3 not saving to BytesIO directly:
        temp_audio_filename = "temp_response.wav"  # or .mp3 if you configure pyttsx3 for it
        tts_engine.save_to_file(bot_response_text, temp_audio_filename)
        tts_engine.runAndWait()  # Important to ensure file is written before reading

        with open(temp_audio_filename, "rb") as audio_file:
            audio_data = audio_file.read()
        os.remove(temp_audio_filename)  # Clean up temp file

        audio_base64 = base64.b64encode(audio_data).decode('utf-8')

        return jsonify({
            "response": bot_response_text,
            "audio_base64": audio_base64,  # Send audio data
            "audio_format": "wav"  # Specify format
        })

    except Exception as e:
        print(f"Error in /chat: {e}")
        # Try to provide a fallback TTS for the error message itself
        error_message_text = "I encountered an issue processing your request. Please try again."
        try:
            temp_audio_filename = "temp_error.wav"
            tts_engine.save_to_file(error_message_text, temp_audio_filename)
            tts_engine.runAndWait()
            with open(temp_audio_filename, "rb") as audio_file:
                audio_data = audio_file.read()
            os.remove(temp_audio_filename)
            audio_base64 = base64.b64encode(audio_data).decode('utf-8')
            return jsonify({
                "response": error_message_text,
                "audio_base64": audio_base64,
                "audio_format": "wav"
            }), 500
        except Exception as tts_e:
            print(f"Error generating TTS for error message: {tts_e}")
            return jsonify({"error": str(e), "response": error_message_text}), 500


# --- New STT Endpoint ---
@app.route('/transcribe', methods=['POST'])
def transcribe_audio():
    if 'audio_data' not in request.files:
        return jsonify({"error": "No audio file part"}), 400

    file = request.files['audio_data']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    recognizer = sr.Recognizer()

    try:
        # The browser might send webm or ogg. SpeechRecognition needs wav.
        # Convert using pydub
        audio = AudioSegment.from_file(file, format=file.content_type.split('/')[-1])  # e.g. "webm"

        # Export to a temporary WAV file in memory (BytesIO)
        wav_io = io.BytesIO()
        audio.export(wav_io, format="wav")
        wav_io.seek(0)  # Reset pointer to the beginning of the BytesIO object

        with sr.AudioFile(wav_io) as source:
            audio_data = recognizer.record(source)  # read the entire audio file

        # Recognize speech using Google Web Speech API (requires internet)
        # You can add try-except blocks for different recognizers (Sphinx for offline, etc.)
        text = recognizer.recognize_google(audio_data)
        return jsonify({"transcript": text})
    except sr.UnknownValueError:
        print("Google Web Speech API could not understand audio")
        return jsonify({"error": "Could not understand audio"}), 400
    except sr.RequestError as e:
        print(f"Could not request results from Google Web Speech API; {e}")
        return jsonify({"error": f"API unavailable: {e}"}), 503
    except Exception as e:
        print(f"Error in /transcribe: {e}")
        return jsonify({"error": f"Transcription failed: {str(e)}"}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5001)  # Run on a different port if your other app is on 5000