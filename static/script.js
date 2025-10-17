let sessionId = null;

document.getElementById('chat-form').addEventListener('submit', async function(event) {
    event.preventDefault();
    const questionInput = document.getElementById('question');
    const question = questionInput.value;
    if (!question.trim()) return;
    questionInput.value = '';

    const chatBody = document.getElementById('chat-body');

    const response = await fetch('/ask', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            question: question,
            session_id: sessionId
        })
    });

    const data = await response.json();
    sessionId = data.session_id;

    // Clear the chat body
    chatBody.innerHTML = '';

    // Render the chat history
    data.history.forEach(chat => {
        if (chat.role === 'user') {
            const userMessageContainer = document.createElement('div');
            userMessageContainer.className = 'message user';
            const userMessageBubble = document.createElement('div');
            userMessageBubble.className = 'message-bubble';
            userMessageBubble.textContent = chat.content;
            userMessageContainer.appendChild(userMessageBubble);
            chatBody.appendChild(userMessageContainer);
        } else if (chat.role === 'assistant') {
            const aiMessageContainer = document.createElement('div');
            aiMessageContainer.className = 'message ai';
            const aiAvatar = document.createElement('img');
            aiAvatar.className = 'avatar';
            aiAvatar.src = 'https://i.imgur.com/7a7yXVB.png'; // A generic AI avatar
            aiMessageContainer.appendChild(aiAvatar);
            const aiMessageBubble = document.createElement('div');
            aiMessageBubble.className = 'message-bubble';

            if (typeof chat.content === 'string') {
                aiMessageBubble.textContent = chat.content;
            } else {
                let html_response = "";
                if (chat.content.professional_greeting) {
                    html_response += `<p>${chat.content.professional_greeting.join(' ')}</p>`;
                }
                if (chat.content.direct_answer_addressing_the_query) {
                    html_response += `<p>${chat.content.direct_answer_addressing_the_query.join(' ')}</p>`;
                }
                if (chat.content.detailed_product_information_from_database) {
                    html_response += "<div class='product-info'>";
                    chat.content.detailed_product_information_from_database.forEach(item => {
                        if (item.includes('Image URL:')) {
                            const img_url = item.split('Image URL:')[1].trim();
                            html_response += `<img src="${img_url}" alt="Product Image">`;
                        } else {
                            html_response += `<p>${item}</p>`;
                        }
                    });
                    html_response += "</div>";
                }
                if (chat.content.relevant_additional_context) {
                    html_response += `<p>${chat.content.relevant_additional_context.join(' ')}</p>`;
                }
                if (chat.content.professional_closing) {
                    html_response += `<p>${chat.content.professional_closing.join(' ')}</p>`;
                }
                aiMessageBubble.innerHTML = html_response;
            }

            aiMessageContainer.appendChild(aiMessageBubble);
            chatBody.appendChild(aiMessageContainer);
        }
    });

    chatBody.scrollTop = chatBody.scrollHeight;
});