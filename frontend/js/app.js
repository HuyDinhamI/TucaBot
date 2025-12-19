// ============================================
// Configuration
// ============================================
const CONFIG = {
    API_BASE_URL: 'http://localhost:1112/mavap/api',
    STORAGE_KEYS: {
        SESSION_ID: 'mavap_session_id',
        CHAT_HISTORY: 'mavap_chat_history',
        THEME: 'mavap_theme',
        THINKING_COLLAPSED: 'mavap_thinking_collapsed'
    }
};

// ============================================
// State Management
// ============================================
class ChatState {
    constructor() {
        this.sessionId = this.getOrCreateSessionId();
        this.chatHistory = this.loadChatHistory();
        this.isStreaming = false;
        this.currentBotMessage = null;
        this.thinkingContent = '';
    }

    getOrCreateSessionId() {
        let sessionId = localStorage.getItem(CONFIG.STORAGE_KEYS.SESSION_ID);
        if (!sessionId) {
            sessionId = this.generateUUID();
            localStorage.setItem(CONFIG.STORAGE_KEYS.SESSION_ID, sessionId);
        }
        return sessionId;
    }

    generateUUID() {
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
            const r = Math.random() * 16 | 0;
            const v = c === 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
    }

    loadChatHistory() {
        try {
            const history = localStorage.getItem(CONFIG.STORAGE_KEYS.CHAT_HISTORY);
            return history ? JSON.parse(history) : [];
        } catch (e) {
            console.error('Error loading chat history:', e);
            return [];
        }
    }

    saveChatHistory() {
        try {
            localStorage.setItem(CONFIG.STORAGE_KEYS.CHAT_HISTORY, JSON.stringify(this.chatHistory));
        } catch (e) {
            console.error('Error saving chat history:', e);
        }
    }

    addMessage(role, content) {
        this.chatHistory.push({ role, content, timestamp: new Date().toISOString() });
        this.saveChatHistory();
    }

    clearHistory() {
        this.chatHistory = [];
        this.sessionId = this.generateUUID();
        localStorage.setItem(CONFIG.STORAGE_KEYS.SESSION_ID, this.sessionId);
        localStorage.removeItem(CONFIG.STORAGE_KEYS.CHAT_HISTORY);
    }
}

// ============================================
// UI Manager
// ============================================
class UIManager {
    constructor() {
        this.elements = {
            messagesContainer: document.getElementById('messagesContainer'),
            messageInput: document.getElementById('messageInput'),
            sendBtn: document.getElementById('sendBtn'),
            clearBtn: document.getElementById('clearBtn'),
            themeToggle: document.getElementById('themeToggle'),
            sessionId: document.getElementById('sessionId'),
            typingIndicator: document.getElementById('typingIndicator'),
            thinkingSection: document.getElementById('thinkingSection'),
            thinkingContent: document.getElementById('thinkingContent'),
            thinkingHeader: document.getElementById('thinkingHeader'),
            toggleThinking: document.getElementById('toggleThinking'),
            charCounter: document.getElementById('charCounter'),
            toast: document.getElementById('toast')
        };

        this.initializeTheme();
        this.initializeThinkingState();
    }

    initializeTheme() {
        const savedTheme = localStorage.getItem(CONFIG.STORAGE_KEYS.THEME) || 'light';
        document.documentElement.setAttribute('data-theme', savedTheme);
        this.updateThemeIcon(savedTheme);
    }

    initializeThinkingState() {
        const isCollapsed = localStorage.getItem(CONFIG.STORAGE_KEYS.THINKING_COLLAPSED) === 'true';
        if (isCollapsed) {
            this.elements.thinkingSection.classList.add('collapsed');
        }
    }

    toggleTheme() {
        const currentTheme = document.documentElement.getAttribute('data-theme');
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', newTheme);
        localStorage.setItem(CONFIG.STORAGE_KEYS.THEME, newTheme);
        this.updateThemeIcon(newTheme);
    }

    updateThemeIcon(theme) {
        const icon = this.elements.themeToggle.querySelector('.theme-icon');
        icon.textContent = theme === 'dark' ? '☀️' : '🌙';
    }

