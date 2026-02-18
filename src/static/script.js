/**
 * GarudaAI Frontend
 * Main application logic for chat interface
 */

// State
let currentModel = null;
let currentSessionId = null;
let isConnected = false;
let voiceEnabled = localStorage.getItem('voiceEnabled') !== 'false';
let recognitionActive = false;
let speechRecognition = null;

// DOM Elements
const app = {
    messages: document.getElementById('messages'),
    input: document.getElementById('message-input'),
    sendBtn: document.getElementById('send-btn'),
    modelSelector: document.getElementById('model-selector'),
    voiceBtn: document.getElementById('voice-btn'),
    settingsBtn: document.getElementById('settings-btn'),
    sidebar: document.getElementById('sidebar'),
    fileList: document.getElementById('file-list'),
    clearHistoryBtn: document.getElementById('clear-history-btn'),
    settingsModal: document.getElementById('settings-modal'),
    voiceToggle: document.getElementById('voice-toggle'),
    passwordBtn: document.getElementById('password-btn'),
    tabBtns: document.querySelectorAll('.tab-btn'),
    tabContents: document.querySelectorAll('.tab-content'),
};

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
    console.log('GarudaAI initializing...');
    
    // Load models
    await loadModels();
    
    // Setup event listeners
    setupEventListeners();
    
    // Load local settings
    loadSettings();
    
    // Setup speech recognition if available
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        setupSpeechRecognition();
    } else {
        app.voiceBtn.disabled = true;
    }
    
    // Create new session
    createNewSession();
    
    console.log('GarudaAI ready');
    addSystemMessage('Welcome to GarudaAI! Select a model and start chatting.');
});

/**
 * Load available models
 */
async function loadModels() {
    try {
        const response = await fetch('/api/models');
        const data = await response.json();
        const models = data.models || [];
        
        app.modelSelector.innerHTML = '';
        
        if (models.length === 0) {
            app.modelSelector.innerHTML = '<option>No models available</option>';
            return;
        }
        
        models.forEach(model => {
            const option = document.createElement('option');
            option.value = model.name;
            option.textContent = model.name;
            app.modelSelector.appendChild(option);
        });
        
        currentModel = models[0].name;
        app.modelSelector.value = currentModel;
        
    } catch (error) {
        console.error('Failed to load models:', error);
        app.modelSelector.innerHTML = '<option>Error loading models</option>';
    }
}

/**
 * Setup event listeners
 */
function setupEventListeners() {
    // Send button
    app.sendBtn.addEventListener('click', sendMessage);
    
    // Enter key
    app.input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    
    // Model selector
    app.modelSelector.addEventListener('change', (e) => {
        currentModel = e.target.value;
        createNewSession();
    });
    
    // Voice button
    app.voiceBtn.addEventListener('click', toggleVoiceInput);
    
    // Settings button
    app.settingsBtn.addEventListener('click', () => {
        app.settingsModal.style.display = 'block';
    });
    
    // Close modal
    document.querySelector('.btn-close').addEventListener('click', () => {
        app.settingsModal.style.display = 'none';
    });
    
    // Tab switching
    app.tabBtns.forEach(btn => {
        btn.addEventListener('click', (e) => {
            const tab = e.target.dataset.tab;
            switchTab(tab);
        });
    });
    
    // Clear history
    app.clearHistoryBtn.addEventListener('click', () => {
        if (confirm('Clear message history?')) {
            app.messages.innerHTML = '';
            createNewSession();
        }
    });
    
    // Settings toggles
    app.voiceToggle.addEventListener('change', (e) => {
        localStorage.setItem('voiceEnabled', e.target.checked ? 'true' : 'false');
        voiceEnabled = e.target.checked;
    });
    
    // Password button
    app.passwordBtn.addEventListener('click', updatePassword);
}

/**
 * Setup speech recognition
 */
function setupSpeechRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    speechRecognition = new SpeechRecognition();
    
    speechRecognition.continuous = false;
    speechRecognition.interimResults = false;
    speechRecognition.lang = 'en-US';
    
    speechRecognition.onresult = (event) => {
        const transcript = Array.from(event.results)
            .map(result => result[0].transcript)
            .join('');
        
        app.input.value = transcript;
        recognitionActive = false;
        updateVoiceButton();
    };
    
    speechRecognition.onerror = (event) => {
        console.error('Speech recognition error:', event.error);
        recognitionActive = false;
        updateVoiceButton();
    };
    
    speechRecognition.onend = () => {
        recognitionActive = false;
        updateVoiceButton();
    };
}

