/**
 * GarudaAI Frontend
 * Mobile-first chat interface with WebSocket streaming, markdown, auth, sessions,
 * camera vision, SOUL.md persona, RAG documents, TTS, STT, export.
 */

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let currentModel = null;
let currentSessionId = null;
let voiceEnabled = localStorage.getItem('voiceEnabled') !== 'false';
let ttsEnabled = localStorage.getItem('ttsEnabled') === 'true';
let recognitionActive = false;
let speechRecognition = null;
let authToken = localStorage.getItem('garudaai_token') || '';
let pendingImage = null;  // base64 image from camera

const isMobile = () => window.innerWidth <= 768 || 'ontouchstart' in window;

// ---------------------------------------------------------------------------
// DOM refs
// ---------------------------------------------------------------------------
const app = {
    messages:        document.getElementById('messages'),
    input:           document.getElementById('message-input'),
    sendBtn:         document.getElementById('send-btn'),
    modelSelector:   document.getElementById('model-selector'),
    voiceBtn:        document.getElementById('voice-btn'),
    settingsBtn:     document.getElementById('settings-btn'),
    sidebar:         document.getElementById('sidebar'),
    sidebarBackdrop: document.getElementById('sidebar-backdrop'),
    clearHistoryBtn: document.getElementById('new-session-btn'),
    voiceToggle:     document.getElementById('voice-toggle'),
    ttsToggle:       document.getElementById('tts-toggle'),
    passwordBtn:     document.getElementById('password-btn'),
    tabBtns:         document.querySelectorAll('.tab-btn'),
    tabContents:     document.querySelectorAll('.tab-content'),
    connStatus:      document.getElementById('conn-status'),
    slowBadge:       document.getElementById('slow-mode-badge'),
    sidebarToggle:   document.getElementById('sidebar-toggle-btn'),
    sidebarClose:    document.getElementById('sidebar-close-btn'),
    loginOverlay:    document.getElementById('login-overlay'),
    loginPassword:   document.getElementById('login-password'),
    loginBtn:        document.getElementById('login-btn'),
    loginError:      document.getElementById('login-error'),
    cameraBtn:       document.getElementById('camera-btn'),
    imagePreviewArea:document.getElementById('image-preview-area'),
    previewImg:      document.getElementById('preview-img'),
    removeImgBtn:    document.getElementById('remove-img-btn'),
    soulTextarea:    document.getElementById('soul-textarea'),
    soulSaveBtn:     document.getElementById('soul-save-btn'),
    ragFileInput:    document.getElementById('rag-file-input'),
    ragStatus:       document.getElementById('rag-status'),
    ragDocList:      document.getElementById('rag-doc-list'),
    exportBtn:       document.getElementById('export-btn'),
};

// ---------------------------------------------------------------------------
// Initialization
// ---------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', async () => {
    loadSettings();

    const ok = await tryLoadModels();
    if (!ok) {
        showLoginOverlay();
        return;
    }
    finishInit();
});

async function finishInit() {
    setupEventListeners();
    setupVisualViewport();
    setupSpeechRecognition();
    await createNewSession();
    const hint = isMobile() ? 'Tap Send to chat.' : 'Press Enter or click Send to chat.';
    addSystemMessage(`Welcome to GarudaAI! ${hint}`);
    loadSoul();
    loadRagDocs();
}