    toggleThinking() {
        this.elements.thinkingSection.classList.toggle('collapsed');
        const isCollapsed = this.elements.thinkingSection.classList.contains('collapsed');
        localStorage.setItem(CONFIG.STORAGE_KEYS.THINKING_COLLAPSED, isCollapsed);
    }

    showThinkingSection() {
        this.elements.thinkingSection.classList.remove('hidden');
    }

    hideThinkingSection() {
        this.elements.thinkingSection.classList.add('hidden');
    }

    clearThinkingContent() {
        this.elements.thinkingContent.innerHTML = '<div class="thinking-empty">Chưa có quá trình suy nghĩ...</div>';
    }

    appendToThinking(content) {
        if (this.elements.thinkingContent.querySelector('.thinking-empty')) {
            this.elements.thinkingContent.innerHTML = '';
        }
        const textNode = document.createTextNode(content);
        this.elements.thinkingContent.appendChild(textNode);
        this.elements.thinkingContent.scrollTop = this.elements.thinkingContent.scrollHeight;
    }

    addUserMessage(content) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message user';
        messageDiv.innerHTML = `
            <div class="message-avatar">👤</div>
            <div class="message-content">${this.escapeHtml(content)}</div>
        `;
        
        // Remove welcome message if exists
        const welcomeMsg = this.elements.messagesContainer.querySelector('.welcome-message');
        if (welcomeMsg) {
            welcomeMsg.remove();
        }
        
        this.elements.messagesContainer.appendChild(messageDiv);
        this.scrollToBottom();
    }

    createBotMessage() {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message bot';
        messageDiv.innerHTML = `
            <div class="message-avatar">🤖</div>
            <div class="message-content"></div>
        `;
        this.elements.messagesContainer.appendChild(messageDiv);
        this.scrollToBottom();
        return messageDiv.querySelector('.message-content');
    }

    appendToBotMessage(content, isMarkdown = true) {
        if (! this.currentBotMessageElement) {
            this.currentBotMessageElement = this.createBotMessage();
        }
        
        if (isMarkdown) {
            // Update with markdown
            const currentText = this.currentBotMessageElement.getAttribute('data-text') || '';
            const newText = currentText + content;
            this.currentBotMessageElement.setAttribute('data-text', newText);
            
            try {
                // Try to parse as markdown
                this.currentBotMessageElement.innerHTML = marked.parse(newText);
            } catch (e) {
                // Fallback:  preserve line breaks and basic formatting
                console.warn('Markdown parsing failed, using fallback', e);
                this.currentBotMessageElement.innerHTML = this.formatPlainText(newText);
            }
        } else {
            this.currentBotMessageElement.textContent += content;
        }
        
        this.scrollToBottom();
    }

    formatPlainText(text) {
        // Fallback formatter for plain text
        // Preserve line breaks and basic formatting
        return text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/\n/g, '<br>')
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')  // Bold
            .replace(/\*(.*? )\*/g, '<em>$1</em>');  // Italic
    }

    finalizeBotMessage() {
        this.currentBotMessageElement = null;
    }

    addWarningMessage(content) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message bot';
        messageDiv.innerHTML = `
            <div class="message-avatar">⚠️</div>
            <div class="message-content message-warning">${this.escapeHtml(content)}</div>
        `;
        this.elements.messagesContainer.appendChild(messageDiv);
        this.scrollToBottom();
    }

    showTypingIndicator() {
        this.elements.typingIndicator.style.display = 'flex';
        this.scrollToBottom();
    }

    hideTypingIndicator() {
        this.elements.typingIndicator.style.display = 'none';
    }

    clearMessages() {
        this.elements.messagesContainer.innerHTML = `
            <div class="welcome-message">
                <h2>Xin chào!  👋</h2>
                <p>Tôi là MAVAP Bot, trợ lý ảo của bạn.Hãy đặt câu hỏi để bắt đầu! </p>
            </div>
        `;
    }

    updateSessionId(sessionId) {
        this.elements.sessionId.textContent = `Session:  ${sessionId.substring(0, 8)}...`;
    }

    updateCharCounter(length, maxLength) {
        this.elements.charCounter.textContent = `${length} / ${maxLength}`;
    }

    showToast(message, duration = 3000) {
        this.elements.toast.textContent = message;
        this.elements.toast.classList.add('show');
        
        setTimeout(() => {
            this.elements.toast.classList.remove('show');
        }, duration);
    }

    setInputEnabled(enabled) {
        this.elements.messageInput.disabled = ! enabled;
        this.elements.sendBtn.disabled = !enabled;
    }

    scrollToBottom() {
        const container = document.querySelector('.chat-container');
        container.scrollTop = container.scrollHeight;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// ============================================
// API Manager
// ============================================
class APIManager {
    constructor(sessionId) {
        this.sessionId = sessionId;
    }

    async *streamChat(message) {
        const url = `${CONFIG.API_BASE_URL}/threads/${this.sessionId}/runs/stream`;
        
        const payload = {
            input: {
                messages: [
                    {
                        role: "user",
                        content: [
                            {
                                type: "text",
                                text: message
                            }
                        ]
                    }
                ]
            },
            config: {
                configurable: {
                    thread_id: this.sessionId,
                    current_time: new Date().toLocaleDateString('vi-VN')
                }
            }
        };

        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                
                if (done) break;
                
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const data = line.substring(6).trim();
                        if (data && data !== '[DONE]') {
                            try {
                                const event = JSON.parse(data);
                                yield event;
                            } catch (e) {
                                console.error('Error parsing event:', e, data);
                            }
                        }
                    }
                }
            }
        } catch (error) {
            console.error('Stream error:', error);
            throw error;
        }
    }
}

