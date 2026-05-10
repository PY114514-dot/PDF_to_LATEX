// PDF2LaTeX Enhanced - 增强版前端脚本

let selectedFile = null;
let selectedFiles = [];  // 批量文件
let selectedImages = [];  // 图片文件
let downloadUrl = null;
let latexContent = null;
let latexFilename = '';
let socket = null;
let currentTaskId = null;
let activeAsyncTask = null;
let isBatchMode = false;  // 是否批量模式
let isImageMode = false;  // 是否图片模式
let lastAnalyzedPdfFile = null;
let currentPhaseRank = 0;
let translatePhaseProgress = 0;
let convertPhaseProgress = 0;
let historyCurrentPage = 1;
const HISTORY_PAGE_SIZE = 10;
const HISTORY_MAX_RECORDS = 20;
const MAX_BATCH_PDF_FILES = 5;

const STATUS_RANK = {
    preparing: 0,
    uploading: 1,
    processing: 2,
    extracting: 3,
    translating: 4,
    converting: 4,
    completed: 5,
    error: 5
};

// 成本统计已移除，保留接口结构但不再进行货币计算。

// 安全的localStorage访问（避免跟踪保护阻止）
const safeStorage = {
    setItem: (key, value) => {
        try {
            localStorage.setItem(key, value);
            return true;
        } catch (e) {
            console.warn('localStorage 被阻止:', e.message);
            return false;
        }
    },
    getItem: (key) => {
        try {
            return localStorage.getItem(key);
        } catch (e) {
            console.warn('localStorage 被阻止:', e.message);
            return null;
        }
    },
    removeItem: (key) => {
        try {
            localStorage.removeItem(key);
            return true;
        } catch (e) {
            console.warn('localStorage 被阻止:', e.message);
            return false;
        }
    }
};

// DOM元素
const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const optionsSection = document.getElementById('optionsSection');
const progressSection = document.getElementById('progressSection');
const resultSection = document.getElementById('resultSection');
const errorSection = document.getElementById('errorSection');
const convertBtn = document.getElementById('convertBtn');
const progressText = document.getElementById('progressText');
const translateProgressFill = document.getElementById('translateProgressFill');
const convertProgressFill = document.getElementById('convertProgressFill');
const translateProgressLabel = document.getElementById('translateProgressLabel');
const convertProgressLabel = document.getElementById('convertProgressLabel');
const translateProgressItem = document.getElementById('translateProgressItem');
const progressDetail = document.getElementById('progressDetail');
const tokenStats = document.getElementById('tokenStats');
const latexEditor = document.getElementById('latexEditor');
const latexRenderFrame = document.getElementById('latexRenderFrame');
const codeLines = document.getElementById('codeLines');
const downloadBtn = document.getElementById('downloadBtn');
const errorMessage = document.getElementById('errorMessage');

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    loadPublicConfig();
    setupDragAndDrop();
    setupFileInput();
    setupImageInput();
    setupBatchFileInput();
    setupPasteImage();
    setupConvertButton();
        setupResultEditor();
    setupLatexSidebar();
    setupHistoryPagination();
    initWebSocket();
    loadAvailableModels();
    loadHistory();
    loadTaskCenter();
    initMinimalMotion();
    initDocxUpload();
});

function initMinimalMotion() {
    const revealTargets = document.querySelectorAll('.header, .main-content, .history-section, .footer');
    if (!revealTargets.length) {
        return;
    }

    revealTargets.forEach((el) => el.classList.add('reveal-item'));

    if (!('IntersectionObserver' in window)) {
        revealTargets.forEach((el) => el.classList.add('is-visible'));
        return;
    }

    const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
            if (entry.isIntersecting) {
                entry.target.classList.add('is-visible');
                observer.unobserve(entry.target);
            }
        });
    }, {
        threshold: 0.14
    });

    revealTargets.forEach((el, index) => {
        el.style.transitionDelay = `${Math.min(index * 90, 360)}ms`;
        observer.observe(el);
    });
}

async function loadPublicConfig() {
    try {
        const response = await fetch('/api/public-config');
        if (!response.ok) {
            return;
        }
        const data = await response.json();
        // 兼容保留：当前前端不再使用成本换算。
    } catch (error) {
        console.warn('读取公开配置失败，使用默认配置:', error.message);
    }
}

function getCurrentLatexContent() {
    if (latexEditor && typeof latexEditor.value === 'string') {
        return latexEditor.value;
    }
    return latexContent || '';
}

function updateLatexEditorPreview(content = '') {
    if (!latexRenderFrame || !latexRenderFrame.contentWindow) {
        return;
    }
    latexRenderFrame.contentWindow.postMessage({
        type: 'latex-preview-update',
        content,
        filename: latexFilename || ''
    }, window.location.origin);
}

function updateLatexEditorStats(content = '') {
    if (codeLines) {
        const lines = content ? content.split('\n').length : 0;
        codeLines.textContent = `${lines} 行`;
    }
}