// ---------------------------------------------------------------------------
// Virtual viewport — keep input visible when keyboard opens (iOS/Android)
// ---------------------------------------------------------------------------
function setupVisualViewport() {
    if (!window.visualViewport) return;
    const container = document.querySelector('.app-container');
    const onResize = () => {
        if (isMobile()) {
            container.style.height = window.visualViewport.height + 'px';
        } else {
            container.style.height = '';
        }
    };
    window.visualViewport.addEventListener('resize', onResize);
    window.visualViewport.addEventListener('scroll', onResize);
    onResize();
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------
function showLoginOverlay() {
    app.loginOverlay.style.display = 'flex';
    setTimeout(() => app.loginPassword && app.loginPassword.focus(), 50);
}
function hideLoginOverlay() { app.loginOverlay.style.display = 'none'; }

async function doLogin() {
    const password = app.loginPassword.value;
    app.loginError.textContent = '';
    app.loginBtn.disabled = true;
    try {
        const resp = await fetch('/api/auth/login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({password}),
        });
        if (!resp.ok) {
            app.loginError.textContent = 'Incorrect password.';
            app.loginBtn.disabled = false;
            app.loginPassword.value = '';
            setTimeout(() => app.loginPassword.focus(), 50);
            return;
        }
        const data = await resp.json();
        authToken = data.token;
        localStorage.setItem('garudaai_token', authToken);
        hideLoginOverlay();
        await tryLoadModels();
        finishInit();
    } catch (e) {
        app.loginError.textContent = 'Login failed: ' + e.message;
        app.loginBtn.disabled = false;
    }
}

function authHeaders() {
    const h = {'Content-Type': 'application/json'};
    if (authToken) h['Authorization'] = `Bearer ${authToken}`;
    return h;
}

async function apiFetch(path, opts = {}) {
    opts.headers = {...(opts.headers || {}), ...authHeaders()};
    const resp = await fetch(path, opts);
    if (resp.status === 401) {
        authToken = '';
        localStorage.removeItem('garudaai_token');
        showLoginOverlay();
        throw new Error('Session expired — please log in again');
    }
    return resp;
}

// ---------------------------------------------------------------------------
// Models
// ---------------------------------------------------------------------------
async function tryLoadModels() {
    try {
        const resp = await fetch('/api/models', {
            headers: authToken ? {Authorization: `Bearer ${authToken}`} : {},
        });
        if (resp.status === 401) return false;
        const data = await resp.json();
        populateModelSelector(data.models || []);
        return true;
    } catch {
        if (app.modelSelector) app.modelSelector.innerHTML = '<option>Error loading models</option>';
        return true;
    }
}

function populateModelSelector(models) {
    app.modelSelector.innerHTML = '';

    if (models.length === 0) {
        app.modelSelector.innerHTML = '<option value="">No models — run: ollama pull gemma2:2b</option>';
        return;
    }

    const normal = models.filter(m => !m.name.includes('-airllm'));
    const airllm = models.filter(m => m.name.includes('-airllm'));

    const addGroup = (label, list) => {
        if (!list.length) return;
        const grp = document.createElement('optgroup');
        grp.label = label;
        list.forEach(model => {
            const opt = document.createElement('option');
            opt.value = model.name;
            opt.textContent = model.name;
            grp.appendChild(opt);
        });
        app.modelSelector.appendChild(grp);
    };

    addGroup('Models', normal);
    addGroup('Slow Mode (AirLLM)', airllm);

    const parseSize = name => {
        const m = String(name || '').match(/(\d+(?:\.\d+)?)\s*b/i);
        return m ? parseFloat(m[1]) : Infinity;
    };
    const sorted = [...normal].sort((a, b) => parseSize(a.name) - parseSize(b.name));
    currentModel = sorted[0] ? sorted[0].name : models[0].name;
    app.modelSelector.value = currentModel;
    updateSlowModeBadge();
}

function updateSlowModeBadge() {
    const isSlowMode = currentModel && currentModel.includes('-airllm');
    app.slowBadge.style.display = isSlowMode ? 'inline-block' : 'none';
}

// ---------------------------------------------------------------------------
// Sidebar
// ---------------------------------------------------------------------------
function openSidebar() {
    app.sidebar.classList.add('sidebar-open');
    app.sidebarBackdrop.classList.add('active');
    loadSessionHistory();
}

function closeSidebar() {
    app.sidebar.classList.remove('sidebar-open');
    app.sidebarBackdrop.classList.remove('active');
}

function toggleSidebar() {
    if (app.sidebar.classList.contains('sidebar-open')) {
        closeSidebar();
    } else {
        openSidebar();
    }
}