// ============================================
// Chat Manager
// ============================================
class ChatManager {
    constructor() {
        this.state = new ChatState();
        this.ui = new UIManager();
        this.api = new APIManager(this.state.sessionId);
        
        this.ui.updateSessionId(this.state.sessionId);
        this.loadChatHistory();
        this.setupEventListeners();
    }

    setupEventListeners() {
        // Send message
        this.ui.elements.sendBtn.addEventListener('click', () => this.sendMessage());
        this.ui.elements.messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        // Auto-resize textarea
        this.ui.elements.messageInput.addEventListener('input', (e) => {
            e.target.style.height = 'auto';
            e.target.style.height = Math.min(e.target.scrollHeight, 150) + 'px';
            this.ui.updateCharCounter(e.target.value.length, 10000);
        });

        // Clear conversation
        this.ui.elements.clearBtn.addEventListener('click', () => this.clearConversation());

        // Theme toggle
        this.ui.elements.themeToggle.addEventListener('click', () => this.ui.toggleTheme());

        // Thinking toggle
        this.ui.elements.thinkingHeader.addEventListener('click', () => this.ui.toggleThinking());
    }

    loadChatHistory() {
        if (this.state.chatHistory.length > 0) {
            this.ui.clearMessages();
            this.state.chatHistory.forEach(msg => {
                if (msg.role === 'user') {
                    this.ui.addUserMessage(msg.content);
                } else {
                    const contentEl = this.ui.createBotMessage();
                    contentEl.innerHTML = marked.parse(msg.content);
                }
            });
        }
    }