function downloadCurrentLatex() {
    const content = getCurrentLatexContent();
    if (!content) {
        showToast('没有可下载的LaTeX内容', 'error');
        return;
    }

    const fileName = (latexFilename || 'edited_output.tex').replace(/\.(tex|latex)$/i, '') + '.tex';
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = fileName;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function setupResultEditor() {
    if (!latexEditor || !latexRenderFrame) {
        return;
    }

    let renderTimer = null;
    const pushPreview = () => {
        const content = getCurrentLatexContent();
        latexContent = content;
        updateLatexEditorStats(content);
        window.requestAnimationFrame(() => updateLatexEditorPreview(content));
    };

    latexEditor.addEventListener('input', () => {
        latexContent = latexEditor.value;
        updateLatexEditorStats(latexEditor.value);
        clearTimeout(renderTimer);
        renderTimer = setTimeout(pushPreview, 120);
        safeStorage.setItem('latexContent', latexEditor.value);
        safeStorage.setItem('latexFilename', latexFilename || '');
    });

    latexRenderFrame.addEventListener('load', () => {
        pushPreview();
    });

    const savedContent = safeStorage.getItem('latexContent');
    if (savedContent && !latexContent) {
        latexEditor.value = savedContent;
        latexContent = savedContent;
        updateLatexEditorStats(savedContent);
    }
}

function setupHistoryPagination() {
    const prevBtn = document.getElementById('historyPrevBtn');
    const nextBtn = document.getElementById('historyNextBtn');
    if (!prevBtn || !nextBtn) {
        return;
    }

    prevBtn.addEventListener('click', () => {
        if (historyCurrentPage > 1) {
            historyCurrentPage -= 1;
            loadHistory();
        }
    });

    nextBtn.addEventListener('click', () => {
        historyCurrentPage += 1;
        loadHistory();
    });
}

function setupLatexSidebar() {
    const sidebar = document.getElementById('latexSidebar');
    const backdrop = document.getElementById('latexSidebarBackdrop');
    const openBtn = document.getElementById('openLatexSidebar');
    const closeBtn = document.getElementById('closeLatexSidebar');
    const renderBtn = document.getElementById('renderLatexBtn');
    const clearBtn = document.getElementById('clearLatexBtn');
    const input = document.getElementById('latexInput');
    const preview = document.getElementById('latexPreview');

    if (!sidebar || !openBtn || !closeBtn || !renderBtn || !clearBtn || !input || !preview) {
        return;
    }

    const openSidebar = () => {
        sidebar.classList.add('open');
        sidebar.setAttribute('aria-hidden', 'false');
        backdrop.classList.add('show');
        backdrop.setAttribute('aria-hidden', 'false');
        input.focus();
        queueRender();
    };

    const closeSidebar = () => {
        sidebar.classList.remove('open');
        sidebar.setAttribute('aria-hidden', 'true');
        backdrop.classList.remove('show');
        backdrop.setAttribute('aria-hidden', 'true');
    };

    let renderDebounceTimer = null;

    const delimiters = [
        { left: '$$', right: '$$', display: true },
        { left: '\\[', right: '\\]', display: true },
        { left: '$', right: '$', display: false },
        { left: '\\(', right: '\\)', display: false }
    ];

    const hasMathDelimiters = (text) => {
        return /\$\$[\s\S]*\$\$|\\\[[\s\S]*\\\]|\\\([\s\S]*\\\)|\$[^$]+\$/.test(text);
    };

    const normalizeStandaloneBlock = (text) => {
        const trimmed = text.trim();
        if (!trimmed) {
            return trimmed;
        }
        if ((trimmed.startsWith('\\[') && trimmed.endsWith('\\]')) ||
            (trimmed.startsWith('$$') && trimmed.endsWith('$$'))) {
            return trimmed;
        }
        // 兼容用户输入 [ ... ] 形式的块公式。
        if (trimmed.startsWith('[') && trimmed.endsWith(']') && trimmed.includes('\\')) {
            return `\\[${trimmed.slice(1, -1).trim()}\\]`;
        }
        return trimmed;
    };

    const renderLatexPreview = () => {
        const rawText = input.value;
        const text = rawText.trim();

        if (!text) {
            preview.textContent = '请输入 LaTeX 内容后点击渲染';
            return;
        }

        preview.textContent = text;
        let rendered = false;

        if (typeof renderMathInElement === 'function' && hasMathDelimiters(text)) {
            renderMathInElement(preview, {
                delimiters,
                throwOnError: false
            });
            rendered = Boolean(preview.querySelector('.katex'));
        }

        if (!rendered && typeof katex !== 'undefined' && typeof katex.render === 'function') {
            try {
                const normalized = normalizeStandaloneBlock(text);
                if (normalized.startsWith('\\[') && normalized.endsWith('\\]')) {
                    katex.render(normalized.slice(2, -2).trim(), preview, {
                        displayMode: true,
                        throwOnError: false
                    });
                } else if (normalized.startsWith('$$') && normalized.endsWith('$$')) {
                    katex.render(normalized.slice(2, -2).trim(), preview, {
                        displayMode: true,
                        throwOnError: false
                    });
                } else {
                    katex.render(normalized, preview, {
                        displayMode: true,
                        throwOnError: false
                    });
                }
                rendered = true;
            } catch (error) {
                preview.textContent = text;
            }
        }

        if (!rendered && typeof renderMathInElement === 'function') {
            renderMathInElement(preview, {
                delimiters,
                throwOnError: false
            });
        }
    };

    const queueRender = () => {
        if (renderDebounceTimer) {
            clearTimeout(renderDebounceTimer);
        }
        renderDebounceTimer = setTimeout(renderLatexPreview, 220);
    };

    openBtn.addEventListener('click', openSidebar);
    closeBtn.addEventListener('click', closeSidebar);
    backdrop.addEventListener('click', closeSidebar);
    renderBtn.addEventListener('click', renderLatexPreview);
    input.addEventListener('input', queueRender);
    input.addEventListener('paste', () => setTimeout(queueRender, 0));
    clearBtn.addEventListener('click', () => {
        input.value = '';
        preview.textContent = '请输入 LaTeX 内容后点击渲染';
        input.focus();
    });
}

// 初始化WebSocket
function initWebSocket() {
    if (typeof io !== 'function') {
        console.error('Socket.IO 客户端未加载，实时进度功能将降级。');
        addTerminalLog('warning', '实时通信库加载失败，已切换为非实时模式。');
        return;
    }

    socket = io({
        transports: ['websocket', 'polling'],
        reconnection: true,
        reconnectionDelay: 1000,
        reconnectionDelayMax: 5000,
        reconnectionAttempts: Infinity,  // 无限重连
        timeout: 300000,  // 5分钟超时
        pingTimeout: 300000,  // 5分钟ping超时
        pingInterval: 25000,  // 25秒ping间隔
        upgrade: false,  // 禁用传输升级，保持稳定
        forceNew: false
    });
    
    socket.on('connect', () => {
        console.log('WebSocket 已连接');
        if (currentTaskId) {
            socket.emit('join_task', { task_id: currentTaskId });
        }
    });
    
    socket.on('disconnect', (reason) => {
        console.warn('WebSocket 已断开:', reason);
        // 如果是ping timeout，尝试重连
        if (reason === 'ping timeout' || reason === 'transport close') {
            console.log('尝试重新连接...');
            setTimeout(() => socket.connect(), 1000);
        }
    });
    
    socket.on('connect_error', (error) => {
        console.error('WebSocket 连接错误:', error.message);
    });
    
    socket.on('reconnect', (attemptNumber) => {
        console.log('WebSocket 重连成功，尝试次数:', attemptNumber);
    });
    
    socket.on('reconnect_error', (error) => {
        console.error('WebSocket 重连失败:', error.message);
    });
    
    socket.on('reconnect_attempt', () => {
        console.log('WebSocket 尝试重连...');
    });
    
    socket.on('progress', (data) => {
        updateProgress(data);
        
        // 如果转换完成，停止进度条并显示结果
        if (data.status === 'completed' && data.result) {
            // 延迟一下让用户看到100%进度
            setTimeout(() => {
                // 判断是批量转换还是单个转换
                if (data.result.results && Array.isArray(data.result.results)) {
                    // 批量转换
                    showBatchResult(data.result);
                } else {
                    // 单个转换
                    showResult(data.result);
                }
            }, 800);
        }
        
        // 如果转换失败，显示错误
        if (data.status === 'error') {
            setTimeout(() => {
                showError(data.message || '转换失败');
            }, 500);
        }
    });
    
    // 添加心跳保活机制
    let heartbeatInterval;
    socket.on('connect', () => {
        if (heartbeatInterval) clearInterval(heartbeatInterval);
        heartbeatInterval = setInterval(() => {
            if (socket.connected) {
                socket.emit('heartbeat', { timestamp: Date.now() });
            }
        }, 20000); // 每20秒发送心跳
    });
    
    socket.on('disconnect', () => {
        if (heartbeatInterval) {
            clearInterval(heartbeatInterval);
            heartbeatInterval = null;
        }
    });
}

// 终端日志管理
function addTerminalLog(type, message) {
    const terminalLog = document.getElementById('terminalLog');
    const terminalBody = document.getElementById('terminalBody');
    
    if (!terminalLog || !terminalBody) {
        console.error('[终端] 元素未找到！');
        return;
    }
    
    // 首次显示终端
    if (terminalLog.style.display === 'none') {
        terminalLog.style.display = 'block';
        // 清空初始内容
        terminalBody.innerHTML = '';
    }
    
    // 创建日志行
    const logLine = document.createElement('div');
    logLine.className = `terminal-line log-${type} latest`;
    
    const prompt = document.createElement('span');
    prompt.className = 'terminal-prompt';
    prompt.textContent = getLogPrompt(type);
    
    const text = document.createElement('span');
    text.className = 'terminal-text';
    text.textContent = message;
    
    logLine.appendChild(prompt);
    logLine.appendChild(text);
    terminalBody.appendChild(logLine);
    
    // 移除旧的 latest 类
    setTimeout(() => {
        logLine.classList.remove('latest');
    }, 1000);
    
    // 自动滚动到底部
    terminalBody.scrollTop = terminalBody.scrollHeight;
}

function getLogPrompt(type) {
    const prompts = {
        'info': '→',
        'success': 'OK',
        'warning': '!',
        'error': '✗',
        'quality': 'Q',
        'progress': '>'
    };
    return prompts[type] || '→';
}

function getDefaultLogType(status) {
    const typeMap = {
        'preparing': 'info',
        'uploading': 'info',
        'extracting': 'progress',
        'converting': 'progress',
        'translating': 'progress',
        'processing': 'progress',
        'completed': 'success',
        'error': 'error'
    };
    return typeMap[status] || 'info';
}

function resetPhaseProgress(enableTranslate = false) {
    translatePhaseProgress = 0;
    convertPhaseProgress = 0;

    if (translateProgressFill) {
        translateProgressFill.style.width = '0%';
    }
    if (convertProgressFill) {
        convertProgressFill.style.width = '0%';
    }

    if (translateProgressLabel) {
        translateProgressLabel.textContent = enableTranslate ? '0%' : '未启用';
    }
    if (convertProgressLabel) {
        convertProgressLabel.textContent = '0%';
    }

    if (translateProgressItem) {
        translateProgressItem.style.opacity = enableTranslate ? '1' : '0.6';
    }
}

function updateStageBar(stage, percent) {
    const safePercent = Math.max(0, Math.min(100, Math.round(percent || 0)));

    if (stage === 'translating') {
        translatePhaseProgress = Math.max(translatePhaseProgress, safePercent);
        if (translateProgressFill) {
            translateProgressFill.style.transition = 'width 0.3s ease';
            translateProgressFill.style.width = `${translatePhaseProgress}%`;
        }
        if (translateProgressLabel) {
            translateProgressLabel.textContent = `${translatePhaseProgress}%`;
        }
        return;
    }

    if (stage === 'converting') {
        convertPhaseProgress = Math.max(convertPhaseProgress, safePercent);
        if (convertProgressFill) {
            convertProgressFill.style.transition = 'width 0.3s ease';
            convertProgressFill.style.width = `${convertPhaseProgress}%`;
        }
        if (convertProgressLabel) {
            convertProgressLabel.textContent = `${convertPhaseProgress}%`;
        }
    }
}

function clearTerminalLog() {
    const terminalBody = document.getElementById('terminalBody');
    terminalBody.innerHTML = '<div class="terminal-line"><span class="terminal-prompt">$</span><span class="terminal-text">日志已清空</span></div>';
}

// 更新进度
function updateProgress(data) {
    console.log('进度更新:', data);

    if (data.task_id && currentTaskId && data.task_id !== currentTaskId) {
        return;
    }

    const incomingRank = STATUS_RANK[data.status] ?? 0;
    if (incomingRank < currentPhaseRank && data.status !== 'error') {
        return;
    }
    if (incomingRank > currentPhaseRank) {
        currentPhaseRank = incomingRank;
    }
    
    // 如果有token信息，更新token统计显示
    if (data.tokens) {
        document.getElementById('promptTokens').textContent = (data.tokens.prompt_tokens || 0).toLocaleString();
        document.getElementById('completionTokens').textContent = (data.tokens.completion_tokens || 0).toLocaleString();
        document.getElementById('totalTokens').textContent = (data.tokens.total_tokens || 0).toLocaleString();
    }
    
    // 显示终端日志
    // 如果有log_message就用log_message，否则对于某些状态使用message
    const shouldShowLog = data.log_message || ['preparing', 'uploading', 'extracting', 'converting', 'translating', 'processing', 'completed'].includes(data.status);
    
    if (shouldShowLog) {
        const logMessage = data.log_message || data.message;
        const logType = data.log_type || getDefaultLogType(data.status);
        addTerminalLog(logType, logMessage);
    }

    // 百分比优先：前端统一以 percent 展示，避免显示“第 x/y 页正在转换”。
    const computedPercent = (() => {
        if (typeof data.percent === 'number') {
            return Math.max(0, Math.min(100, Math.round(data.percent)));
        }
        if (typeof data.current === 'number' && typeof data.total === 'number' && data.total > 0) {
            return Math.max(0, Math.min(100, Math.round((data.current / data.total) * 100)));
        }
        if (data.status === 'completed') {
            return 100;
        }
        return 0;
    })();
    
    // 分阶段更新进度条：翻译 / 转换
    if (data.status === 'translating') {
        updateStageBar('translating', computedPercent);
    } else if (data.status === 'converting') {
        updateStageBar('converting', computedPercent);
    } else if (data.status === 'completed') {
        updateStageBar('translating', 100);
        updateStageBar('converting', 100);
    }
    
    // 根据状态显示不同的消息前缀
    let message = data.message || '';
    let label = '';
    
    switch (data.status) {
        case 'preparing':
            label = '准备中';
            break;
        case 'uploading':
            label = '上传中';
            break;
        case 'extracting':
            label = '提取中';
            message = data.message;
            break;
        case 'translating':
            label = '翻译中';
            tokenStats.style.display = 'block';
            break;
        case 'converting':
            label = '转换中';
            tokenStats.style.display = 'block';
            break;
        case 'processing':
            label = '处理中';
            break;
        case 'completed':
            label = '已完成';
            break;
        default:
            label = '进度';
    }

    // 主文案固定为阶段 + 百分比
    progressText.textContent = `${label} · ${computedPercent}%`;

    // 详细文案不再显示具体页码
    let detailText = '';
    if (data.status === 'completed') {
        detailText = '处理完成';
    } else if (data.status === 'uploading') {
        detailText = '文件上传中';
    } else if (data.status === 'extracting') {
        detailText = '正文提取中';
    } else if (data.status === 'translating') {
        detailText = '翻译处理中';
    } else if (data.status === 'converting') {
        detailText = 'LaTeX 转换中';
    } else if (data.status === 'processing') {
        detailText = '任务处理中';
    } else if (data.status === 'preparing') {
        detailText = '任务准备中';
    } else {
        detailText = '处理中';
    }

    progressDetail.textContent = detailText;
    progressDetail.style.fontSize = '';
    progressDetail.style.fontWeight = '';
    progressDetail.style.color = data.status === 'completed' ? 'var(--success-color)' : 'var(--text-secondary)';
}

// 设置拖拽功能
function setupDragAndDrop() {
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => {
            dropZone.classList.add('dragover');
        });
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => {
            dropZone.classList.remove('dragover');
        });
    });

    dropZone.addEventListener('drop', handleDrop);
}