// ---------------------------------------------------------------------------
// Event Listeners
// ---------------------------------------------------------------------------
function setupEventListeners() {
    app.sendBtn.addEventListener('click', sendMessage);

    app.input.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey && !isMobile()) {
            e.preventDefault();
            sendMessage();
        }
    });

    app.input.addEventListener('input', () => {
        app.input.style.height = 'auto';
        app.input.style.height = Math.min(app.input.scrollHeight, 130) + 'px';
    });

    app.modelSelector.addEventListener('change', e => {
        currentModel = e.target.value;
        updateSlowModeBadge();
        createNewSession();
    });

    if (app.voiceBtn) app.voiceBtn.addEventListener('click', toggleVoiceInput);

    app.tabBtns.forEach(btn => {
        btn.addEventListener('click', e => switchTab(e.currentTarget.dataset.tab));
    });

    if (app.clearHistoryBtn) {
        app.clearHistoryBtn.addEventListener('click', () => {
            createNewSession();
            closeSidebar();
        });
    }

    if (app.voiceToggle) {
        app.voiceToggle.addEventListener('change', e => {
            voiceEnabled = e.target.checked;
            localStorage.setItem('voiceEnabled', voiceEnabled ? 'true' : 'false');
        });
    }

    if (app.ttsToggle) {
        app.ttsToggle.addEventListener('change', e => {
            ttsEnabled = e.target.checked;
            localStorage.setItem('ttsEnabled', ttsEnabled ? 'true' : 'false');
        });
    }

    if (app.passwordBtn) app.passwordBtn.addEventListener('click', updatePassword);

    if (app.sidebarToggle) app.sidebarToggle.addEventListener('click', toggleSidebar);
    if (app.sidebarClose)  app.sidebarClose.addEventListener('click', closeSidebar);
    if (app.sidebarBackdrop) app.sidebarBackdrop.addEventListener('click', closeSidebar);

    // Settings button opens sidebar to settings tab
    if (app.settingsBtn) {
        app.settingsBtn.addEventListener('click', () => {
            openSidebar();
            switchTab('settings');
        });
    }

    // Copy button delegation
    app.messages.addEventListener('click', e => {
        if (e.target.classList.contains('copy-btn')) {
            const msgDiv = e.target.closest('.message');
            if (!msgDiv) return;
            const content = msgDiv.querySelector('.message-content');
            const text = content.dataset.raw || content.textContent || '';
            navigator.clipboard.writeText(text).then(() => {
                e.target.textContent = '✓';
                setTimeout(() => { e.target.textContent = '⎘'; }, 1500);
            }).catch(() => { e.target.textContent = '!'; });
        }
    });

    // Login
    if (app.loginBtn) app.loginBtn.addEventListener('click', doLogin);
    if (app.loginPassword) {
        app.loginPassword.addEventListener('keydown', e => { if (e.key === 'Enter') doLogin(); });
    }

    // Camera
    if (app.cameraBtn) app.cameraBtn.addEventListener('click', captureFromCamera);
    if (app.removeImgBtn) app.removeImgBtn.addEventListener('click', removeImage);

    // SOUL.md
    if (app.soulSaveBtn) app.soulSaveBtn.addEventListener('click', saveSoul);

    // RAG upload
    if (app.ragFileInput) app.ragFileInput.addEventListener('change', handleRagUpload);

    // Export
    if (app.exportBtn) app.exportBtn.addEventListener('click', exportConversation);

    // Keyboard shortcuts (desktop)
    document.addEventListener('keydown', e => {
        if (e.ctrlKey && e.key === '/') { e.preventDefault(); app.input.focus(); }
        if (e.key === 'Escape') closeSidebar();
    });
}