/**
 * Toggle voice input
 */
function toggleVoiceInput() {
    if (!voiceEnabled || !speechRecognition) return;
    
    if (recognitionActive) {
        speechRecognition.abort();
        recognitionActive = false;
    } else {
        recognitionActive = true;
        speechRecognition.start();
    }
    
    updateVoiceButton();
}

/**
 * Update voice button UI
 */
function updateVoiceButton() {
    if (recognitionActive) {
        app.voiceBtn.classList.add('active');
        app.voiceBtn.textContent = '🎤🔴';
    } else {
        app.voiceBtn.classList.remove('active');
        app.voiceBtn.textContent = '🎤';
    }
}

/**
 * Load local settings
 */
function loadSettings() {
    app.voiceToggle.checked = voiceEnabled;
}

/**
 * Switch tabs in sidebar
 */
function switchTab(tabName) {
    // Update buttons
    app.tabBtns.forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tabName);
    });
    
    // Update content
    app.tabContents.forEach(content => {
        content.style.display = content.id === `${tabName}-tab` ? 'block' : 'none';
    });
    
    // Load content if needed
    if (tabName === 'files') {
        loadFileList('/');
    }
}

/**
 * Send a message
 */
async function sendMessage() {
    const message = app.input.value.trim();
    
    if (!message || !currentModel) {
        return;
    }
    
    // Clear input
    app.input.value = '';
    app.input.style.height = 'auto';
    
    // Add user message to UI
    addUserMessage(message);
    
    // Show loading indicator
    const loadingId = addLoadingMessage();
    
    try {
        // Connect to WebSocket and stream response
        await streamChatResponse(message, loadingId);
    } catch (error) {
        console.error('Chat error:', error);
        updateMessage(loadingId, `Error: ${error.message}`);
    }
}

/**
 * Stream chat response via WebSocket
 */
