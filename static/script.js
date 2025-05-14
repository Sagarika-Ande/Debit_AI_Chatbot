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
    let thinkingMessageElement = null;

    // --- New State Variables for MediaRecorder STT ---
    let mediaRecorder;
    let audioChunks = [];
    let isRecording = false;
    let currentPlayingAudio = null; // To manage TTS playback

    // --- Utility Functions (mostly same) ---
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
                case "speaking": // Server is "speaking" via client-side audio playback
                case "listening": // Client is listening via microphone
                    agentStatusDisplay.classList.add('status-speaking'); // Re-use 'speaking' style
                    break;
                default: // info
                    break;
            }
        }
    }

    function toggleInputControls(disabled) {
        userInput.disabled = disabled;
        sendButton.disabled = disabled;
        if (micButton) micButton.disabled = disabled || isRecording; // Disable mic if main input is disabled OR already recording

        userInput.style.opacity = disabled ? 0.7 : 1;
        sendButton.style.opacity = disabled ? 0.7 : 1;
        if (micButton) micButton.style.opacity = (disabled || isRecording) ? 0.7 : 1;
    }


    function showMessagePlaceholder(show) {
        if (messagePlaceholder) {
            messagePlaceholder.style.display = show ? 'flex' : 'none';
        }
    }

    // --- MediaRecorder STT Logic ---
    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        console.log('getUserMedia supported.');
        if (micButton) {
            micButton.addEventListener('click', async () => {
                if (!currentCustomerId) {
                    addMessageToUI("Please select a customer before using the microphone.", 'bot-message');
                    // No speak() here, as we're moving TTS to server
                    return;
                }

                if (isRecording) {
                    // Stop recording
                    mediaRecorder.stop();
                    micButton.classList.remove('recording');
                    micButton.querySelector('.mic-on-icon').style.display = 'block';
                    micButton.querySelector('.mic-off-icon').style.display = 'none';
                    updateAgentStatus("Processing audio...", "info");
                    toggleInputControls(true); // Disable while processing
                    isRecording = false;
                } else {
                    // Start recording
                    try {
                        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                        mediaRecorder = new MediaRecorder(stream);
                        audioChunks = []; // Reset chunks

                        mediaRecorder.ondataavailable = event => {
                            audioChunks.push(event.data);
                        };

                        mediaRecorder.onstart = () => {
                            isRecording = true;
                            micButton.classList.add('recording');
                            micButton.querySelector('.mic-on-icon').style.display = 'none';
                            micButton.querySelector('.mic-off-icon').style.display = 'block';
                            updateAgentStatus("Listening...", "listening");
                            toggleInputControls(true); // Disable other inputs
                            if (micButton) micButton.disabled = false; // Keep mic button enabled to stop
                        };

                        mediaRecorder.onstop = async () => {
                            isRecording = false; // ensure this is false before async operations
                            updateAgentStatus("Transcribing...", "info");
                            const audioBlob = new Blob(audioChunks, { type: 'audio/webm' }); // Adjust type if necessary
                            audioChunks = []; // Clear for next recording

                            // Release microphone track
                            stream.getTracks().forEach(track => track.stop());

                            const formData = new FormData();
                            formData.append('audio_data', audioBlob, 'user_audio.webm');

                            try {
                                const response = await fetch('/transcribe', {
                                    method: 'POST',
                                    body: formData
                                });
                                if (!response.ok) {
                                    const errorData = await response.json();
                                    throw new Error(errorData.error || `Transcription failed: ${response.status}`);
                                }
                                const data = await response.json();
                                userInput.value = data.transcript;
                                updateAgentStatus("Transcription complete!", "info");
                                if (currentCustomerId) toggleInputControls(false);
                                // Optionally, auto-send the message:
                                // if (data.transcript.trim() !== "") sendMessage();
                                // else updateAgentStatus("Ready.", "ready");
                                updateAgentStatus("Ready.", "ready");


                            } catch (error) {
                                console.error('Transcription error:', error);
                                addMessageToUI(`STT Error: ${error.message}. Please type.`, 'bot-message');
                                updateAgentStatus("STT Error", "error");
                                if (currentCustomerId) toggleInputControls(false);
                            }
                        };
                        mediaRecorder.start();
                    } catch (err) {
                        console.error('Error accessing microphone:', err);
                        addMessageToUI('Microphone access denied or error. Please check permissions and try again.', 'bot-message');
                        updateAgentStatus("Mic access error", "error");
                        if (currentCustomerId) toggleInputControls(false);
                    }
                }
            });
        }
    } else {
        console.warn("MediaRecorder API not supported in this browser.");
        if (micButton) micButton.style.display = 'none';
    }


    // --- TTS (Text-to-Speech) via Server ---
    function playAudio(audioBase64, audioFormat = "wav") {
        if (currentPlayingAudio) {
            currentPlayingAudio.pause();
            currentPlayingAudio.currentTime = 0;
        }
        try {
            const audioSrc = `data:audio/${audioFormat};base64,${audioBase64}`;
            currentPlayingAudio = new Audio(audioSrc);
            currentPlayingAudio.play()
                .then(() => {
                    updateAgentStatus("Speaking...", "speaking");
                })
                .catch(e => {
                    console.error("Error playing audio:", e);
                    updateAgentStatus("TTS Playback Error", "error");
                    addMessageToUI("I'm having trouble playing my voice. Please read my response.", "bot-message");
                });

            currentPlayingAudio.onended = () => {
                if (currentCustomerId && !userInput.disabled && !isRecording) {
                     updateAgentStatus("Your turn.", "ready");
                }
                currentPlayingAudio = null;
            };
            currentPlayingAudio.onerror = (e) => {
                console.error("Audio element error:", e);
                updateAgentStatus("TTS Error", "error");
                 addMessageToUI("Error with audio playback.", "bot-message");
                currentPlayingAudio = null;
            };

        } catch (error) {
            console.error("Error setting up audio for playback:", error);
            updateAgentStatus("TTS Setup Error", "error");
            addMessageToUI("Could not prepare audio. Please read my response.", "bot-message");
        }
    }


    // --- Customer Selection Logic ---
    customerSelect.addEventListener('change', () => {
        currentCustomerId = customerSelect.value;
        conversationHistory = [];
        chatBox.innerHTML = '';
        if (thinkingMessageElement) thinkingMessageElement = null;
        if (currentPlayingAudio) {
            currentPlayingAudio.pause();
            currentPlayingAudio = null;
        }


        if (currentCustomerId) {
            const selectedCustomerText = customerSelect.options[customerSelect.selectedIndex].text;
            const customerNameMatch = selectedCustomerText.match(/^(.*?) \(/);
            const customerName = customerNameMatch ? customerNameMatch[1] : "Selected Customer";

            currentCustomerNameDisplay.textContent = customerName;
            updateAgentStatus(`Initializing for ${customerName}...`, "info");
            showMessagePlaceholder(false);
            // toggleInputControls(false); // Enable controls after greeting

            // The initial bot message will now also trigger TTS from server.
            // To do this, we can simulate a "chat" call for the greeting or have a dedicated endpoint.
            // For simplicity, let's make the first message part of the normal chat flow, but originating from the bot.
            // OR, easier: client displays it, and requests audio for it.
            // Let's make it part of the system prompt logic for the *very first* interaction.
            // The prompt in app.py defines this first message. The client will show it, and then we'll fetch audio.

            const initialBotMessage = `Hello, I'm FinBot from ${yourCompanyName}. I understand you're ${customerName}. How are you feeling today?`;
            addMessageToUI(initialBotMessage, 'bot-message');
            conversationHistory.push({ role: "model", parts: [{ text: initialBotMessage }] }); // Add to history

            // Fetch audio for the initial greeting
            // This requires the greeting text to be sent to an endpoint that returns audio
            // OR, we can assume the /chat endpoint is robust enough if we send it a "system" message
            // For now, let's directly call a modified /chat or a new /tts endpoint.
            // Simpler: modify `sendMessage` to handle initial greeting audio.
            // For now, let's make the greeting only text on init, and first *user* interaction gets audio response.
            // A better UX would be to get audio for this greeting immediately.

            // For now, let's skip TTS for the initial canned greeting and let the first *response* from the bot have audio.
            // If you want TTS for the initial greeting, you'd need an extra fetch here to a TTS endpoint or make /chat handle it.

            // Let's make the first bot message have audio by faking a message to the backend that just returns this known greeting + audio
            // This is a bit of a hack. A dedicated endpoint /get_greeting_audio?customerId=... would be cleaner.
            // For now, let's stick to text-only for this specific auto-greeting to keep it simpler.
            // The user's first message will trigger a response with audio.

            userInput.focus();
            updateAgentStatus("Ready to listen.", "ready");
            toggleInputControls(false); // Enable input after greeting is shown

        } else {
            currentCustomerNameDisplay.textContent = "N/A";
            updateAgentStatus("Awaiting Selection", "info");
            showMessagePlaceholder(true);
            toggleInputControls(true);
        }
    });

    // --- Chat Logic (addMessageToUI is mostly the same) ---
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
            // No client-side speak()
            return;
        }
        const messageText = userInput.value.trim();
        if (messageText === '') return;

        addMessageToUI(messageText, 'user-message');
        userInput.value = '';
        toggleInputControls(true);
        if (currentPlayingAudio) { // Stop any ongoing TTS from previous turn
            currentPlayingAudio.pause();
            currentPlayingAudio.currentTime = 0;
        }

        if (thinkingMessageElement && thinkingMessageElement.parentNode === chatBox) {
            chatBox.removeChild(thinkingMessageElement);
            thinkingMessageElement = null;
        }
        addMessageToUI("Thinking how I can best help...", 'bot-message', true);
        updateAgentStatus("Consulting the digital brain...", "info");


        const historyForBackend = [...conversationHistory];
        // The very first "model" message (greeting) is already in conversationHistory if customer selected

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
                // The error response from Flask might also contain audio_base64
                if (errorData.response) { // Display the text part of the error
                     addMessageToUI(errorData.response, 'bot-message');
                } else {
                     addMessageToUI(errorData.error || `Connection error: ${response.status}`, 'bot-message');
                }
                if (errorData.audio_base64) {
                    playAudio(errorData.audio_base64, errorData.audio_format || 'wav');
                }
                throw new Error(errorData.error || `Chat API error: ${response.status}`);
            }

            const data = await response.json();
            const botResponse = data.response;
            const audioBase64 = data.audio_base64;
            const audioFormat = data.audio_format || "wav";

            addMessageToUI(botResponse, 'bot-message');
            if (audioBase64) {
                playAudio(audioBase64, audioFormat); // This will update status to "Speaking..."
            } else {
                 updateAgentStatus("Ready when you are.", "ready"); // If no audio, go to ready
            }


            conversationHistory.push({ role: "user", parts: [{ text: messageText }] });
            conversationHistory.push({ role: "model", parts: [{ text: botResponse }] });
            // Status will be updated by playAudio on end/error or above if no audio

        } catch (error) {
            console.error('Error sending message:', error);
            // Error message already added to UI if it was a response error
            if (!(error.message.startsWith("Chat API error") || error.message.startsWith("Connection error"))) {
                // Only add generic error if not already handled by specific API error
                if (thinkingMessageElement && thinkingMessageElement.parentNode === chatBox) {
                    chatBox.removeChild(thinkingMessageElement);
                    thinkingMessageElement = null;
                }
                addMessageToUI(`Error: ${error.message}. Please try again.`, 'bot-message');
            }
            updateAgentStatus("Oops, a hiccup!", "error");
        } finally {
            // Only enable controls if not currently recording or speaking
            if (currentCustomerId && !isRecording && !currentPlayingAudio) {
                 toggleInputControls(false);
            } else if (currentCustomerId && !isRecording && currentPlayingAudio) {
                // Controls will be re-enabled when audio finishes.
                // Keep user input disabled, but mic enabled if not recording
                userInput.disabled = true;
                sendButton.disabled = true;
                if (micButton) micButton.disabled = isRecording;
            }
            userInput.focus();
        }
    }

    sendButton.addEventListener('click', sendMessage);
    userInput.addEventListener('keypress', (event) => {
        if (event.key === 'Enter' && !userInput.disabled) {
            sendMessage();
        }
    });

    // --- Theme Toggle Logic (same) ---
    if (themeToggleButton) {
        themeToggleButton.addEventListener('click', () => {
            document.body.classList.toggle('dark-theme');
            localStorage.setItem('theme', document.body.classList.contains('dark-theme') ? 'dark' : 'light');
        });
        if (localStorage.getItem('theme') === 'dark') {
            document.body.classList.add('dark-theme');
        }
    }

    // --- Initial Setup ---
    showMessagePlaceholder(true);
    toggleInputControls(true);
    updateAgentStatus("Awaiting Selection", "info");
    if(micButton) { // Ensure mic icons are correctly set initially
        micButton.querySelector('.mic-on-icon').style.display = 'block';
        micButton.querySelector('.mic-off-icon').style.display = 'none';
    }
});