// ---------------------------------------------------------------------------
// Speech Recognition (browser-side STT — fallback)
// ---------------------------------------------------------------------------
function setupSpeechRecognition() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
        if (app.voiceBtn) { app.voiceBtn.title = 'Voice input (hold to record)'; }
        return;
    }
    speechRecognition = new SR();
    speechRecognition.continuous = false;
    speechRecognition.interimResults = false;
    speechRecognition.lang = 'en-US';
    speechRecognition.onresult = e => {
        app.input.value = Array.from(e.results).map(r => r[0].transcript).join('');
        app.input.dispatchEvent(new Event('input'));
        recognitionActive = false;
        updateVoiceButton();
    };
    speechRecognition.onerror = () => { recognitionActive = false; updateVoiceButton(); };
    speechRecognition.onend   = () => { recognitionActive = false; updateVoiceButton(); };
}

function toggleVoiceInput() {
    if (!voiceEnabled) return;
    if (speechRecognition) {
        // Use browser SpeechRecognition
        if (recognitionActive) { speechRecognition.abort(); }
        else { recognitionActive = true; speechRecognition.start(); }
        updateVoiceButton();
    }
}

function updateVoiceButton() {
    if (!app.voiceBtn) return;
    if (recognitionActive) {
        app.voiceBtn.textContent = '🛑';
        app.voiceBtn.classList.add('recording');
        app.voiceBtn.title = 'Stop recording';
    } else {
        app.voiceBtn.textContent = '🎤';
        app.voiceBtn.classList.remove('recording');
        app.voiceBtn.title = 'Voice input';
    }
}

// ---------------------------------------------------------------------------
// Camera — capture photo for vision AI
// ---------------------------------------------------------------------------
async function captureFromCamera() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: isMobile() ? 'environment' : 'user' }
        });

        // Create a brief video preview overlay
        const overlay = document.createElement('div');
        overlay.style.cssText = 'position:fixed;inset:0;z-index:3000;background:#000;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:1rem;';

        const video = document.createElement('video');
        video.style.cssText = 'width:100%;max-width:480px;border-radius:12px;';
        video.autoplay = true;
        video.playsInline = true;
        video.srcObject = stream;

        const captureBtn = document.createElement('button');
        captureBtn.textContent = '📷 Capture';
        captureBtn.style.cssText = 'padding:0.75rem 2rem;background:var(--accent);color:var(--accent-fg);border:none;border-radius:20px;font-size:1rem;font-weight:600;cursor:pointer;';

        const cancelBtn = document.createElement('button');
        cancelBtn.textContent = 'Cancel';
        cancelBtn.style.cssText = 'padding:0.5rem 1.5rem;background:transparent;color:#fff;border:1px solid rgba(255,255,255,0.3);border-radius:20px;font-size:0.9rem;cursor:pointer;';

        overlay.appendChild(video);
        overlay.appendChild(captureBtn);
        overlay.appendChild(cancelBtn);
        document.body.appendChild(overlay);

        captureBtn.onclick = () => {
            const canvas = document.createElement('canvas');
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            canvas.getContext('2d').drawImage(video, 0, 0);
            stream.getTracks().forEach(t => t.stop());
            document.body.removeChild(overlay);
            const base64 = canvas.toDataURL('image/jpeg', 0.85).split(',')[1];
            pendingImage = base64;
            showImagePreview(canvas.toDataURL('image/jpeg', 0.85));
        };

        cancelBtn.onclick = () => {
            stream.getTracks().forEach(t => t.stop());
            document.body.removeChild(overlay);
        };
    } catch (err) {
        addSystemMessage('Camera access denied or unavailable.');
    }
}

function showImagePreview(dataUrl) {
    if (!app.imagePreviewArea) return;
    app.previewImg.src = dataUrl;
    app.imagePreviewArea.style.display = 'flex';
}

function removeImage() {
    pendingImage = null;
    if (app.imagePreviewArea) app.imagePreviewArea.style.display = 'none';
    if (app.previewImg) app.previewImg.src = '';
}

