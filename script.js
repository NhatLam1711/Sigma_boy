document.getElementById('input-text').addEventListener('input', function() {
    const inputText = this.value;
    document.getElementById('output-text').textContent = inputText;
});

document.addEventListener('DOMContentLoaded', () => {
    const messageForm = document.getElementById('message-form');
    const userInput = document.getElementById('user-input');
    const messagesContainer = document.getElementById('messages');
    const chatHistory = document.querySelector('.chat-history');
    const newChatButton = document.querySelector('.new-chat');

    let currentChatId = null;
    
    // Load existing chats
    loadChats();
    
    // Create new chat
    newChatButton.addEventListener('click', createNewChat);

    // Auto resize textarea
    userInput.addEventListener('input', () => {
        userInput.style.height = 'auto';
        userInput.style.height = userInput.scrollHeight + 'px';
    });

    messageForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const message = userInput.value.trim();
        
        if (message) {
            if (!currentChatId) {
                createNewChat();
            }
            
            // Add and save user message
            addMessage(message, 'user');
            saveMessage(currentChatId, message, 'user');
            
            userInput.value = '';
            userInput.style.height = 'auto';

            // Simulate bot response
            setTimeout(() => {
                const botResponse = 'This is a simulated response.';
                addMessage(botResponse, 'bot');
                saveMessage(currentChatId, botResponse, 'bot');
            }, 1000);
        }
    });

    function createNewChat() {
        currentChatId = Date.now().toString();
        const chat = {
            id: currentChatId,
            title: 'New Chat',
            messages: []
        };
        
        saveChat(chat);
        addChatToSidebar(chat);
        clearMessages();
    }

    function saveChat(chat) {
        const chats = getChats();
        chats[chat.id] = chat;
        localStorage.setItem('chats', JSON.stringify(chats));
    }

    function getChats() {
        return JSON.parse(localStorage.getItem('chats') || '{}');
    }

    function loadChats() {
        const chats = getChats();
        Object.values(chats).forEach(chat => {
            addChatToSidebar(chat);
        });
    }

    function addChatToSidebar(chat) {
        const chatElement = document.createElement('div');
        chatElement.classList.add('chat-item');
        chatElement.textContent = chat.title;
        chatElement.dataset.chatId = chat.id;
        chatElement.addEventListener('click', () => loadChat(chat.id));
        chatHistory.appendChild(chatElement);
    }

    function loadChat(chatId) {
        currentChatId = chatId;
        const chats = getChats();
        const chat = chats[chatId];
        
        if (chat) {
            clearMessages();
            chat.messages.forEach(msg => addMessage(msg.text, msg.sender));
        }
    }

    function addMessage(text, sender) {
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message', `${sender}-message`);
        messageDiv.textContent = text;
        messagesContainer.appendChild(messageDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    function saveMessage(chatId, text, sender) {
        const chats = getChats();
        const chat = chats[chatId];
        
        if (chat) {
            chat.messages.push({ text, sender, timestamp: Date.now() });
            if (chat.messages.length === 1) {
                chat.title = text.substring(0, 30) + '...';
                updateChatTitle(chatId, chat.title);
            }
            saveChat(chat);
        }
    }

    function updateChatTitle(chatId, title) {
        const chatElement = document.querySelector(`[data-chat-id="${chatId}"]`);
        if (chatElement) {
            chatElement.textContent = title;
        }
    }

    function clearMessages() {
        messagesContainer.innerHTML = '';
    }
});