// 处理文件拖拽
function handleDrop(e) {
    const dt = e.dataTransfer;
    const files = Array.from(dt.files);
    
    if (files.length === 0) return;
    
    // 检查文件类型
    const hasImages = files.some(f => isImageFile(f));
    const hasPDFs = files.some(f => f.name.toLowerCase().endsWith('.pdf'));
    
    if (files.length > 1) {
        // 多个文件 - 批量模式
        if (hasImages && hasPDFs) {
            alert('不支持混合PDF和图片，请分别上传');
            return;
        }
        const fakeEvent = { target: { files: files } };
        handleBatchFileSelect(fakeEvent);
    } else if (files.length === 1) {
        // 单个文件
        if (isImageFile(files[0])) {
            const fakeEvent = { target: { files: [files[0]] } };
            handleImageFileSelect(fakeEvent);
        } else {
            handleFileSelect(files[0]);
        }
    }
}

// 设置文件输入
function setupFileInput() {
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFileSelect(e.target.files[0]);
        }
    });
}

// 设置批量文件输入
function setupBatchFileInput() {
    const batchInput = document.getElementById('batchFileInput');
    if (batchInput) {
        batchInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                handleBatchFileSelect(e);
            }
        });
    }
}

// 处理文件选择
async function handleFileSelect(file) {
    if (!file.type.includes('pdf') && !file.name.toLowerCase().endsWith('.pdf')) {
        showError('请选择PDF文件');
        return;
    }

    const maxSize = 50 * 1024 * 1024;
    if (file.size > maxSize) {
        showError('文件大小超过50MB限制');
        return;
    }

    selectedFile = file;
    selectedFiles = [];
    selectedImages = [];
    isImageMode = false;
    isBatchMode = false;
    lastAnalyzedPdfFile = file;
    
    const dropText = dropZone.querySelector('.drop-text');
    dropText.innerHTML = `已选择: <strong>${file.name}</strong> <span style="color: #888;">(正在检测页数...)</span>`;
    dropText.style.color = 'var(--success-color)';
    
    optionsSection.style.display = 'block';
    
    // 获取PDF页数
    try {
        const pageCount = await getPdfPageCount(file);
        dropText.innerHTML = `已选择: <strong>${file.name}</strong> <span style="color: #888;">(共 ${pageCount} 页)</span>`;
        
        // 更新页码输入提示
        const pagesInput = document.getElementById('pagesInput');
        pagesInput.placeholder = `例如: 1-3,5,7-9 (共${pageCount}页)`;
    } catch (error) {
        console.error('获取页数失败:', error);
        dropText.innerHTML = `已选择: <strong>${file.name}</strong>`;
    }
    
    optionsSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// 设置转换按钮
function setupConvertButton() {
    convertBtn.addEventListener('click', startConversion);
}

function collectCommonOptions() {
    return {
        model: document.getElementById('modelSelect').value,
        template: document.getElementById('templateSelect')?.value || 'article',
        quality_mode: document.getElementById('qualityModeSelect')?.value || 'standard',
        translation_prompt: document.getElementById('translationPromptInput')?.value?.trim() || ''
    };
}

async function pollAsyncTask(taskId) {
    activeAsyncTask = taskId;
    const maxRounds = 3600; // 最多轮询 1 小时
    let rounds = 0;
    while (activeAsyncTask === taskId && rounds < maxRounds) {
        rounds += 1;
        try {
            const res = await fetch(`/api/task/${taskId}`);
            const data = await res.json();
            if (data.success && data.task) {
                const status = data.task.status;
                if (status === 'completed' && data.task.result) {
                    showResult(data.task.result);
                    loadTaskCenter();
                    activeAsyncTask = null;
                    return;
                }
                if (status === 'failed') {
                    showError(data.task.error || '异步任务失败');
                    loadTaskCenter();
                    activeAsyncTask = null;
                    return;
                }
            }
        } catch (err) {
            console.warn('轮询异步任务失败:', err.message);
        }
        await new Promise(resolve => setTimeout(resolve, 2000));
    }
}

async function resumeLastAsyncTask() {
    const taskId = safeStorage.getItem('lastAsyncTaskId');
    if (!taskId) {
        showToast('没有找到可恢复的异步任务ID', 'error');
        return;
    }

    try {
        const response = await fetch(`/api/task/${taskId}/resume`, { method: 'POST' });
        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.error || '恢复失败');
        }
        currentTaskId = taskId;
        if (socket) {
            socket.emit('join_task', { task_id: taskId });
        }
        progressSection.style.display = 'block';
        optionsSection.style.display = 'none';
        resultSection.style.display = 'none';
        errorSection.style.display = 'none';
        addTerminalLog('info', `已恢复异步任务: ${taskId}`);
        pollAsyncTask(taskId);
        loadTaskCenter();
    } catch (err) {
        showToast(`恢复失败: ${err.message}`, 'error');
    }
}

// 开始转换
async function startConversion() {
    if (!selectedFile && selectedFiles.length === 0) {
        showError('请先选择文件');
        return;
    }

    // 图片模式
    if (isImageMode) {
        if (isBatchMode && selectedImages.length > 0) {
            startBatchImageConversion();
        } else {
            startImageConversion();
        }
    }
    // PDF模式
    else {
        if (isBatchMode && selectedFiles.length > 0) {
            startBatchConversion();
        } else {
            startSingleConversion();
        }
    }
}

// 单文件转换
async function startSingleConversion() {
    const translate = document.getElementById('translateOption').checked;
    const addWrapper = document.getElementById('wrapperOption').checked;
    const pagesInput = document.getElementById('pagesInput').value.trim();
    const options = collectCommonOptions();
    const asyncMode = document.getElementById('asyncOption')?.checked;

    optionsSection.style.display = 'none';
    progressSection.style.display = 'block';
    resultSection.style.display = 'none';
    errorSection.style.display = 'none';
    tokenStats.style.display = 'none';
    
    // 生成task_id并提前加入room
    const timestamp = Date.now();
    const taskId = `task_${timestamp}`;
    currentTaskId = taskId;
    currentPhaseRank = 0;
    resetPhaseProgress(translate);
    if (socket) {
        socket.emit('join_task', { task_id: taskId });
    }
    
    // 重置并显示终端日志
    const terminalLog = document.getElementById('terminalLog');
    const terminalBody = document.getElementById('terminalBody');
    terminalLog.style.display = 'block';
    terminalBody.innerHTML = '';
    addTerminalLog('info', '开始单文件转换任务...');

    updateProgress({
        percent: 0,
        current: 0,
        total: 100,
        message: '准备上传文件...',
        status: 'preparing'
    });

    try {
        if (!isImageMode && selectedFile) {
            lastAnalyzedPdfFile = selectedFile;
        }

        // 解析页码输入
        let pages = '';
        if (pagesInput) {
            try {
                pages = parsePageInput(pagesInput);
            } catch (error) {
                showError(error.message);
                return;
            }
        }
        
        const formData = new FormData();
        formData.append('file', selectedFile);
        formData.append('translate', translate);
        formData.append('add_wrapper', addWrapper);
        formData.append('model', options.model);
        formData.append('template', options.template);
        formData.append('quality_mode', options.quality_mode);
        formData.append('task_id', taskId);  // 传递task_id
        if (pages) {
            formData.append('pages', pages);
        }

        // 使用 XMLHttpRequest 监控上传进度
        const xhr = new XMLHttpRequest();
        
        // 上传进度监控
        xhr.upload.addEventListener('progress', (e) => {
            if (e.lengthComputable) {
                const percentComplete = Math.round((e.loaded / e.total) * 15); // 上传占15%
                updateProgress({
                    percent: percentComplete,
                    current: e.loaded,
                    total: e.total,
                    message: `上传文件中... ${formatBytes(e.loaded)} / ${formatBytes(e.total)}`,
                    status: 'uploading'
                });
            }
        });
        
        // 上传完成
        xhr.upload.addEventListener('load', () => {
            updateProgress({
                percent: 15,
                current: 1,
                total: 1,
                message: '文件上传完成，开始处理...',
                status: 'processing'
            });
        });
        
        // 创建Promise来处理XHR请求
        const uploadPromise = new Promise((resolve, reject) => {
            xhr.onload = () => {
                if (xhr.status === 200) {
                    try {
                        const result = JSON.parse(xhr.responseText);
                        resolve(result);
                    } catch (e) {
                        reject(new Error('解析响应失败'));
                    }
                } else {
                    try {
                        const error = JSON.parse(xhr.responseText);
                        reject(new Error(error.error || '转换失败'));
                    } catch (e) {
                        reject(new Error(`HTTP ${xhr.status}: ${xhr.statusText}`));
                    }
                }
            };
            
            xhr.onerror = () => reject(new Error('网络请求失败'));
            xhr.ontimeout = () => reject(new Error('请求超时'));
            
            xhr.open('POST', asyncMode ? '/api/convert-async' : '/api/convert');
            xhr.timeout = 1800000; // 30分钟超时（翻译需要更长时间）
            xhr.send(formData);
        });

        const result = await uploadPromise;

        if (asyncMode) {
            addTerminalLog('info', `异步任务已提交: ${result.task_id}`);
            safeStorage.setItem('lastAsyncTaskId', result.task_id);
            pollAsyncTask(result.task_id);
            loadTaskCenter();
            return;
        }

        // 不再直接调用 showResult，等待 WebSocket 的 'completed' 事件
        // WebSocket 会在转换完成时自动调用 showResult
        console.log('转换请求已发送，等待 WebSocket 完成通知...');

    } catch (error) {
        console.error('转换错误:', error);
        showError(error.message || '转换过程中出现错误');
    }
}

// 格式化字节大小
function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