// ---------------------------------------------------------------------------
// TTS — speak response text using backend Piper or browser synthesis
// ---------------------------------------------------------------------------
async function speakResponse(text) {
    if (!ttsEnabled || !text) return;
    const stripped = text
        .replace(/```[\s\S]*?```/g, 'code block')
        .replace(/[*_`#\[\]]/g, '')
        .trim();
    if (!stripped) return;

    try {
        // Try server-side Piper TTS first
        const resp = await fetch('/api/speak', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'Authorization': `Bearer ${authToken}`},
            body: JSON.stringify({text: stripped.slice(0, 500)}),
        });
        if (resp.ok) {
            const blob = await resp.blob();
            const url = URL.createObjectURL(blob);
            const audio = new Audio(url);
            audio.onended = () => URL.revokeObjectURL(url);
            audio.play();
            return;
        }
    } catch (_) {}

    // Fallback: browser SpeechSynthesis
    if (window.speechSynthesis) {
        window.speechSynthesis.cancel();
        const utt = new SpeechSynthesisUtterance(stripped.slice(0, 300));
        window.speechSynthesis.speak(utt);
    }
}

// ---------------------------------------------------------------------------
// SOUL.md — persona editor
// ---------------------------------------------------------------------------
async function loadSoul() {
    if (!app.soulTextarea) return;
    try {
        const resp = await apiFetch('/api/soul');
        const data = await resp.json();
        app.soulTextarea.value = data.content || '';
    } catch (_) {}
}

async function saveSoul() {
    if (!app.soulTextarea || !app.soulSaveBtn) return;
    const content = app.soulTextarea.value;
    app.soulSaveBtn.disabled = true;
    app.soulSaveBtn.textContent = 'Saving...';
    try {
        const resp = await apiFetch('/api/soul', {
            method: 'POST',
            body: JSON.stringify({content}),
        });
        if (resp.ok) {
            app.soulSaveBtn.textContent = '✓ Saved';
            setTimeout(() => { app.soulSaveBtn.textContent = 'Save Persona'; app.soulSaveBtn.disabled = false; }, 1800);
        } else {
            app.soulSaveBtn.textContent = 'Error';
            app.soulSaveBtn.disabled = false;
        }
    } catch (_) {
        app.soulSaveBtn.textContent = 'Error';
        app.soulSaveBtn.disabled = false;
    }
}

// ---------------------------------------------------------------------------
// RAG — document upload and list
// ---------------------------------------------------------------------------
async function handleRagUpload() {
    const file = app.ragFileInput.files[0];
    if (!file) return;
    if (app.ragStatus) app.ragStatus.textContent = `Uploading ${file.name}...`;

    const fd = new FormData();
    fd.append('file', file);

    try {
        const resp = await fetch('/api/rag/upload', {
            method: 'POST',
            headers: authToken ? {Authorization: `Bearer ${authToken}`} : {},
            body: fd,
        });
        if (resp.status === 401) { showLoginOverlay(); return; }
        const data = await resp.json();
        if (app.ragStatus) app.ragStatus.textContent = data.message || 'Uploaded!';
        app.ragFileInput.value = '';
        await loadRagDocs();
        setTimeout(() => { if (app.ragStatus) app.ragStatus.textContent = ''; }, 4000);
    } catch (err) {
        if (app.ragStatus) app.ragStatus.textContent = 'Upload failed: ' + err.message;
    }
}

async function loadRagDocs() {
    if (!app.ragDocList) return;
    try {
        const resp = await apiFetch('/api/rag/documents');
        const data = await resp.json();
        const sources = data.sources || [];
        app.ragDocList.innerHTML = '';
        sources.forEach(src => {
            const item = document.createElement('div');
            item.className = 'rag-doc-item';
            const span = document.createElement('span');
            span.textContent = src;
            item.appendChild(span);
            app.ragDocList.appendChild(item);
        });
        if (sources.length === 0) {
            app.ragDocList.innerHTML = '<div style="font-size:0.8rem;color:var(--text-muted);">No documents yet</div>';
        }
    } catch (_) {}
}

// ---------------------------------------------------------------------------
// Export conversation as Markdown
// ---------------------------------------------------------------------------
function exportConversation() {
    const messages = [...app.messages.querySelectorAll('.message')];
    if (messages.length === 0) { alert('Nothing to export yet.'); return; }

    const lines = messages.map(m => {
        if (m.classList.contains('system-message')) return null;
        const isUser = m.classList.contains('user-message');
        const role = isUser ? '**You**' : '**GarudaAI**';
        const content = m.querySelector('.message-content');
        const text = content ? (content.dataset.raw || content.textContent || '').trim() : '';
        return `${role}\n\n${text}`;
    }).filter(Boolean);

    const md = lines.join('\n\n---\n\n');
    const blob = new Blob([md], {type: 'text/markdown; charset=utf-8'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `garuda-chat-${new Date().toISOString().slice(0,10)}.md`;
    a.click();
    URL.revokeObjectURL(a.href);
}

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------
function loadSettings() {
    if (app.voiceToggle) app.voiceToggle.checked = voiceEnabled;
    if (app.ttsToggle)   app.ttsToggle.checked = ttsEnabled;
}

// ---------------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------------
function switchTab(tabName) {
    app.tabBtns.forEach(btn => btn.classList.toggle('active', btn.dataset.tab === tabName));
    app.tabContents.forEach(c => {
        c.style.display = c.id === `${tabName}-tab` ? 'block' : 'none';
    });
    if (tabName === 'history') loadSessionHistory();
    if (tabName === 'settings') { loadSoul(); loadRagDocs(); }
}

// ---------------------------------------------------------------------------
// Sending messages
// ---------------------------------------------------------------------------
async function sendMessage() {
    const message = app.input.value.trim();
    if (!message || !currentModel) return;

    app.input.value = '';
    app.input.style.height = 'auto';
    if (isMobile()) app.input.blur();

    const imageToSend = pendingImage;
    if (imageToSend) removeImage();  // clear preview immediately

    addUserMessage(message, imageToSend);

    const isSlowMode = currentModel.includes('-airllm');
    const loadingId = addLoadingMessage(isSlowMode);

    try {
        await streamChatResponse(message, loadingId, 0, imageToSend);
    } catch (error) {
        updateMessage(loadingId, `Error: ${error.message}`, false);
    }
}

// ---------------------------------------------------------------------------
// WebSocket streaming with exponential backoff
// ---------------------------------------------------------------------------
function setConnStatus(state) {
    app.connStatus.className = `conn-status conn-${state}`;
    app.connStatus.title = {ok: 'Connected', reconnecting: 'Reconnecting...', error: 'Disconnected'}[state] || '';
}

async function streamChatResponse(message, loadingId, attempt = 0, image = null) {
    const MAX_ATTEMPTS = 3;
    try {
        await _doWebSocketStream(message, loadingId, image);
    } catch (err) {
        if (attempt < MAX_ATTEMPTS - 1) {
            const delay = 1000 * Math.pow(2, attempt);
            setConnStatus('reconnecting');
            updateMessage(loadingId, `⏳ Reconnecting (attempt ${attempt + 2}/${MAX_ATTEMPTS})...`, false);
            await new Promise(r => setTimeout(r, delay));
            return streamChatResponse(message, loadingId, attempt + 1, image);
        }
        setConnStatus('error');
        throw err;
    }
}

function _doWebSocketStream(message, loadingId, image = null) {
    return new Promise((resolve, reject) => {
        let pendingText = '';
        let flushTimer = null;
        let resolved = false;
        let firstToken = true;
        let finalText = '';

        const flushPending = () => {
            if (!pendingText) { flushTimer = null; return; }
            updateMessage(loadingId, pendingText, true);
            finalText += pendingText;
            pendingText = '';
            flushTimer = null;
        };

        const scheduleFlush = () => {
            if (flushTimer) return;
            flushTimer = setTimeout(flushPending, 40);
        };

        const finalize = (stats) => {
            if (resolved) return;
            resolved = true;
            if (flushTimer) { clearTimeout(flushTimer); flushTimer = null; }
            flushPending();
            setConnStatus('ok');
            if (stats) attachMessageStats(loadingId, stats);
            if (finalText) speakResponse(finalText);
            resolve();
        };

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const tokenParam = authToken ? `?token=${encodeURIComponent(authToken)}` : '';
        const wsUrl = `${protocol}//${window.location.host}/ws/chat${tokenParam}`;

        const ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            setConnStatus('ok');
            const payload = {
                model: currentModel,
                message,
                session_id: currentSessionId,
                use_case: localStorage.getItem('useCase') || 'general',
            };
            if (image) payload.image = image;
            ws.send(JSON.stringify(payload));
        };

        ws.onmessage = e => {
            try {
                let parsed;
                try { parsed = JSON.parse(e.data); } catch (_) {}

                if (parsed) {
                    if (parsed.type === 'done') {
                        ws.close();
                        finalize(parsed.stats || null);
                        return;
                    }
                    if (parsed.type === 'error') {
                        const errText = `Error: ${parsed.message}`;
                        if (firstToken) { updateMessage(loadingId, errText, false); firstToken = false; }
                        else { pendingText += errText; scheduleFlush(); }
                        ws.close(); finalize(null); return;
                    }
                }

                const text = (parsed && typeof parsed === 'object') ? JSON.stringify(parsed) : e.data;
                if (firstToken) {
                    updateMessage(loadingId, text, false);
                    finalText = text;
                    firstToken = false;
                } else {
                    pendingText += text;
                    scheduleFlush();
                }
            } catch (err) {
                console.error('Message parse error:', err);
            }
        };

        ws.onerror = () => reject(new Error('WebSocket connection failed'));
        ws.onclose = () => finalize(null);
    });
}

