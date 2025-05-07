document.addEventListener('DOMContentLoaded', () => {
    // --- DOM Elements ---
    const chatBox = document.getElementById('chatBox');
    const userInput = document.getElementById('userInput');
    const sendButton = document.getElementById('sendButton');
    const micButton = document.getElementById('micButton');
    const customerSelect = document.getElementById('customerSelect');
    const currentCustomerNameDisplay = document.getElementById('currentCustomerName');
    const agentStatusDisplay = document.getElementById('agentStatus');
    const messagePlaceholder = document.querySelector('.message-placeholder');
    const themeToggleButton = document.getElementById('themeToggle');

    // --- State Variables ---
    let conversationHistory = [];
    let currentCustomerId = null;
    const yourCompanyName = "Asset Telematics."; // Match your Flask app.py
    let recognition;
    let isRecording = false;
    let thinkingMessageElement = null;

    // --- Utility Functions ---
    function updateAgentStatus(statusText, statusType = "info") { // statusType: info, ready, error, speaking, listening
        if (agentStatusDisplay) {
            agentStatusDisplay.textContent = statusText;
            agentStatusDisplay.className = 'status-indicator'; // Reset classes
            switch(statusType) {
                case "ready":
                    agentStatusDisplay.classList.add('status-ready');
                    break;
                case "error":
                    agentStatusDisplay.classList.add('status-error');
                    break;
                case "speaking":
                case "listening":
                    agentStatusDisplay.classList.add('status-speaking');
                    break;
                default: // info
                    // Default styling (from CSS)
                    break;
            }
        }
    }

    function toggleInputControls(disabled) {
        userInput.disabled = disabled;
        sendButton.disabled = disabled;
        if (micButton) micButton.disabled = disabled || isRecording;

        userInput.style.opacity = disabled ? 0.7 : 1;
        sendButton.style.opacity = disabled ? 0.7 : 1;
        if (micButton) micButton.style.opacity = (disabled || isRecording) ? 0.7 : 1;
    }

    function showMessagePlaceholder(show) {
        if (messagePlaceholder) {
            messagePlaceholder.style.display = show ? 'flex' : 'none';
        }
    }

    // --- Web Speech API for STT (Speech-to-Text) ---
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        recognition = new SpeechRecognition();
        recognition.continuous = false;
        recognition.lang = 'en-US';
        recognition.interimResults = false;
        recognition.maxAlternatives = 1;

        recognition.onstart = () => {
            isRecording = true;
            micButton.classList.add('recording');
            micButton.querySelector('.mic-on-icon').style.display = 'none';
            micButton.querySelector('.mic-off-icon').style.display = 'block';
            updateAgentStatus("Listening attentively...", "listening");
            toggleInputControls(true);
            if(micButton) micButton.disabled = false; // Keep mic button enabled to stop
        };

        recognition.onresult = (event) => {
            const transcript = event.results[0][0].transcript;
            userInput.value = transcript;
            updateAgentStatus("Got it! Processing...", "info");
            sendMessage();
        };

        recognition.onerror = (event) => {
            console.error('Speech recognition error:', event.error);
            addMessageToUI('Speech recognition error. Please type or try again.', 'bot-message');
            updateAgentStatus("Mic error, sorry!", "error");
            isRecording = false; // Ensure isRecording is false
            micButton.classList.remove('recording');
            micButton.querySelector('.mic-on-icon').style.display = 'block';
            micButton.querySelector('.mic-off-icon').style.display = 'none';
            if (currentCustomerId) toggleInputControls(false);
        };

        recognition.onend = () => {
            isRecording = false;
            micButton.classList.remove('recording');
            micButton.querySelector('.mic-on-icon').style.display = 'block';
            micButton.querySelector('.mic-off-icon').style.display = 'none';
            if (!userInput.disabled && currentCustomerId) {
                 toggleInputControls(false);
                 updateAgentStatus("Ready when you are.", "ready");
            }
        };
    } else {
        if(micButton) micButton.style.display = 'none';
        console.warn("Web Speech API (STT) not supported in this browser.");
    }

    if(micButton) {
        micButton.addEventListener('click', () => {
            if (!recognition || !currentCustomerId) return;

            if (isRecording) {
                recognition.stop();
            } else {
                try {
                    recognition.start();
                } catch (e) {
                    console.error("Error starting recognition:", e);
                    updateAgentStatus("Mic Error", "error");
                    addMessageToUI('Could not start microphone. Please check permissions.', 'bot-message');
                }
            }
        });
    }

    // --- Web Speech API for TTS (Text-to-Speech) ---
    function speak(text) {
        if ('speechSynthesis' in window) {
            speechSynthesis.cancel();
            const utterance = new SpeechSynthesisUtterance(text);
            utterance.lang = 'en-US';

            const voices = speechSynthesis.getVoices();
            let selectedVoice = null;

            if (voices.length > 0) {
                const preferredVoiceNames = [
                    "Google US English", "Microsoft Zira Desktop - English (United States)",
                    "Microsoft David Desktop - English (United States)", "Samantha",
                ];
                selectedVoice = voices.find(voice => preferredVoiceNames.includes(voice.name) && voice.lang === 'en-US');

                if (!selectedVoice) {
                    selectedVoice = voices.find(voice =>
                        voice.lang === 'en-US' && voice.localService &&
                        (voice.name.toLowerCase().includes('female') || !voice.name.toLowerCase().includes('male'))
                    );
                }
                if (!selectedVoice) {
                    selectedVoice = voices.find(voice => voice.name.toLowerCase().includes('google') && voice.lang === 'en-US');
                }
                if (!selectedVoice) {
                    selectedVoice = voices.find(voice => voice.lang === 'en-US' && voice.localService);
                }
                if (!selectedVoice) {
                    selectedVoice = voices.find(voice => voice.lang === 'en-US');
                }
            }

            if (selectedVoice) {
                utterance.voice = selectedVoice;
            }

            utterance.pitch = 1.0;
            utterance.rate = 0.95;
            utterance.volume = 1;

            utterance.onstart = () => updateAgentStatus("Speaking...", "speaking");
            utterance.onend = () => {
                if (currentCustomerId && !userInput.disabled) updateAgentStatus("Your turn.", "ready");
            };
            utterance.onerror = (event) => {
                console.error("Speech synthesis error:", event.error);
                updateAgentStatus("TTS Error", "error");
                addMessageToUI("I'm having trouble speaking right now. Please read my response.", "bot-message");
            };
            speechSynthesis.speak(utterance);
        } else {
            console.warn("Web Speech API (TTS) not supported in this browser.");
            addMessageToUI("It seems my voice synthesizer isn't available in your browser. Please read my responses.", "bot-message");
        }
    }

    // --- Customer Selection Logic ---
    customerSelect.addEventListener('change', () => {
        currentCustomerId = customerSelect.value;
        conversationHistory = [];
        chatBox.innerHTML = '';
        if (thinkingMessageElement) thinkingMessageElement = null;

        if (currentCustomerId) {
            const selectedCustomerText = customerSelect.options[customerSelect.selectedIndex].text;
            const customerNameMatch = selectedCustomerText.match(/^(.*?) \(/);
            const customerName = customerNameMatch ? customerNameMatch[1] : "Selected Customer";

            currentCustomerNameDisplay.textContent = customerName;
            updateAgentStatus(`Initializing for ${customerName}...`, "info");
            showMessagePlaceholder(false);
            toggleInputControls(false);

            // This greeting matches the one expected by the refined system prompt in app.py
            const initialBotMessage = `Hello, I'm FinBot from ${yourCompanyName}. I understand you're ${customerName}. How are you feeling today?`;
            addMessageToUI(initialBotMessage, 'bot-message');
            speak(initialBotMessage);
            conversationHistory.push({ role: "model", parts: [{ text: initialBotMessage }] });
            userInput.focus();
            updateAgentStatus("Ready to listen.", "ready");
        } else {
            currentCustomerNameDisplay.textContent = "N/A";
            updateAgentStatus("Awaiting Selection", "info");
            showMessagePlaceholder(true);
            toggleInputControls(true);
        }
    });

    // --- Chat Logic ---
    function addMessageToUI(text, sender, isThinking = false) {
        if (messagePlaceholder && messagePlaceholder.style.display !== 'none') {
            showMessagePlaceholder(false);
        }

        const messageElement = document.createElement('div');
        messageElement.classList.add('message', sender);
        if (isThinking) {
            messageElement.classList.add('thinking');
        }

        const avatarElement = document.createElement('div');
        avatarElement.classList.add('avatar');
        if (sender === 'bot-message') {
            avatarElement.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8V4H8"/><rect x="4" y="4" width="16" height="16" rx="2"/><path d="M12 12h4"/><path d="M12 16h4"/><path d="M8 12h.01"/><path d="M8 16h.01"/></svg>`;
        } else {
//            avatarElement.textContent = 'U';
        }
        messageElement.appendChild(avatarElement);

        const contentElement = document.createElement('div');
        contentElement.classList.add('content');
        const p = document.createElement('p');
        p.textContent = text;
        contentElement.appendChild(p);
        messageElement.appendChild(contentElement);

        chatBox.appendChild(messageElement);

        chatBox.parentElement.scrollTo({
            top: chatBox.parentElement.scrollHeight,
            behavior: 'smooth'
        });

        if (isThinking) {
            thinkingMessageElement = messageElement;
        }
    }

    async function sendMessage() {
        if (!currentCustomerId) {
            addMessageToUI("Please select a customer case first.", 'bot-message');
            speak("Please select a customer case first.");
            return;
        }
        const messageText = userInput.value.trim();
        if (messageText === '') return;

        addMessageToUI(messageText, 'user-message');
        userInput.value = '';
        toggleInputControls(true);

        if (thinkingMessageElement && thinkingMessageElement.parentNode === chatBox) {
            chatBox.removeChild(thinkingMessageElement);
            thinkingMessageElement = null;
        }
        addMessageToUI("Thinking how I can best help...", 'bot-message', true);
        updateAgentStatus("Considering your words...", "info");

        const historyForBackend = [...conversationHistory];

        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: messageText,
                    history: historyForBackend,
                    customerId: currentCustomerId
                }),
            });

            if (thinkingMessageElement && thinkingMessageElement.parentNode === chatBox) {
                chatBox.removeChild(thinkingMessageElement);
                thinkingMessageElement = null;
            }

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `Connection error: ${response.status}`);
            }

            const data = await response.json();
            const botResponse = data.response;

            addMessageToUI(botResponse, 'bot-message');
            speak(botResponse);

            conversationHistory.push({ role: "user", parts: [{ text: messageText }] });
            conversationHistory.push({ role: "model", parts: [{ text: botResponse }] });
            updateAgentStatus("Ready when you are.", "ready");

        } catch (error) {
            console.error('Error sending message:', error);
            if (thinkingMessageElement && thinkingMessageElement.parentNode === chatBox) {
                chatBox.removeChild(thinkingMessageElement);
                thinkingMessageElement = null;
            }
            addMessageToUI(`Error: ${error.message}. Please try again.`, 'bot-message');
            speak(`There was an error. ${error.message}.`);
            updateAgentStatus("Oops, a hiccup!", "error");
        } finally {
            if (currentCustomerId) toggleInputControls(false);
            userInput.focus();
        }
    }

    sendButton.addEventListener('click', sendMessage);
    userInput.addEventListener('keypress', (event) => {
        if (event.key === 'Enter' && !userInput.disabled) {
            sendMessage();
        }
    });

    // --- Theme Toggle Logic ---
    if (themeToggleButton) {
        themeToggleButton.addEventListener('click', () => {
            document.body.classList.toggle('dark-theme');
            if (document.body.classList.contains('dark-theme')) {
                localStorage.setItem('theme', 'dark');
            } else {
                localStorage.setItem('theme', 'light');
            }
        });

        const currentTheme = localStorage.getItem('theme');
        if (currentTheme === 'dark') {
            document.body.classList.add('dark-theme');
        }
    }

    // --- Initial Setup ---
    showMessagePlaceholder(true);
    toggleInputControls(true);
    updateAgentStatus("Awaiting Selection", "info");

    if ('speechSynthesis' in window) {
        const loadVoices = () => {
            // console.log("Voices available:", speechSynthesis.getVoices().length);
        };
        if (speechSynthesis.getVoices().length > 0) {
            loadVoices();
        } else {
            speechSynthesis.onvoiceschanged = loadVoices;
        }
    }
});