    async sendMessage() {
        const message = this.ui.elements. messageInput.value.trim();
        
        if (!message || this.state.isStreaming) {
            return;
        }

        // Add user message
        this.ui.addUserMessage(message);
        this.state.addMessage('user', message);

        // Clear input
        this.ui.elements.messageInput.value = '';
        this.ui.elements.messageInput.style.height = 'auto';
        this. ui.updateCharCounter(0, 10000);

        // Show typing indicator
        this.ui. showTypingIndicator();
        this.ui.setInputEnabled(false);
        this.state. isStreaming = true;

        // Clear thinking
        this.ui.clearThinkingContent();

        try {
            let botResponse = '';
            let isThinking = false;

            for await (const event of this.api.streamChat(message)) {
                // 🔍 DEBUG: Log all events
                console.log('📨 [EVENT]', {
                    type: event.event,
                    name: event.name,
                    node: event.metadata?.langgraph_node,
                    data:  event.data
                });

                this.ui.hideTypingIndicator();

                if (event.event === 'on_custom_event') {
                    if (event.name === 'on_think_event') {
                        isThinking = true;
                        this.ui.showThinkingSection();
                        const content = event.data?.chunk?.content || event.data?.text || '';
                        if (content) {
                            this.ui.appendToThinking(content);
                        }
                    } else if (event.name === 'on_answer_event') {
                        isThinking = false;
                        const content = event.data?.chunk?.content || event.data?.text || '';
                        if (content) {
                            // 🔍 DEBUG: Check for URLs in content
                            if (content.includes('http://') || content.includes('https://')) {
                                console.log('🔗 [LINK DETECTED]', content);
                            }
                            botResponse += content;
                            this.ui. appendToBotMessage(content);
                        }
                    } else if (event.name === 'on_blocked_event') {
                        const text = event.data?.chunk?.content || event.data?.text || 'Nội dung bị chặn';
                        this.ui.addWarningMessage(`🛑 ${text}`);
                    } else if (event.name === 'on_passed_event') {
                        // Nội dung đã được kiểm duyệt - không cần hiển thị
                        continue;
                    } else if (event.name === 'on_terminated_event') {
                        break;
                    } else {
                        // Handle other custom events from specific nodes
                        const metadata = event.metadata || {};
                        const node = metadata.langgraph_node;
                        
                        if (['ask_user', 'gather_user_information_agent', 'general_agent', 'answer_agent', 'document_agent'].includes(node)) {
                            const content = event.data?. chunk?.content || event.data?. text || '';
                            if (content) {
                                // 🔍 DEBUG: Check for URLs in content
                                if (content.includes('http://') || content.includes('https://')) {
                                    console.log('🔗 [LINK DETECTED in node]', node, content);
                                }
                                botResponse += content;
                                this.ui.appendToBotMessage(content);
                            }
                        }
                    }
                } else if (event.event === 'on_chat_model_stream') {
                    isThinking = false;
                    const content = event.data?.chunk?.content || '';
                    if (content) {
                        // 🔍 DEBUG: Check for URLs in content
                        if (content.includes('http://') || content.includes('https://')) {
                            console.log('🔗 [LINK DETECTED in stream]', content);
                        }
                        botResponse += content;
                        this.ui.appendToBotMessage(content);
                    }
                }
            }

            // Finalize bot message
            this.ui. finalizeBotMessage();
            if (botResponse) {
                // 🔍 DEBUG: Log final response with links
                const urlRegex = /(https?:\/\/[^\s]+)/g;
                const urls = botResponse.match(urlRegex);
                if (urls && urls.length > 0) {
                    console.log('🔗 [FINAL LINKS]', urls);
                    urls.forEach(url => {
                        console.log('  └─ ', url);
                    });
                }
                this.state.addMessage('assistant', botResponse);
            }

        } catch (error) {
            console.error('Error sending message:', error);
            this.ui.addWarningMessage('❌ Đã xảy ra lỗi khi gửi tin nhắn.Vui lòng thử lại.');
            this.ui.showToast('Lỗi kết nối đến server', 5000);
        } finally {
            this.ui.hideTypingIndicator();
            this.ui.setInputEnabled(true);
            this.state.isStreaming = false;
            this.ui.elements.messageInput.focus();
        }
    }

    clearConversation() {
        if (confirm('Bạn có chắc muốn xóa toàn bộ hội thoại?')) {
            this.state.clearHistory();
            this.ui.clearMessages();
            this.ui.clearThinkingContent();
            this.ui.hideThinkingSection();
            this.ui.updateSessionId(this.state.sessionId);
            this.api.sessionId = this.state.sessionId;
            this.ui.showToast('Đã xóa hội thoại và tạo phiên mới');
        }
    }
}

// ============================================
// Initialize App
// ============================================
document.addEventListener('DOMContentLoaded', () => {
    const chatManager = new ChatManager();
    console.log('MAVAP Chatbot initialized');
});