function attachMessageStats(messageId, stats) {
    const div = document.getElementById(messageId);
    if (!div || !stats) return;
    const content = div.querySelector('.message-content');
    if (!content) return;
    const statsEl = document.createElement('span');
    statsEl.className = 'msg-stats';
    statsEl.textContent = `~${stats.tokens} tokens · ${stats.tps} tok/s`;
    content.appendChild(statsEl);
}

// ---------------------------------------------------------------------------
// Message rendering
// ---------------------------------------------------------------------------
function renderMessageContent(contentEl, text, append = false) {
    const raw = append ? (contentEl.dataset.raw || '') + text : text;
    contentEl.dataset.raw = raw;
    if (window.marked && window.DOMPurify) {
        contentEl.innerHTML = DOMPurify.sanitize(marked.parse(raw));
    } else {
        contentEl.textContent = raw;
    }
}

function addUserMessage(text, image = null) {
    const div = document.createElement('div');
    div.className = 'message user-message';
    const content = document.createElement('div');
    content.className = 'message-content';

    if (image) {
        const img = document.createElement('img');
        img.className = 'message-image';
        img.src = `data:image/jpeg;base64,${image}`;
        img.alt = 'Attached image';
        content.appendChild(img);
    }

    const textNode = document.createElement('span');
    textNode.textContent = text;
    content.appendChild(textNode);

    div.appendChild(content);
    app.messages.appendChild(div);
    scrollToBottom();
}