async function streamChatResponse(message, loadingId) {
    return new Promise((resolve, reject) => {
        try {
            // Determine WebSocket protocol
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws/chat`;
            
            const ws = new WebSocket(wsUrl);
            
            ws.onopen = () => {
                // Send message
                ws.send(JSON.stringify({
                    model: currentModel,
                    message: message,
                    session_id: currentSessionId,
                    use_case: localStorage.getItem('useCase') || 'general',
                }));
            };
            
            ws.onmessage = (event) => {
                try {
                    if (event.data === '{"type":"done"}' || event.data.includes('"type":"done"')) {
                        ws.close();
                        resolve();
                    } else {
                        // Parse JSON or treat as plain text
                        let text = event.data;
                        try {
                            const json = JSON.parse(event.data);
                            if (json.type === 'error') {
                                text = `Error: ${json.message}`;
                            } else if (json.type === 'done') {
                                ws.close();
                                resolve();
                                return;
                            }
                        } catch (e) {
                            // Not JSON, treat as plain text token
                        }
                        
                        updateMessage(loadingId, text, true);
                    }
                } catch (error) {
                    console.error('Message parse error:', error);
                }
            };
            
            ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                reject(new Error('Connection failed'));
            };
            
            ws.onclose = () => {
                resolve();
            };
            
        } catch (error) {
            reject(error);
        }
    });
}

/**
 * Add user message to UI
 */
function addUserMessage(text) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message user-message';
    messageDiv.innerHTML = `<div class="message-content">${escapeHtml(text)}</div>`;
    app.messages.appendChild(messageDiv);
    scrollToBottom();
}

/**
 * Add assistant message (streaming)
 */
function addLoadingMessage() {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant-message';
    messageDiv.id = 'msg-' + Date.now();
    messageDiv.innerHTML = `<div class="message-content"><span class="typing-indicator">▪ ▪ ▪</span></div>`;
    app.messages.appendChild(messageDiv);
    scrollToBottom();
    return messageDiv.id;
}

/**
 * Update a message with streamed content
 */
function updateMessage(messageId, text, append = false) {
    const messageDiv = document.getElementById(messageId);
    if (!messageDiv) return;
    
    const content = messageDiv.querySelector('.message-content');
    
    if (append) {
        content.textContent = (content.textContent || '').replace('▪ ▪ ▪', '') + text;
    } else {
        content.textContent = text;
    }
    
    scrollToBottom();
}

/**
 * Add system message
 */
function addSystemMessage(text) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message system-message';
    messageDiv.innerHTML = `<div class="message-content">${escapeHtml(text)}</div>`;
    app.messages.appendChild(messageDiv);
    scrollToBottom();
}

/**
 * Create new session
 */
async function createNewSession() {
    try {
        const response = await fetch('/api/sessions', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({model_name: currentModel || 'neural-chat'})
        });
        const data = await response.json();
        currentSessionId = data.session_id;
    } catch (error) {
        currentSessionId = 'session-' + Date.now();
    }
    app.messages.innerHTML = '';
    addSystemMessage(`New session started`);
}

/**
 * Load session history
 */
async function loadSessionHistory() {
    try {
        const response = await fetch('/api/sessions');
        const data = await response.json();
        const sessions = data.sessions || [];
        
        const tabContent = document.querySelector('[data-tab="history"]');
        if (!tabContent) return;
        
        tabContent.innerHTML = '';
        
        if (sessions.length === 0) {
            tabContent.innerHTML = '<div style="padding: 20px; color: #999;">No session history yet</div>';
            return;
        }
        
        const list = document.createElement('div');
        sessions.forEach(session => {
            const div = document.createElement('div');
            div.className = 'history-item';
            div.style.padding = '12px';
            div.style.borderBottom = '1px solid #333';
            div.style.cursor = 'pointer';
            div.style.transition = 'background-color 0.2s';
            
            const date = new Date(session.last_accessed).toLocaleString();
            const summary = session.summary || `${session.model_name}`;
            
            div.innerHTML = `
                <strong>${summary}</strong>
                <br><small style="color: #999; font-size: 0.85em;">${date}</small>
            `;
            
            div.addEventListener('click', () => loadSession(session.session_id));
            div.addEventListener('mouseenter', () => div.style.backgroundColor = '#333');
            div.addEventListener('mouseleave', () => div.style.backgroundColor = 'transparent');
            list.appendChild(div);
        });
        
        tabContent.appendChild(list);
    } catch (error) {
        console.error('Failed to load history:', error);
    }
}

/**
 * Load and resume a session
 */
async function loadSession(sessionId) {
    try {
        const response = await fetch(`/api/sessions/${sessionId}`);
        const data = await response.json();
        
        currentSessionId = sessionId;
        currentModel = data.session.model_name;
        if (app.modelSelector) app.modelSelector.value = currentModel;
        app.messages.innerHTML = '';
        
        data.messages.forEach(msg => {
            if (msg.role === 'user') {
                addUserMessage(msg.content);
            } else {
                addAssistantMessage(msg.content);
            }
        });
        
        switchTab('chat');
    } catch (error) {
        console.error('Failed to load session:', error);
    }
}

/**
 * Load file list
 */
async function loadFileList(path) {
    try {
        // This would call the filesystem API in Phase 2
        app.fileList.innerHTML = '<div class="placeholder">File browser coming in Phase 2</div>';
    } catch (error) {
        console.error('Failed to load files:', error);
        app.fileList.innerHTML = '<div class="error">Error loading files</div>';
    }
}

/**
 * Update password
 */
async function updatePassword() {
    const password = document.getElementById('password-input').value;
    
    if (!password) {
        alert('Please enter a password');
        return;
    }
    
    try {
        // This would update the password in Phase 2
        alert('Password update coming in Phase 2');
    } catch (error) {
        alert('Error updating password: ' + error.message);
    }
}

/**
 * Utility: Scroll to bottom of messages
 */
function scrollToBottom() {
    setTimeout(() => {
        app.messages.scrollTop = app.messages.scrollHeight;
    }, 0);
}

/**
 * Utility: Escape HTML
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Utility: Auto-expand textarea
 */
app.input.addEventListener('input', (e) => {
    e.target.style.height = 'auto';
    e.target.style.height = Math.min(e.target.scrollHeight, 150) + 'px';
});