// 批量转换
async function startBatchConversion() {
    if (selectedFiles.length > MAX_BATCH_PDF_FILES) {
        showError(`最多支持同时翻译 ${MAX_BATCH_PDF_FILES} 个不同的PDF文件`);
        return;
    }

    const translate = document.getElementById('translateOption').checked;
    const addWrapper = document.getElementById('wrapperOption').checked;
    const pagesInput = document.getElementById('pagesInput').value.trim();
    const options = collectCommonOptions();

    optionsSection.style.display = 'none';
    progressSection.style.display = 'block';
    resultSection.style.display = 'none';
    errorSection.style.display = 'none';
    tokenStats.style.display = 'none';
    
    // 重置并显示终端日志
    const terminalLog = document.getElementById('terminalLog');
    const terminalBody = document.getElementById('terminalBody');
    terminalLog.style.display = 'block';
    terminalBody.innerHTML = '';
    const batchTaskId = `batch_${Date.now()}`;
    currentTaskId = batchTaskId;
    if (socket) {
        socket.emit('join_task', { task_id: batchTaskId });
    }
    addTerminalLog('info', `开始批量转换 ${selectedFiles.length} 个文件... (任务ID: ${batchTaskId})`);
    currentPhaseRank = 0;
    resetPhaseProgress(translate);

    updateProgress({
        percent: 0,
        current: 0,
        total: selectedFiles.length,
        message: `准备批量处理 ${selectedFiles.length} 个文件...`,
        status: 'preparing'
    });

    try {
        // 解析页码输入
        let pages = '';
        if (pagesInput) {
            try {
                pages = parsePageInput(pagesInput);
            } catch (error) {
                showError(error.message);
                return;
            }
        }
        
        const formData = new FormData();
        
        // 添加所有文件
        for (const file of selectedFiles) {
            formData.append('files', file);
        }
        
        formData.append('translate', translate);
        formData.append('add_wrapper', addWrapper);
        formData.append('model', options.model);
        formData.append('template', options.template);
        formData.append('quality_mode', options.quality_mode);
        formData.append('task_id', batchTaskId);
        if (pages) {
            formData.append('pages', pages);
        }

        // 计算总文件大小
        const totalSize = selectedFiles.reduce((sum, file) => sum + file.size, 0);

        // 使用 XMLHttpRequest 监控上传进度
        const xhr = new XMLHttpRequest();
        
        // 上传进度监控
        xhr.upload.addEventListener('progress', (e) => {
            if (e.lengthComputable) {
                const percentComplete = Math.round((e.loaded / e.total) * 10); // 上传占10%
                updateProgress({
                    percent: percentComplete,
                    current: e.loaded,
                    total: e.total,
                    message: `上传 ${selectedFiles.length} 个文件中... ${formatBytes(e.loaded)} / ${formatBytes(e.total)}`,
                    status: 'uploading'
                });
            }
        });
        
        // 上传完成
        xhr.upload.addEventListener('load', () => {
            updateProgress({
                percent: 10,
                current: 0,
                total: selectedFiles.length,
                message: '文件上传完成，开始批量处理...',
                status: 'processing'
            });
        });
        
        // 创建Promise来处理XHR请求
        const uploadPromise = new Promise((resolve, reject) => {
            xhr.onload = () => {
                if (xhr.status === 200) {
                    try {
                        const result = JSON.parse(xhr.responseText);
                        resolve(result);
                    } catch (e) {
                        reject(new Error('解析响应失败'));
                    }
                } else {
                    try {
                        const error = JSON.parse(xhr.responseText);
                        reject(new Error(error.error || '批量转换失败'));
                    } catch (e) {
                        reject(new Error(`HTTP ${xhr.status}: ${xhr.statusText}`));
                    }
                }
            };
            
            xhr.onerror = () => reject(new Error('网络请求失败'));
            xhr.ontimeout = () => reject(new Error('请求超时'));
            
            xhr.open('POST', '/api/batch-convert');
            xhr.timeout = 600000; // 10分钟超时
            xhr.send(formData);
        });

        const result = await uploadPromise;

        // 优先使用 WebSocket；若连接异常导致未收到 completed，则使用 HTTP 结果兜底。
        setTimeout(() => {
            const waitingForSocket =
                currentTaskId === batchTaskId &&
                resultSection.style.display !== 'block' &&
                progressSection.style.display === 'block';
            if (waitingForSocket && result?.success) {
                addTerminalLog('info', '未收到实时完成事件，已切换为HTTP结果展示。');
                showBatchResult(result);
            }
        }, 1200);

    } catch (error) {
        console.error('批量转换错误:', error);
        showError(error.message || '批量转换过程中出现错误');
    }
}

// 显示结果
function showResult(result) {
    progressSection.style.display = 'none';
    resultSection.style.display = 'block';

    downloadUrl = result.download_url;
    latexContent = result.content;
    latexFilename = result.filename || result.output_filename || 'converted.tex';
    safeStorage.setItem('latexContent', latexContent || '');
    safeStorage.setItem('latexFilename', latexFilename || '');
        
    if (latexEditor) {
        latexEditor.value = result.content || '';
    }

    updateLatexEditorStats(result.content || '');
    updateLatexEditorPreview(result.content || '');

    // 显示统计信息
    if (result.stats) {
        // 处理页数显示 - 如果是图片则显示"1 张"，否则显示"x / y"
        const pagesText = isImageMode 
            ? `${result.stats.processed_pages || 1} 张`
            : `${result.stats.processed_pages || 0} / ${result.stats.total_pages || 0}`;
        document.getElementById('resultPages').textContent = pagesText;
        
        document.getElementById('resultTokens').textContent = 
            (result.stats.total_tokens || 0).toLocaleString();
        document.getElementById('resultTime').textContent = 
            `${result.stats.processing_time || 0}s`;
        
        // 更新Token统计（如果在进度中显示）
        document.getElementById('promptTokens').textContent = 
            (result.stats.prompt_tokens || 0).toLocaleString();
        document.getElementById('completionTokens').textContent = 
            (result.stats.completion_tokens || 0).toLocaleString();
        document.getElementById('totalTokens').textContent = 
            (result.stats.total_tokens || 0).toLocaleString();
    } else {
        // 如果没有stats，显示默认值
        const pagesText = isImageMode ? '1 张' : '0 / 0';
        document.getElementById('resultPages').textContent = pagesText;
        document.getElementById('resultTokens').textContent = '0';
        document.getElementById('resultTime').textContent = '0s';
        
        document.getElementById('promptTokens').textContent = '0';
        document.getElementById('completionTokens').textContent = '0';
        document.getElementById('totalTokens').textContent = '0';
    }

    // 设置下载按钮
    downloadBtn.onclick = downloadCurrentLatex;

    // 刷新历史记录
    loadHistory();

    resultSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}










function renderMathInContainer(container) {
    if (!container || typeof renderMathInElement !== 'function') {
        return;
    }
    try {
        renderMathInElement(container, {
            delimiters: [
                { left: '$$', right: '$$', display: true },
                { left: '\\[', right: '\\]', display: true },
                { left: '$', right: '$', display: false },
                { left: '\\(', right: '\\)', display: false }
            ],
            throwOnError: false,
            trust: true,
            strict: false
        });
    } catch (error) {
        console.warn('renderMathInElement 失败:', error.message);
    }
}



// 从历史记录运行学术智能体 - 打开新窗口


// 显示错误
function showError(message) {
    progressSection.style.display = 'none';
    optionsSection.style.display = 'none';
    errorSection.style.display = 'block';
    errorMessage.textContent = message;
    
    errorSection.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

// 复制到剪贴板（增强版，支持多种方式）
function copyToClipboard(event) {
    const content = getCurrentLatexContent();
    if (!content) {
        showCopyMessage('没有可复制的内容', false);
        return;
    }

    const btn = event?.target?.closest ? event.target.closest('button') : null;
    const originalHTML = btn.innerHTML;

    // 方法1: 使用现代 Clipboard API
    if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(content)
            .then(() => {
                showCopyMessage('已复制到剪贴板', true, btn, originalHTML);
            })
            .catch(err => {
                console.error('Clipboard API 失败:', err);
                // 如果失败，尝试备用方法
                fallbackCopyMethod(btn, originalHTML);
            });
    } else {
        // 不支持 Clipboard API，使用备用方法
        fallbackCopyMethod(btn, originalHTML);
    }
}

// 备用复制方法（兼容性更好）
function fallbackCopyMethod(btn, originalHTML) {
    try {
        // 创建临时 textarea
        const textarea = document.createElement('textarea');
        textarea.value = getCurrentLatexContent();
        textarea.style.position = 'fixed';
        textarea.style.top = '0';
        textarea.style.left = '0';
        textarea.style.width = '2em';
        textarea.style.height = '2em';
        textarea.style.padding = '0';
        textarea.style.border = 'none';
        textarea.style.outline = 'none';
        textarea.style.boxShadow = 'none';
        textarea.style.background = 'transparent';
        textarea.style.opacity = '0';
        
        document.body.appendChild(textarea);
        textarea.focus();
        textarea.select();
        
        // 尝试复制
        const successful = document.execCommand('copy');
        document.body.removeChild(textarea);
        
        if (successful) {
            showCopyMessage('已复制到剪贴板', true, btn, originalHTML);
        } else {
            showCopyMessage('复制失败，请手动复制', false, btn, originalHTML);
        }
    } catch (err) {
        console.error('备用复制方法失败:', err);
        showCopyMessage('复制失败，请手动复制', false, btn, originalHTML);
    }
}

// 显示复制消息
function showCopyMessage(message, success, btn, originalHTML) {
    if (btn) {
        if (success) {
            btn.innerHTML = `
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                    <polyline points="20 6 9 17 4 12"></polyline>
                </svg>
                ${message}
            `;
            btn.style.background = 'var(--success-color)';
            btn.style.color = 'white';
            
            setTimeout(() => {
                btn.innerHTML = originalHTML;
                btn.style.background = '';
                btn.style.color = '';
            }, 2000);
        } else {
            btn.innerHTML = `
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                    <circle cx="12" cy="12" r="10"></circle>
                    <line x1="12" y1="8" x2="12" y2="12"></line>
                    <line x1="12" y1="16" x2="12.01" y2="16"></line>
                </svg>
                ${message}
            `;
            btn.style.background = 'var(--error-color)';
            btn.style.color = 'white';
            
            setTimeout(() => {
                btn.innerHTML = originalHTML;
                btn.style.background = '';
                btn.style.color = '';
            }, 3000);
        }
    } else {
        // 如果没有按钮，显示提示框
        if (success) {
            showToast(message, 'success');
        } else {
            showToast(message, 'error');
        }
    }
}