function addLoadingMessage(slowMode = false) {
    const div = document.createElement('div');
    div.className = 'message assistant-message';
    div.id = 'msg-' + Date.now() + '-' + Math.random().toString(36).slice(2);

    const content = document.createElement('div');
    content.className = 'message-content';

    const indicator = document.createElement('span');
    indicator.className = 'typing-indicator';
    for (let i = 0; i < 3; i++) {
        const dot = document.createElement('span');
        dot.className = 'dot';
        indicator.appendChild(dot);
    }
    if (slowMode) {
        const label = document.createElement('span');
        label.className = 'slow-mode-label';
        label.textContent = ' Thinking… (1-3 min)';
        indicator.appendChild(label);
    }
    content.appendChild(indicator);

    const copyBtn = document.createElement('button');
    copyBtn.className = 'copy-btn';
    copyBtn.textContent = '⎘';
    copyBtn.title = 'Copy';

    div.appendChild(content);
    div.appendChild(copyBtn);
    app.messages.appendChild(div);
    scrollToBottom();
    return div.id;
}

function updateMessage(messageId, text, append = false) {
    const div = document.getElementById(messageId);
    if (!div) return;
    const content = div.querySelector('.message-content');
    // Remove typing indicator on first real content
    const indicator = content.querySelector('.typing-indicator');
    if (indicator && !append) indicator.remove();
    renderMessageContent(content, text, append);
    scrollToBottom();
}

