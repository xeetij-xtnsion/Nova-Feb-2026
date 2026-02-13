from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/demo", response_class=HTMLResponse)
async def demo_ui():
    """
    Demo UI for testing the RAG system.

    Patient-friendly chat interface with quick action buttons.
    """
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Nova Clinic - Chat Assistant</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            .container {
                max-width: 900px;
                margin: 0 auto;
                background: white;
                border-radius: 16px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                overflow: hidden;
                display: flex;
                flex-direction: column;
                height: 90vh;
            }
            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 24px;
                text-align: center;
            }
            .header h1 {
                font-size: 28px;
                margin-bottom: 8px;
            }
            .header p {
                font-size: 15px;
                opacity: 0.95;
            }
            .chat-container {
                flex: 1;
                overflow-y: auto;
                padding: 24px;
                background: #f9fafb;
            }
            .message {
                margin-bottom: 24px;
                animation: fadeIn 0.4s ease-in;
            }
            @keyframes fadeIn {
                from { opacity: 0; transform: translateY(10px); }
                to { opacity: 1; transform: translateY(0); }
            }
            .message.user {
                text-align: right;
            }
            .message-content {
                display: inline-block;
                max-width: 75%;
                padding: 14px 18px;
                border-radius: 18px;
                word-wrap: break-word;
                line-height: 1.5;
            }
            .message.user .message-content {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border-bottom-right-radius: 4px;
            }
            .message.assistant .message-content {
                background: white;
                color: #1f2937;
                border: 1px solid #e5e7eb;
                text-align: left;
                border-bottom-left-radius: 4px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            }
            .confidence-badge {
                display: inline-block;
                padding: 4px 10px;
                border-radius: 12px;
                font-size: 11px;
                font-weight: 600;
                margin-top: 10px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            .confidence-high {
                background: #d1fae5;
                color: #065f46;
            }
            .confidence-low {
                background: #fee2e2;
                color: #991b1b;
            }
            .citations {
                margin-top: 16px;
                padding: 14px;
                background: #f3f4f6;
                border-radius: 12px;
                font-size: 13px;
                border-left: 3px solid #667eea;
            }
            .citations h4 {
                font-size: 11px;
                color: #6b7280;
                margin-bottom: 10px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                font-weight: 600;
            }
            .citation-item {
                padding: 8px 0;
                border-bottom: 1px solid #e5e7eb;
                color: #4b5563;
            }
            .citation-item:last-child {
                border-bottom: none;
            }
            .citation-item strong {
                color: #667eea;
                font-weight: 600;
            }
            .feedback-buttons {
                margin-top: 12px;
            }
            .feedback-btn {
                background: white;
                border: 2px solid #e5e7eb;
                padding: 8px 16px;
                margin-right: 8px;
                border-radius: 20px;
                cursor: pointer;
                font-size: 16px;
                transition: all 0.2s;
            }
            .feedback-btn:hover {
                background: #f9fafb;
                transform: translateY(-1px);
                border-color: #667eea;
            }
            .feedback-btn.active-up {
                background: #d1fae5;
                border-color: #10b981;
            }
            .feedback-btn.active-down {
                background: #fee2e2;
                border-color: #ef4444;
            }
            .quick-actions {
                padding: 20px 24px;
                background: white;
                border-top: 1px solid #e5e7eb;
            }
            .quick-actions h3 {
                font-size: 13px;
                color: #6b7280;
                margin-bottom: 12px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            .button-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
                gap: 10px;
            }
            .quick-btn {
                background: white;
                border: 2px solid #e5e7eb;
                padding: 12px 16px;
                border-radius: 12px;
                cursor: pointer;
                font-size: 14px;
                font-weight: 500;
                color: #374151;
                transition: all 0.2s;
                text-align: center;
            }
            .quick-btn:hover {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border-color: transparent;
                transform: translateY(-2px);
                box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
            }
            .input-container {
                padding: 20px 24px;
                background: white;
                border-top: 1px solid #e5e7eb;
                display: flex;
                gap: 12px;
            }
            #questionInput {
                flex: 1;
                padding: 14px 18px;
                border: 2px solid #e5e7eb;
                border-radius: 24px;
                font-size: 15px;
                outline: none;
                transition: all 0.2s;
                font-family: inherit;
            }
            #questionInput:focus {
                border-color: #667eea;
                box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
            }
            #sendButton {
                padding: 14px 28px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                border-radius: 24px;
                cursor: pointer;
                font-size: 15px;
                font-weight: 600;
                transition: all 0.2s;
                box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
            }
            #sendButton:hover {
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
            }
            #sendButton:active {
                transform: translateY(0);
            }
            #sendButton:disabled {
                opacity: 0.6;
                cursor: not-allowed;
                transform: none;
            }
            .loading {
                display: inline-block;
                width: 16px;
                height: 16px;
                border: 2px solid white;
                border-radius: 50%;
                border-top-color: transparent;
                animation: spin 0.6s linear infinite;
            }
            @keyframes spin {
                to { transform: rotate(360deg); }
            }
            .typing-indicator {
                display: inline-block;
                padding: 14px 18px;
                background: white;
                border-radius: 18px;
                border-bottom-left-radius: 4px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            }
            .typing-indicator span {
                height: 8px;
                width: 8px;
                background: #9ca3af;
                border-radius: 50%;
                display: inline-block;
                margin: 0 2px;
                animation: bounce 1.4s infinite ease-in-out both;
            }
            .typing-indicator span:nth-child(1) { animation-delay: -0.32s; }
            .typing-indicator span:nth-child(2) { animation-delay: -0.16s; }
            @keyframes bounce {
                0%, 80%, 100% { transform: scale(0); }
                40% { transform: scale(1); }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🏥 Nova Clinic Assistant</h1>
                <p>Hi! I'm Nova, your friendly clinic assistant. How can I help you today?</p>
            </div>

            <div class="chat-container" id="chatContainer">
                <div class="message assistant">
                    <div class="message-content">
                        👋 Welcome! I'm here to help you learn about our services, book appointments, and answer any questions about Nova Clinic. What would you like to know?
                    </div>
                </div>
            </div>

            <div class="quick-actions">
                <h3>🎯 Quick Questions</h3>
                <div class="button-grid">
                    <button class="quick-btn" onclick="askQuestion('What services do you offer?')">Our Services</button>
                    <button class="quick-btn" onclick="askQuestion('Tell me about acupuncture')">Acupuncture</button>
                    <button class="quick-btn" onclick="askQuestion('What is naturopathic medicine?')">Naturopathy</button>
                    <button class="quick-btn" onclick="askQuestion('Do you offer massage therapy?')">Massage</button>
                    <button class="quick-btn" onclick="askQuestion('How do I book an appointment?')">Book Appointment</button>
                    <button class="quick-btn" onclick="askQuestion('What are your hours?')">Clinic Hours</button>
                </div>
            </div>

            <div class="input-container">
                <input
                    type="text"
                    id="questionInput"
                    placeholder="Type your question here..."
                    onkeypress="if(event.key==='Enter') sendMessage()"
                />
                <button id="sendButton" onclick="sendMessage()">Send</button>
            </div>
        </div>

        <script>
            let currentSessionId = null;
            let lastResponse = null;

            function askQuestion(question) {
                document.getElementById('questionInput').value = question;
                sendMessage();
            }

            async function sendMessage() {
                const input = document.getElementById('questionInput');
                const question = input.value.trim();

                if (!question) return;

                // Disable input
                const sendButton = document.getElementById('sendButton');
                input.disabled = true;
                sendButton.disabled = true;
                sendButton.innerHTML = '<span class="loading"></span>';

                // Add user message
                addMessage(question, 'user');
                input.value = '';

                // Show typing indicator
                const typingId = addTypingIndicator();

                try {
                    // Call chat API
                    const response = await fetch('/chat', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            message: question,
                            session_id: currentSessionId
                        })
                    });

                    if (!response.ok) {
                        throw new Error('Failed to get response');
                    }

                    const data = await response.json();

                    // Store session ID
                    if (data.session_id) {
                        currentSessionId = data.session_id;
                    }

                    // Store last response for feedback
                    lastResponse = {
                        question: question,
                        answer: data.answer,
                        citations: data.citations
                    };

                    // Remove typing indicator
                    removeTypingIndicator(typingId);

                    // Add assistant message
                    addMessage(data.answer, 'assistant', data.citations, data.confidence, data.max_similarity);

                } catch (error) {
                    console.error('Error:', error);
                    removeTypingIndicator(typingId);
                    addMessage('Sorry, I had trouble connecting. Please try again in a moment! 😊', 'assistant');
                } finally {
                    // Re-enable input
                    input.disabled = false;
                    sendButton.disabled = false;
                    sendButton.textContent = 'Send';
                    input.focus();
                }
            }

            function addTypingIndicator() {
                const container = document.getElementById('chatContainer');
                const messageDiv = document.createElement('div');
                messageDiv.className = 'message assistant';
                messageDiv.id = 'typing-indicator-' + Date.now();
                messageDiv.innerHTML = '<div class="typing-indicator"><span></span><span></span><span></span></div>';
                container.appendChild(messageDiv);
                container.scrollTop = container.scrollHeight;
                return messageDiv.id;
            }

            function removeTypingIndicator(id) {
                const indicator = document.getElementById(id);
                if (indicator) {
                    indicator.remove();
                }
            }

            function addMessage(text, sender, citations = [], confidence = null, maxSimilarity = null) {
                const container = document.getElementById('chatContainer');
                const messageDiv = document.createElement('div');
                messageDiv.className = `message ${sender}`;

                let html = `<div class="message-content">${escapeHtml(text)}`;

                if (confidence && sender === 'assistant') {
                    const confClass = confidence === 'high' ? 'confidence-high' : 'confidence-low';
                    const confText = confidence === 'high' ? '✓ Verified' : '⚠ Limited Info';
                    html += `<br><span class="confidence-badge ${confClass}">${confText}</span>`;
                }

                if (citations && citations.length > 0) {
                    html += '<div class="citations"><h4>📚 Sources</h4>';
                    citations.forEach(c => {
                        html += `<div class="citation-item">
                            <strong>${escapeHtml(c.section_heading)}</strong>
                        </div>`;
                    });
                    html += '</div>';
                }

                if (sender === 'assistant') {
                    html += `<div class="feedback-buttons">
                        <button class="feedback-btn" onclick="submitFeedback(1, this)" title="Helpful">👍</button>
                        <button class="feedback-btn" onclick="submitFeedback(-1, this)" title="Not helpful">👎</button>
                    </div>`;
                }

                html += '</div>';
                messageDiv.innerHTML = html;
                container.appendChild(messageDiv);
                container.scrollTop = container.scrollHeight;
            }

            async function submitFeedback(rating, button) {
                if (!lastResponse) return;

                // Disable both buttons
                const buttons = button.parentElement.querySelectorAll('.feedback-btn');
                buttons.forEach(btn => btn.disabled = true);

                // Highlight clicked button
                button.classList.add(rating > 0 ? 'active-up' : 'active-down');

                try {
                    const response = await fetch('/feedback', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            session_id: currentSessionId,
                            question: lastResponse.question,
                            answer: lastResponse.answer,
                            citations: lastResponse.citations,
                            rating: rating
                        })
                    });

                    if (response.ok) {
                        console.log('Feedback submitted successfully');
                    }
                } catch (error) {
                    console.error('Error submitting feedback:', error);
                }
            }

            function escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }

            // Focus input on load
            document.getElementById('questionInput').focus();
        </script>
    </body>
    </html>
    """
    return html_content