// Toast 提示（可选的额外提示方式）
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;

    let bgColor = '#3b82f6', padding = '1rem 1.5rem', fontSize = '14px';
    if (type === 'success') {
        bgColor = '#10b981';
    } else if (type === 'error') {
        bgColor = '#ef4444';
    }

    toast.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: ${bgColor};
        color: white;
        padding: ${padding};
        border-radius: 0.5rem;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
        z-index: 10000;
        animation: slideIn 0.3s ease;
        font-size: ${fontSize};
    `;
    
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => {
            document.body.removeChild(toast);
        }, 300);
    }, 3000);
}

// 全屏切换
function toggleFullscreen(event) {
    const codePreview = document.querySelector('#latexWorkspace') || document.querySelector('.code-preview');
    codePreview.classList.toggle('fullscreen');
    
    const btn = event?.target?.closest ? event.target.closest('button') : null;
    if (!btn) {
        return;
    }
    if (codePreview.classList.contains('fullscreen')) {
        btn.innerHTML = `
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"></path>
            </svg>
        `;
    } else {
        btn.innerHTML = `
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"></path>
            </svg>
        `;
    }
}

// 显示批量结果
function showBatchResult(result) {
    progressSection.style.display = 'none';
    resultSection.style.display = 'block';

    const stats = result.total_stats;
    const results = result.results;

    // 保存结果到全局变量
    window.batchResults = results;

    // 更新统计信息（使用人民币）
    const pagesText = isImageMode 
        ? `${stats.total_pages || stats.successful_files || 0} 张`
        : `${stats.total_pages || 0}`;
    document.getElementById('resultPages').textContent = pagesText;
    document.getElementById('resultTokens').textContent = (stats.total_tokens || 0).toLocaleString();
    document.getElementById('resultTime').textContent = `${(stats.total_time || 0).toFixed(1)}s`;

    // 显示批量结果列表
    const codePreview = document.querySelector('.code-preview');
    codePreview.innerHTML = `
        <div class="code-header">
            <span>批量转换结果 (${stats.successful_files}/${stats.total_files} 成功)</span>
            <div class="code-header-right">
                <button class="icon-btn" onclick="downloadBatchResults('${result.batch_id}')" title="打包下载">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                        <polyline points="7 10 12 15 17 10"></polyline>
                        <line x1="12" y1="15" x2="12" y2="3"></line>
                    </svg>
                </button>
                        <button class="icon-btn" onclick="mergeBatchResults(window.batchResults)" title="合并为单个tex">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                                <path d="M8 6h13M8 12h13M8 18h13"></path>
                                <path d="M3 6h.01M3 12h.01M3 18h.01"></path>
                            </svg>
                        </button>
            </div>
        </div>
        <div class="batch-results-list">
            ${results.map((r, idx) => `
                <div class="batch-result-item ${r.success ? 'success' : 'error'}">
                    <div class="batch-result-header">
                        <span class="batch-result-icon">${r.success ? 'SUCCESS' : 'FAILED'}</span>
                        <span class="batch-result-filename">${r.filename}</span>
                        <div class="batch-result-actions">
                            ${r.success ? `
                                <button class="batch-action-btn render-btn" onclick="renderBatchFile(window.batchResults[${idx}].content, '${r.filename}')" title="渲染预览">
                                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                                        <circle cx="12" cy="12" r="10"></circle>
                                        <polygon points="10 8 16 12 10 16 10 8"></polygon>
                                    </svg>
                                    渲染
                                </button>
                                <button class="batch-action-btn download-btn" onclick="window.location.href='${r.download_url}'" title="下载文件">
                                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                                        <polyline points="7 10 12 15 17 10"></polyline>
                                        <line x1="12" y1="15" x2="12" y2="3"></line>
                                    </svg>
                                    下载
                                </button>
                            ` : ''}
                        </div>
                    </div>
                    ${r.success ? `
                        <div class="batch-result-stats">
                            <span>页数 ${r.stats.processed_pages}</span>
                            <span>Tokens ${r.stats.total_tokens.toLocaleString()}</span>
                            <span>耗时 ${r.stats.processing_time}s</span>
                        </div>
                    ` : `
                        <div class="batch-result-error">错误: ${r.error}</div>
                    `}
                </div>
            `).join('')}
        </div>
    `;

    // 刷新历史记录
    loadHistory();

    resultSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }

// 下载批量结果
function downloadBatchResults(batchId) {
    window.location.href = `/api/download-batch/${batchId}`;
}

async function mergeBatchResults(results) {
    const successful = (results || []).filter(r => r.success && r.output_filename).map(r => r.output_filename);
    if (successful.length < 2) {
        showToast('至少需要 2 个成功文件才能合并', 'error');
        return;
    }

    try {
        const payload = {
            filenames: successful,
            template: document.getElementById('templateSelect')?.value || 'article',
            use_chinese: document.getElementById('translateOption')?.checked || false,
            merged_name: `merged_${Date.now()}.tex`
        };
        const response = await fetch('/api/merge-outputs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.error || '合并失败');
        }
        window.location.href = data.download_url;
        showToast('合并完成，已开始下载', 'success');
    } catch (error) {
        showToast(`合并失败: ${error.message}`, 'error');
    }
}

// 解析页码输入（支持范围和逗号分隔）
function parsePageInput(input) {
    /**
     * 解析页码输入，支持以下格式：
     * - 单页: "1" -> "1"
     * - 逗号分隔: "1,2,3" -> "1,2,3"
     * - 范围: "1-3" -> "1,2,3"
     * - 混合: "1-3,5,7-9" -> "1,2,3,5,7,8,9"
     */
    if (!input || !input.trim()) {
        return '';
    }
    
    try {
        const parts = input.split(',').map(p => p.trim()).filter(p => p);
        const pages = new Set(); // 使用Set自动去重
        
        for (const part of parts) {
            if (part.includes('-')) {
                // 处理范围格式 "1-3"
                const range = part.split('-').map(n => n.trim());
                if (range.length !== 2) {
                    throw new Error(`无效的范围格式: ${part}`);
                }
                
                const start = parseInt(range[0]);
                const end = parseInt(range[1]);
                
                if (isNaN(start) || isNaN(end)) {
                    throw new Error(`无效的页码: ${part}`);
                }
                
                if (start > end) {
                    throw new Error(`起始页不能大于结束页: ${part}`);
                }
                
                if (start < 1 || end < 1) {
                    throw new Error(`页码必须大于0: ${part}`);
                }
                
                // 添加范围内的所有页码
                for (let i = start; i <= end; i++) {
                    pages.add(i);
                }
            } else {
                // 处理单个页码
                const page = parseInt(part);
                if (isNaN(page)) {
                    throw new Error(`无效的页码: ${part}`);
                }
                
                if (page < 1) {
                    throw new Error(`页码必须大于0: ${part}`);
                }
                
                pages.add(page);
            }
        }
        
        // 转换为排序后的逗号分隔字符串
        return Array.from(pages).sort((a, b) => a - b).join(',');
    } catch (error) {
        throw new Error(`页码格式错误: ${error.message}`);
    }
}

// 压缩页码范围显示，如 "1,2,3,4,7,8,9,21,22,23,24" -> "1-4,7-9,21-24"
function compressPageRanges(pagesStr) {
    if (!pagesStr || pagesStr === 'all' || pagesStr === '*') {
        return '全部';
    }

    // 如果已经是范围格式或单页，直接返回
    if (pagesStr.includes('-')) {
        return pagesStr;
    }

    const pages = pagesStr.split(',').map(p => parseInt(p.trim())).filter(p => !isNaN(p));
    if (pages.length === 0) return pagesStr;
    if (pages.length === 1) return pages[0].toString();

    pages.sort((a, b) => a - b);
    const ranges = [];
    let start = pages[0];
    let end = pages[0];

    for (let i = 1; i < pages.length; i++) {
        if (pages[i] === end + 1) {
            end = pages[i];
        } else {
            ranges.push(start === end ? start.toString() : `${start}-${end}`);
            start = pages[i];
            end = pages[i];
        }
    }
    ranges.push(start === end ? start.toString() : `${start}-${end}`);

    return ranges.join(',');
}

// 获取PDF页数
async function getPdfPageCount(file) {
    try {
        const formData = new FormData();
        formData.append('file', file);
        
        const response = await fetch('/api/get-pdf-pages', {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            throw new Error('获取页数失败');
        }
        
        const data = await response.json();
        
        if (data.success) {
            return data.total_pages;
        } else {
            throw new Error(data.error || '获取页数失败');
        }
    } catch (error) {
        console.error('获取PDF页数错误:', error);
        throw error;
    }
}

// 重置应用
function resetApp() {
    selectedFile = null;
    selectedFiles = [];
    downloadUrl = null;
    latexContent = null;
    currentTaskId = null;
    isBatchMode = false;
    isImageMode = false;
    selectedImages = [];
    lastAnalyzedPdfFile = null;

    const dropText = dropZone.querySelector('.drop-text');
    dropText.innerHTML = '拖拽文件到这里';
    dropText.style.color = '';

    fileInput.value = '';
    const batchInput = document.getElementById('batchFileInput');
    if (batchInput) batchInput.value = '';
    
    document.getElementById('translateOption').checked = false;
    document.getElementById('wrapperOption').checked = true;
    document.getElementById('pagesInput').value = '';
    const templateSelect = document.getElementById('templateSelect');
    const qualityModeSelect = document.getElementById('qualityModeSelect');
    const asyncOption = document.getElementById('asyncOption');
    if (templateSelect) templateSelect.value = 'article';
    if (qualityModeSelect) qualityModeSelect.value = 'standard';
    if (asyncOption) asyncOption.checked = false;

    optionsSection.style.display = 'none';
    progressSection.style.display = 'none';
    resultSection.style.display = 'none';
    errorSection.style.display = 'none';
    tokenStats.style.display = 'none';
        
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function openRenderPreview(content, filename = '') {
    if (!content) {
        showToast('没有可渲染的LaTeX代码', 'error');
        return;
    }

    // 多通道传递，避免浏览器阻止 localStorage 时首次渲染失败。
    safeStorage.setItem('latexContent', content);
    if (filename) {
        safeStorage.setItem('latexFilename', filename);
    }

    window.__latexRenderPayload = {
        latexContent: content,
        latexFilename: filename || ''
    };

    const renderWindow = window.open('/render', '_blank', 'width=1400,height=900');
    if (renderWindow) {
        try {
            renderWindow.name = JSON.stringify(window.__latexRenderPayload);
        } catch (error) {
            console.warn('写入渲染窗口 payload 失败:', error.message);
        }
    }
}

// LaTeX本地渲染（使用KaTeX）
function renderLatex(content = null) {
    const contentToRender = content || latexContent;
    
    if (!contentToRender) {
        showToast('没有可渲染的LaTeX代码', 'error');
        return;
    }

    openRenderPreview(contentToRender, latexFilename || safeStorage.getItem('latexFilename') || '');
}

// 为批量结果渲染特定文件
function renderBatchFile(fileContent, filename) {
    if (!fileContent) {
        showToast('无法获取文件内容', 'error');
        return;
    }

    openRenderPreview(fileContent, filename || '');
}

// 加载可用模型列表
async function loadAvailableModels() {
    const modelSelect = document.getElementById('modelSelect');
    
    try {
        const response = await fetch('/api/models');
        const data = await response.json();
        
        if (data.success && data.models && data.models.length > 0) {
            // 清空加载中的选项
            modelSelect.innerHTML = '';
            
            // 添加模型选项
            data.models.forEach(model => {
                const option = document.createElement('option');
                option.value = model.id;
                option.textContent = `${model.name} - ${model.description}`;
                
                // 默认选中 deepseek-chat
                if (model.id === 'deepseek-chat') {
                    option.selected = true;
                }
                
                modelSelect.appendChild(option);
            });
            
            console.log(`已加载 ${data.models.length} 个可用模型`);
        } else {
            modelSelect.innerHTML = '<option value="deepseek-chat">DeepSeek Chat (默认)</option>';
            console.warn('未找到可用模型，使用默认模型');
        }
    } catch (error) {
        console.error('加载模型列表失败:', error);
        modelSelect.innerHTML = '<option value="deepseek-chat">DeepSeek Chat (默认)</option>';
    }
}

// 检查API状态
async function checkApiStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        console.log('API状态:', data);
    } catch (error) {
        console.error('API连接失败:', error);
    }
}

checkApiStatus();

// ==================== 历史记录功能 ====================

// 加载历史记录
async function loadHistory() {
    const historyList = document.getElementById('historyList');
    const pagination = document.getElementById('historyPagination');
    const pageInfo = document.getElementById('historyPageInfo');
    const prevBtn = document.getElementById('historyPrevBtn');
    const nextBtn = document.getElementById('historyNextBtn');
    
    try {
        const offset = (historyCurrentPage - 1) * HISTORY_PAGE_SIZE;
        const response = await fetch(`/api/history?limit=${HISTORY_PAGE_SIZE}&offset=${offset}`);
        const data = await response.json();
        const total = Math.min(data.total || 0, HISTORY_MAX_RECORDS);
        const totalPages = Math.max(1, Math.ceil(total / HISTORY_PAGE_SIZE));
        const safePage = Math.min(Math.max(1, historyCurrentPage), totalPages);
        if (safePage !== historyCurrentPage) {
            historyCurrentPage = safePage;
        }
        
        if (data.success && data.history && data.history.length > 0) {
            historyList.innerHTML = data.history.map((record, index) => {
                const absoluteIndex = offset + index;
                const date = new Date(record.timestamp);
                const dateStr = date.toLocaleString('zh-CN');
                const model = record.model || 'unknown';
                const language = record.translated ? '中文' : '英文';
                const pages = compressPageRanges(record.pages);
                const tokens = record.stats?.total_tokens || 0;
                
                return `
                    <div class="history-item" onclick="viewHistory(${absoluteIndex})">
                        <div class="history-icon">PDF</div>
                        <div class="history-info">
                            <div class="history-filename">${record.filename}</div>
                            <div class="history-meta">
                                <span>模型 ${model}</span>
                                <span>语言 ${language}</span>
                                <span>页码 ${pages}</span>
                                <span>Tokens ${tokens.toLocaleString()}</span>
                                <span>时间 ${dateStr}</span>
                            </div>
                        </div>
                        <div class="history-actions" onclick="event.stopPropagation()">
                            <button class="history-action-btn primary" onclick="downloadHistory(${absoluteIndex})">
                                下载
                            </button>
                            <button class="history-action-btn secondary" onclick="viewHistory(${absoluteIndex})">
                                查看
                            </button>
                            
                            <button class="history-action-btn danger" onclick="deleteHistory(${absoluteIndex})">
                                删除
                            </button>
                        </div>
                    </div>
                `;
            }).join('');
            if (pagination && pageInfo && prevBtn && nextBtn) {
                pagination.style.display = total > HISTORY_PAGE_SIZE ? 'flex' : 'none';
                pageInfo.textContent = `${historyCurrentPage} / ${totalPages}`;
                prevBtn.disabled = historyCurrentPage <= 1;
                nextBtn.disabled = historyCurrentPage >= totalPages;
            }
        } else {
            historyList.innerHTML = `
                <div class="history-empty">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
                    </svg>
                    <p>暂无历史记录</p>
                </div>
            `;
            if (pagination) {
                pagination.style.display = 'none';
            }
        }
    } catch (error) {
        console.error('加载历史记录失败:', error);
        historyList.innerHTML = `
            <div class="history-empty">
                <p>加载历史记录失败</p>
            </div>
        `;
        if (pagination) {
            pagination.style.display = 'none';
        }
    }
}

// 刷新历史记录
function refreshHistory() {
    historyCurrentPage = 1;
    loadHistory();
}

async function loadTaskCenter() {
    const taskList = document.getElementById('taskCenterList');
    if (!taskList) return;

    try {
        const response = await fetch('/api/tasks?limit=50');
        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.error || '加载任务中心失败');
        }

        // 只筛选未完成的任务（进行中、排队中、失败）
        const incompleteTasks = (data.tasks || []).filter(task => {
            const status = task.status || '';
            return status !== 'completed';
        });

        if (incompleteTasks.length === 0) {
            taskList.innerHTML = '<div class="history-empty"><p>暂无进行中的任务</p></div>';
            return;
        }

        taskList.innerHTML = incompleteTasks.map(task => {
            const rawStatus = task.status || 'unknown';
            let statusLabel = '处理中';
            if (rawStatus === 'queued' || rawStatus === 'preparing' || rawStatus === 'uploading') {
                statusLabel = '排队中';
            } else if (rawStatus === 'failed' || rawStatus === 'error') {
                statusLabel = '失败';
            }
            const taskId = task.task_id;
            const updatedAt = task.updated_at ? new Date(task.updated_at).toLocaleString('zh-CN') : '-';
            const progress = task.progress || {};
            const result = task.result || null;
            const sourceName = task.payload?.filename || result?.source_filename || taskId;
            const texName = result?.filename || (task.payload?.output_path ? task.payload.output_path.split(/[\\/]/).pop() : '-');

            return `
                <div class="history-item">
                    <div class="history-icon">${rawStatus === 'failed' ? '!' : '↻'}</div>
                    <div class="history-info">
                        <div class="history-filename">${sourceName}</div>
                        <div class="history-meta">
                            <span>状态: ${statusLabel}</span>
                            <span>进度: ${progress.percent ?? 0}%</span>
                            <span>${progress.message || '处理中...'}</span>
                        </div>
                    </div>
                    <div class="history-actions">
                        ${result ? `<button class="history-action-btn primary" onclick="openTaskResult('${taskId}')">查看</button>` : ''}
                        ${rawStatus === 'failed' ? `<button class="history-action-btn secondary" onclick="resumeTaskById('${taskId}')">重试</button>` : ''}
                    </div>
                </div>
            `;
        }).join('');
    } catch (error) {
        taskList.innerHTML = `<div class="history-empty"><p>加载失败: ${error.message}</p></div>`;
    }
}

async function openTaskResult(taskId) {
    try {
        const response = await fetch(`/api/task/${taskId}`);
        const data = await response.json();
        if (!response.ok || !data.success || !data.task?.result) {
            throw new Error(data.error || '结果不存在');
        }
        showResult(data.task.result);
    } catch (error) {
        showToast(`打开任务结果失败: ${error.message}`, 'error');
    }
}

async function resumeTaskById(taskId) {
    try {
        const response = await fetch(`/api/task/${taskId}/resume`, { method: 'POST' });
        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.error || '恢复失败');
        }
        currentTaskId = taskId;
        if (socket) {
            socket.emit('join_task', { task_id: taskId });
        }
        safeStorage.setItem('lastAsyncTaskId', taskId);
        pollAsyncTask(taskId);
        loadTaskCenter();
        showToast('任务已恢复', 'success');
    } catch (error) {
        showToast(`恢复失败: ${error.message}`, 'error');
    }
}

// 查看历史记录
async function viewHistory(index) {
    try {
        const response = await fetch(`/api/history/${index}`);
        const data = await response.json();

        if (data.success && data.record) {
            // 获取文件内容并渲染
            if (data.record.output_file) {
                const filename = data.record.output_file.split(/[\\/]/).pop();

                // 读取文件内容
                const fileResponse = await fetch(`/api/download/${encodeURIComponent(filename)}`);

                if (!fileResponse.ok) {
                    const errorData = await fileResponse.json().catch(() => ({error: '文件不存在或已被删除'}));
                    showToast(`文件不存在: ${errorData.error || '请检查文件是否被删除'}`, 'error');
                    return;
                }

                const latexContent = await fileResponse.text();
                openRenderPreview(latexContent, filename);
            } else {
                showToast('该历史记录没有对应的输出文件', 'error');
            }
        } else {
            showToast('记录不存在', 'error');
        }
    } catch (error) {
        console.error('查看历史记录失败:', error);
        showToast('查看失败: ' + error.message, 'error');
    }
}

// 下载历史记录
async function downloadHistory(index) {
    try {
        const response = await fetch(`/api/history/${index}`);
        const data = await response.json();

        if (data.success && data.record) {
            if (data.record.output_file) {
                const filename = data.record.output_file.split(/[\\/]/).pop();
                window.location.href = `/api/download/${encodeURIComponent(filename)}`;
            } else {
                showToast('该历史记录没有对应的输出文件', 'error');
            }
        } else {
            showToast('记录不存在', 'error');
        }
    } catch (error) {
        console.error('下载历史记录失败:', error);
        showToast('下载失败: ' + error.message, 'error');
    }
}

// 删除单条历史记录
async function deleteHistory(index) {
    if (!confirm('确定删除这条历史记录吗？')) {
        return;
    }

    try {
        const response = await fetch(`/api/history/${index}`, { method: 'DELETE' });
        const data = await response.json();
        if (data.success) {
            loadHistory();
        } else {
            alert(data.error || '删除失败');
        }
    } catch (error) {
        console.error('删除历史记录失败:', error);
        alert('删除失败: ' + error.message);
    }
}

// 一键清空历史记录
async function clearAllHistory() {
    if (!confirm('确定清空所有历史记录吗？此操作不可恢复。')) {
        return;
    }

    try {
        const response = await fetch('/api/history/clear', { method: 'POST' });
        const data = await response.json();
        if (data.success) {
            historyCurrentPage = 1;
            loadHistory();
        } else {
            alert(data.error || '清空失败');
        }
    } catch (error) {
        console.error('清空历史记录失败:', error);
        alert('清空失败: ' + error.message);
    }
}

// ================================
// 图片处理功能
// ================================

// 检查是否为图片文件
function isImageFile(file) {
    const imageExtensions = ['png', 'jpg', 'jpeg', 'webp', 'bmp', 'tiff', 'gif'];
    const ext = file.name.split('.').pop().toLowerCase();
    return imageExtensions.includes(ext);
}

// 设置图片输入
function setupImageInput() {
    const imageInput = document.getElementById('imageInput');
    if (imageInput) {
        imageInput.addEventListener('change', handleImageFileSelect);
    }
}

// 处理图片文件选择
function handleImageFileSelect(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    if (!isImageFile(file)) {
        alert('请选择有效的图片文件');
        return;
    }
    
    selectedFile = file;
    selectedFiles = [];
    selectedImages = [file];
    isImageMode = true;
    isBatchMode = false;
    
    // 更新拖放区域提示
    const dropText = dropZone.querySelector('.drop-text');
    dropText.innerHTML = `已选择图片: <strong>${file.name}</strong>`;
    dropText.style.color = 'var(--success-color)';
    
    // 显示图片预览
    displayImagePreview([file]);
    
    // 显示转换选项
    optionsSection.style.display = 'block';
    
    // 显示OCR引擎选择
    const ocrGroup = document.getElementById('ocrProviderGroup');
    if (ocrGroup) {
        ocrGroup.style.display = 'block';
    }
    
    // 隐藏页码选项（图片不需要页码）
    const pagesGroup = document.querySelector('#pagesInput').closest('.option-group');
    if (pagesGroup) {
        pagesGroup.style.display = 'none';
    }
}

// 处理批量文件选择（支持图片或PDF，不支持混合）
function handleBatchFileSelect(eventOrFiles) {
    const files = Array.isArray(eventOrFiles)
        ? eventOrFiles
        : Array.from(eventOrFiles?.target?.files || []);
    if (files.length === 0) return;
    
    // 检查文件类型
    const hasImages = files.some(f => isImageFile(f));
    const hasPDFs = files.some(f => f.name.toLowerCase().endsWith('.pdf'));
    
    if (hasImages && hasPDFs) {
        alert('批量转换不支持混合PDF和图片，请分别上传');
        return;
    }

    // PDF 批量限制：最多 5 个，且过滤重复文件。
    if (hasPDFs) {
        const maxSize = 50 * 1024 * 1024;
        const dedupMap = new Map();
        const invalidFiles = [];

        for (const file of files) {
            const isPdf = file.name.toLowerCase().endsWith('.pdf') || (file.type && file.type.includes('pdf'));
            if (!isPdf) {
                invalidFiles.push(`${file.name} (不是PDF)`);
                continue;
            }
            if (file.size > maxSize) {
                invalidFiles.push(`${file.name} (超过50MB)`);
                continue;
            }
            const signature = `${file.name}::${file.size}::${file.lastModified || 0}`;
            if (!dedupMap.has(signature)) {
                dedupMap.set(signature, file);
            }
        }

        const uniquePdfFiles = Array.from(dedupMap.values());
        if (uniquePdfFiles.length > MAX_BATCH_PDF_FILES) {
            showError(`最多支持同时翻译 ${MAX_BATCH_PDF_FILES} 个不同的PDF文件`);
            return;
        }
        if (uniquePdfFiles.length === 0) {
            showError('请至少选择1个有效PDF文件');
            return;
        }
        if (invalidFiles.length > 0) {
            showError(`以下文件无效:\n${invalidFiles.join('\n')}`);
            return;
        }

        selectedFile = null;
        selectedImages = [];
        selectedFiles = uniquePdfFiles;
        isImageMode = false;
        isBatchMode = true;

        const dropText = dropZone.querySelector('.drop-text');
        dropText.innerHTML = `已选择 <strong>${uniquePdfFiles.length}</strong> 个PDF文件（最多${MAX_BATCH_PDF_FILES}个）`;
        dropText.style.color = 'var(--success-color)';

        // PDF 模式恢复页码选项，隐藏 OCR 图片选项。
        const ocrGroup = document.getElementById('ocrProviderGroup');
        if (ocrGroup) {
            ocrGroup.style.display = 'none';
        }
        const pagesGroup = document.querySelector('#pagesInput')?.closest('.option-group');
        if (pagesGroup) {
            pagesGroup.style.display = 'block';
        }
        const previewSection = document.getElementById('imagePreviewSection');
        if (previewSection) {
            previewSection.style.display = 'none';
        }

        optionsSection.style.display = 'block';

        const batchInfo = document.getElementById('batchInfo');
        if (batchInfo) {
            batchInfo.textContent = `已选择 ${uniquePdfFiles.length} 个PDF文件（上限 ${MAX_BATCH_PDF_FILES}）`;
            batchInfo.style.display = 'block';
        }
        return;
    }
    
    selectedFile = null;
    selectedFiles = files;
    isImageMode = hasImages;
    isBatchMode = true;
    
    // 更新拖放区域提示
    const dropText = dropZone.querySelector('.drop-text');
    dropText.innerHTML = `已选择 <strong>${files.length}</strong> 个${hasImages ? '图片' : 'PDF'}文件`;
    dropText.style.color = 'var(--success-color)';
    
    if (hasImages) {
        selectedImages = files;
        displayImagePreview(files);
        // 显示OCR引擎选择
        const ocrGroup = document.getElementById('ocrProviderGroup');
        if (ocrGroup) {
            ocrGroup.style.display = 'block';
        }
        // 隐藏页码选项
        const pagesGroup = document.querySelector('#pagesInput')?.closest('.option-group');
        if (pagesGroup) {
            pagesGroup.style.display = 'none';
        }
    }
    
    // 显示转换选项
    optionsSection.style.display = 'block';
    
    const batchInfo = document.getElementById('batchInfo');
    if (batchInfo) {
        batchInfo.textContent = `已选择 ${files.length} 个${isImageMode ? '图片' : 'PDF'}文件`;
        batchInfo.style.display = 'block';
    }
}

// 显示图片预览
function displayImagePreview(files) {
    const previewSection = document.getElementById('imagePreviewSection');
    const thumbnails = document.getElementById('imageThumbnails');
    
    if (!previewSection || !thumbnails) return;
    
    thumbnails.innerHTML = '';
    
    files.forEach((file, index) => {
        const reader = new FileReader();
        reader.onload = (e) => {
            const thumbnail = document.createElement('div');
            thumbnail.className = 'image-thumbnail';
            thumbnail.innerHTML = `
                <img src="${e.target.result}" alt="${file.name}">
                <div class="image-name">${file.name}</div>
                <button class="image-remove-btn" onclick="removeImage(${index})" title="删除">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="18" y1="6" x2="6" y2="18"></line>
                        <line x1="6" y1="6" x2="18" y2="18"></line>
                    </svg>
                </button>
            `;
            thumbnails.appendChild(thumbnail);
        };
        reader.readAsDataURL(file);
    });
    
    previewSection.style.display = 'block';
}

// 删除图片
function removeImage(index) {
    selectedImages.splice(index, 1);
    
    if (selectedImages.length === 0) {
        selectedFile = null;
        selectedFiles = [];
        isImageMode = false;
        const previewSection = document.getElementById('imagePreviewSection');
        if (previewSection) {
            previewSection.style.display = 'none';
        }
        // 隐藏选项区域
        optionsSection.style.display = 'none';
        // 重置拖放区域提示
        const dropText = dropZone.querySelector('.drop-text');
        dropText.innerHTML = '拖拽文件到这里';
        dropText.style.color = '';
    } else {
        if (!isBatchMode) {
            selectedFile = selectedImages[0];
        } else {
            selectedFiles = selectedImages;
        }
        displayImagePreview(selectedImages);
        // 更新提示文本
        const dropText = dropZone.querySelector('.drop-text');
        dropText.innerHTML = `已选择 <strong>${selectedImages.length}</strong> 个图片`;
    }
}

// ===== Tab Switching =====

function showPdfTab() {
    document.getElementById('docx-tab').style.display = 'none';
    document.getElementById('fileInput').click();
}

function showDocxTab() {
    document.getElementById('docx-tab').style.display = 'block';
    // Hide PDF-related sections
    const optionsSection = document.getElementById('optionsSection');
    const progressSection = document.getElementById('progressSection');
    const resultSection = document.getElementById('resultSection');
    const imagePreviewSection = document.getElementById('imagePreviewSection');
    if (optionsSection) optionsSection.style.display = 'none';
    if (progressSection) progressSection.style.display = 'none';
    if (resultSection) resultSection.style.display = 'none';
    if (imagePreviewSection) imagePreviewSection.style.display = 'none';
}

// ===== DOCX Upload Handling =====

let selectedDocxFiles = [];

function initDocxUpload() {
    const dropZone = document.getElementById('docx-drop-zone');
    const fileInput = document.getElementById('docx-input');
    const batchInput = document.getElementById('docx-batch-input');
    const convertBtn = document.getElementById('convert-docx-btn');

    if (!dropZone || !fileInput) return;

    // File selected (single)
    fileInput.addEventListener('change', (e) => {
        const files = Array.from(e.target.files).filter(f => f.name.endsWith('.docx'));
        if (files.length > 0) {
            handleDocxFilesSelect(files);
        }
    });

    // Batch file selected
    if (batchInput) {
        batchInput.addEventListener('change', (e) => {
            const files = Array.from(e.target.files).filter(f => f.name.endsWith('.docx'));
            if (files.length > 0) {
                handleDocxFilesSelect(files);
            }
        });
    }

    // Drag and drop
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('drag-over');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('drag-over');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
        const files = Array.from(e.dataTransfer.files).filter(f => f.name.endsWith('.docx'));
        if (files.length > 0) {
            handleDocxFilesSelect(files);
        }
    });

    // Convert button
    if (convertBtn) {
        convertBtn.addEventListener('click', convertDocxToLatex);
    }
}

function handleDocxFilesSelect(files) {
    selectedDocxFiles = files;
    const dropZone = document.getElementById('docx-drop-zone');
    const optionsSection = document.getElementById('docxOptionsSection');
    const dropText = dropZone?.querySelector('.drop-text');
    const dropSubtitle = dropZone?.querySelector('.drop-text-subtitle');

    if (dropText) {
        dropText.textContent = files.length === 1
            ? files[0].name
            : `已选择 ${files.length} 个文件`;
    }
    if (dropSubtitle) {
        dropSubtitle.textContent = '点击下方"开始转换"按钮进行转换';
    }

    if (optionsSection) {
        optionsSection.style.display = 'block';
    }
}

function removeDocxFile() {
    selectedDocxFiles = [];
    const dropZone = document.getElementById('docx-drop-zone');
    const optionsSection = document.getElementById('docxOptionsSection');
    const fileInput = document.getElementById('docx-input');
    const batchInput = document.getElementById('docx-batch-input');
    const progressSection = document.getElementById('docx-progress');
    const dropText = dropZone?.querySelector('.drop-text');
    const dropSubtitle = dropZone?.querySelector('.drop-text-subtitle');

    if (dropZone) dropZone.style.display = 'block';
    if (optionsSection) optionsSection.style.display = 'none';
    if (progressSection) progressSection.style.display = 'none';
    if (fileInput) fileInput.value = '';
    if (batchInput) batchInput.value = '';
    if (dropText) dropText.textContent = '拖拽 Word 文件到此处';
    if (dropSubtitle) dropSubtitle.textContent = '支持 .docx 格式，可多选';
}

async function convertDocxToLatex() {
    if (selectedDocxFiles.length === 0) {
        showError('请先选择文件');
        return;
    }

    const convertBtn = document.getElementById('convert-docx-btn');
    const progressSection = document.getElementById('docx-progress');
    const progressText = document.getElementById('docx-progress-text');

    // Disable button and show loading
    if (convertBtn) {
        convertBtn.disabled = true;
        const btnText = convertBtn.querySelector('.btn-text');
        const btnLoading = convertBtn.querySelector('.btn-loading');
        if (btnText) btnText.style.display = 'none';
        if (btnLoading) btnLoading.style.display = 'inline-flex';
    }
    if (progressSection) progressSection.style.display = 'block';
    if (progressText) progressText.textContent = `正在上传和转换 ${selectedDocxFiles.length} 个文件...`;

    const formData = new FormData();
    selectedDocxFiles.forEach(file => {
        formData.append('files', file);
    });
    formData.append('model', document.getElementById('docx-model-select')?.value || 'deepseek-math');
    formData.append('template', document.getElementById('docx-template-select')?.value || 'article');
    formData.append('quality', document.getElementById('docx-quality-select')?.value || 'standard');
    formData.append('translate', document.getElementById('docx-translate')?.checked ? 'true' : 'false');
    formData.append('async_mode', document.getElementById('docx-async-option')?.checked ? 'true' : 'false');

    try {
        const response = await fetch('/api/convert-docx', {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (result.success) {
            if (progressText) progressText.textContent = `转换完成！共 ${selectedDocxFiles.length} 个文件`;

            if (result.results && result.results.length > 0) {
                displayLatexResult(result.results[0].latex, result.results[0].download_url);
            } else {
                displayLatexResult(result.latex, result.download_url);
            }

            setTimeout(() => {
                removeDocxFile();
            }, 1500);
        } else {
            throw new Error(result.error || '转换失败');
        }
    } catch (error) {
        showError('转换失败: ' + error.message);
    } finally {
        // Re-enable button
        if (convertBtn) {
            convertBtn.disabled = false;
            const btnText = convertBtn.querySelector('.btn-text');
            const btnLoading = convertBtn.querySelector('.btn-loading');
            if (btnText) btnText.style.display = 'inline-flex';
            if (btnLoading) btnLoading.style.display = 'none';
        }
        if (progressSection) progressSection.style.display = 'none';
    }
}

// 设置粘贴图片功能
function setupPasteImage() {
    document.addEventListener('paste', handlePaste);
}

// 处理粘贴事件
function handlePaste(event) {
    const items = event.clipboardData?.items;
    if (!items) return;
    
    for (let item of items) {
        if (item.type.indexOf('image') !== -1) {
            event.preventDefault();
            const blob = item.getAsFile();
            
            // 创建File对象
            const timestamp = new Date().getTime();
            const file = new File([blob], `screenshot_${timestamp}.png`, { type: 'image/png' });
            
            selectedFile = file;
            selectedFiles = [];
            selectedImages = [file];
            isImageMode = true;
            isBatchMode = false;
            
            // 更新拖放区域提示
            const dropText = dropZone.querySelector('.drop-text');
            dropText.innerHTML = `已粘贴截图: <strong>${file.name}</strong>`;
            dropText.style.color = 'var(--success-color)';
            
            displayImagePreview([file]);
            
            // 显示转换选项
            optionsSection.style.display = 'block';
            
            // 显示OCR引擎选择
            const ocrGroup = document.getElementById('ocrProviderGroup');
            if (ocrGroup) {
                ocrGroup.style.display = 'block';
            }
            
            // 隐藏页码选项
            const pagesGroup = document.querySelector('#pagesInput')?.closest('.option-group');
            if (pagesGroup) {
                pagesGroup.style.display = 'none';
            }
            
            // 提示用户
            const pasteHint = document.getElementById('pasteHint');
            if (pasteHint) {
                pasteHint.style.display = 'block';
                pasteHint.textContent = '截图已粘贴';
                setTimeout(() => {
                    pasteHint.style.display = 'none';
                }, 3000);
            }
            
            break;
        }
    }
}

// 开始图片转换
async function startImageConversion() {
    if (!selectedFile) {
        alert('请先选择图片');
        return;
    }
    
    // 隐藏结果和错误，显示进度
    optionsSection.style.display = 'none';
    progressSection.style.display = 'block';
    resultSection.style.display = 'none';
    errorSection.style.display = 'none';
    tokenStats.style.display = 'none';
    
    // 重置并显示终端日志
    const terminalLog = document.getElementById('terminalLog');
    const terminalBody = document.getElementById('terminalBody');
    if (terminalLog) terminalLog.style.display = 'block';
    if (terminalBody) terminalBody.innerHTML = '';
    
    const timestamp = Date.now();
    currentTaskId = `task_${timestamp}`;
    currentPhaseRank = 0;
    resetPhaseProgress(document.getElementById('translateOption').checked);
    if (socket) {
        socket.emit('join_task', { task_id: currentTaskId });
    }
    addTerminalLog('info', `开始图片转换任务: ${currentTaskId}`);
    
    // 初始化进度
    updateProgress({
        percent: 0,
        current: 0,
        total: 100,
        message: '准备识别图片...',
        status: 'preparing'
    });
    
    const formData = new FormData();
    formData.append('task_id', currentTaskId);
    formData.append('file', selectedFile);
    const options = collectCommonOptions();
    formData.append('model', options.model);
    formData.append('template', options.template);
    formData.append('quality_mode', options.quality_mode);
    formData.append('translate', document.getElementById('translateOption').checked);
    formData.append('ocr_provider', document.getElementById('ocrProviderSelect')?.value || 'mixed');
    formData.append('add_document_wrapper', document.getElementById('wrapperOption').checked);
    
    try {
        const response = await fetch('/api/convert-image', {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (!response.ok) {
            throw new Error(result.error || '转换失败');
        }
        
        // 转换成功，等待WebSocket进度完成后再显示结果
        // showResult 会在 WebSocket 'completed' 状态时调用
        
    } catch (error) {
        console.error('转换失败:', error);
        showError(error.message);
    }
}

// 开始批量图片转换
async function startBatchImageConversion() {
    if (!selectedImages || selectedImages.length === 0) {
        alert('请先选择图片');
        return;
    }
    
    // 隐藏结果和错误，显示进度
    optionsSection.style.display = 'none';
    progressSection.style.display = 'block';
    resultSection.style.display = 'none';
    errorSection.style.display = 'none';
    tokenStats.style.display = 'none';
    
    // 重置并显示终端日志
    const terminalLog = document.getElementById('terminalLog');
    const terminalBody = document.getElementById('terminalBody');
    if (terminalLog) terminalLog.style.display = 'block';
    if (terminalBody) terminalBody.innerHTML = '';
    
    const timestamp = Date.now();
    currentTaskId = `task_${timestamp}`;
    currentPhaseRank = 0;
    if (socket) {
        socket.emit('join_task', { task_id: currentTaskId });
    }
    addTerminalLog('info', `开始批量图片转换任务: ${currentTaskId} (共 ${selectedImages.length} 张)`);
    
    // 初始化进度
    updateProgress({
        percent: 0,
        current: 0,
        total: selectedImages.length,
        message: `准备识别 ${selectedImages.length} 张图片...`,
        status: 'preparing'
    });
    
    const formData = new FormData();
    formData.append('task_id', currentTaskId);
    selectedImages.forEach(file => {
        formData.append('files', file);
    });
    const options = collectCommonOptions();
    formData.append('model', options.model);
    formData.append('template', options.template);
    formData.append('quality_mode', options.quality_mode);
    formData.append('translate', document.getElementById('translateOption').checked);
    formData.append('ocr_provider', document.getElementById('ocrProviderSelect')?.value || 'mixed');
    formData.append('add_document_wrapper', document.getElementById('wrapperOption').checked);
    
    try {
        const response = await fetch('/api/convert-images', {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (!response.ok) {
            throw new Error(result.error || '批量转换失败');
        }
        
        // 批量转换成功
        addTerminalLog('success', `批量转换完成，共处理 ${result.successful_images} 张图片`);
        
    } catch (error) {
        console.error('批量转换失败:', error);
        showError(error.message);
    }
}