function addAssistantMessage(text) {
    const id = addLoadingMessage(false);
    updateMessage(id, text, false);
    return id;
}

function addSystemMessage(text) {
    const div = document.createElement('div');
    div.className = 'message system-message';
    const content = document.createElement('div');
    content.className = 'message-content';
    content.textContent = text;
    div.appendChild(content);
    app.messages.appendChild(div);
    scrollToBottom();
}

// ---------------------------------------------------------------------------
// Sessions
// ---------------------------------------------------------------------------
async function createNewSession() {
    try {
        const resp = await apiFetch('/api/sessions', {
            method: 'POST',
            body: JSON.stringify({model_name: currentModel || 'gemma2:2b'}),
        });
        const data = await resp.json();
        currentSessionId = data.session_id;
    } catch {
        currentSessionId = 'local-' + Date.now();
    }
    app.messages.innerHTML = '';
}

async function loadSessionHistory() {
    const listContainer = document.getElementById('history-list');
    if (!listContainer) return;
    try {
        const resp = await apiFetch('/api/sessions');
        const data = await resp.json();
        const sessions = data.sessions || [];
        listContainer.innerHTML = '';

        if (sessions.length === 0) {
            listContainer.innerHTML = '<div class="placeholder">No history yet</div>';
            return;
        }

        sessions.forEach(session => {
            const div = document.createElement('div');
            div.className = 'history-item';

            const title = document.createElement('strong');
            title.textContent = session.summary || session.model_name || 'Session';

            const meta = document.createElement('small');
            meta.textContent = new Date(session.last_accessed).toLocaleString();

            div.appendChild(title);
            div.appendChild(document.createElement('br'));
            div.appendChild(meta);
            div.addEventListener('click', () => { loadSession(session.session_id); closeSidebar(); });
            listContainer.appendChild(div);
        });
    } catch {
        listContainer.innerHTML = '<div class="placeholder">Error loading history</div>';
    }
}

async function loadSession(sessionId) {
    try {
        const resp = await apiFetch(`/api/sessions/${sessionId}`);
        const data = await resp.json();
        currentSessionId = sessionId;
        currentModel = data.session.model_name;
        if (app.modelSelector) app.modelSelector.value = currentModel;
        updateSlowModeBadge();
        app.messages.innerHTML = '';

        data.messages.forEach(msg => {
            if (msg.role === 'user') addUserMessage(msg.content);
            else if (msg.role === 'assistant') addAssistantMessage(msg.content);
        });
    } catch (err) {
        console.error('Failed to load session:', err);
    }
}

// ---------------------------------------------------------------------------
// Password update
// ---------------------------------------------------------------------------
async function updatePassword() {
    const input = document.getElementById('password-input');
    const new_password = input ? input.value : '';
    if (!new_password) { alert('Please enter a new password'); return; }
    if (new_password.length < 8) { alert('Password must be at least 8 characters'); return; }
    try {
        const resp = await apiFetch('/api/auth/update-password', {
            method: 'POST',
            body: JSON.stringify({new_password}),
        });
        if (resp.ok) {
            if (input) input.value = '';
            alert('Password updated. Please log in again.');
            authToken = '';
            localStorage.removeItem('garudaai_token');
            showLoginOverlay();
        } else {
            const err = await resp.json().catch(() => ({}));
            alert('Failed: ' + (err.detail || 'Unknown error'));
        }
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------
function scrollToBottom() {
    requestAnimationFrame(() => {
        app.messages.scrollTop = app.messages.scrollHeight;
    });
}

if (window.marked) {
    marked.setOptions({ breaks: true, gfm: true });
}
