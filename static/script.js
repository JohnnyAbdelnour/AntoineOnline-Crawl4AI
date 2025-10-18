let sessionId = null;

document.getElementById('chat-form').addEventListener('submit', async function(event) {
    event.preventDefault();
    const questionInput = document.getElementById('question');
    const question = questionInput.value;
    if (!question.trim()) return;

    const chatBody = document.getElementById('chat-body');

    // Display user's message immediately
    appendMessage(chatBody, 'user', question);
    questionInput.value = '';
    chatBody.scrollTop = chatBody.scrollHeight;

    // Show a typing indicator
    const typingIndicator = appendMessage(chatBody, 'ai', '...');
    chatBody.scrollTop = chatBody.scrollHeight;

    try {
        const payload = { question: question };
        if (sessionId) {
            payload.session_id = sessionId;
        }

        const response = await fetch('/ask', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const errorData = await response.json();
            console.error('Server error:', JSON.stringify(errorData, null, 2));
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        sessionId = data.session_id;

        // Get the last message from the history, which is the AI's response
        const aiMessage = data.history[data.history.length - 1];

        // Remove typing indicator
        chatBody.removeChild(typingIndicator);

        // Display the final AI response
        if (aiMessage && aiMessage.role === 'assistant') {
            appendMessage(chatBody, 'ai', aiMessage.content, true);
        } else {
            appendMessage(chatBody, 'ai', "Sorry, I couldn't get a response.", false);
        }

    } catch (error) {
        console.error('Fetch error:', error);
        // Remove typing indicator and show error
        if (typingIndicator) {
            chatBody.removeChild(typingIndicator);
        }
        appendMessage(chatBody, 'ai', 'Error: Could not connect to the server. Please try again.', false);
    } finally {
        chatBody.scrollTop = chatBody.scrollHeight;
    }
});

function appendMessage(chatBody, role, content, parseMarkdown = false) {
    const messageContainer = document.createElement('div');
    messageContainer.className = `message ${role}`;

    if (role === 'ai') {
        const avatar = document.createElement('img');
        avatar.className = 'avatar';
        avatar.src = 'https://i.imgur.com/7a7yXVB.png'; // AI avatar
        messageContainer.appendChild(avatar);
    }

    const messageBubble = document.createElement('div');
    messageBubble.className = 'message-bubble';

    if (parseMarkdown) {
        messageBubble.innerHTML = marked.parse(content);
    } else {
        messageBubble.textContent = content;
    }

    messageContainer.appendChild(messageBubble);
    chatBody.appendChild(messageContainer);

    // Find and style images within the bubble
    const images = messageBubble.querySelectorAll('img');
    images.forEach(img => {
        img.style.maxWidth = '100%';
        img.style.borderRadius = '8px';
        img.style.marginTop = '10px';
    });

    return messageContainer;
}