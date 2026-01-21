// PDF2LaTeX Enhanced - 增强版前端脚本

let selectedFile = null;
let selectedFiles = [];  // 批量文件
let downloadUrl = null;
let latexContent = null;
let socket = null;
let currentTaskId = null;
let isBatchMode = false;  // 是否批量模式

// DOM元素
const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const optionsSection = document.getElementById('optionsSection');
const progressSection = document.getElementById('progressSection');
const resultSection = document.getElementById('resultSection');
const errorSection = document.getElementById('errorSection');
const convertBtn = document.getElementById('convertBtn');
const progressText = document.getElementById('progressText');
const progressBarFill = document.getElementById('progressBarFill');
const progressDetail = document.getElementById('progressDetail');
const tokenStats = document.getElementById('tokenStats');
const codeContent = document.getElementById('codeContent');
const codeLines = document.getElementById('codeLines');
const downloadBtn = document.getElementById('downloadBtn');
const errorMessage = document.getElementById('errorMessage');

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    setupDragAndDrop();
    setupFileInput();
    setupBatchFileInput();
    setupConvertButton();
    initWebSocket();
    loadAvailableModels();
});

// 初始化WebSocket
function initWebSocket() {
    socket = io({
        transports: ['websocket', 'polling'],  // 支持多种传输方式
        reconnection: true,
        reconnectionDelay: 1000,
        reconnectionDelayMax: 5000,
        reconnectionAttempts: 5,
        timeout: 120000,  // 120秒超时
        pingTimeout: 120000,
        pingInterval: 25000
    });
    
    socket.on('connect', () => {
        console.log('WebSocket 已连接');
    });
    
    socket.on('disconnect', (reason) => {
        console.log('WebSocket 已断开:', reason);
        if (reason === 'io server disconnect') {
            // 服务器主动断开，尝试重连
            socket.connect();
        }
    });
    
    socket.on('connect_error', (error) => {
        console.error('WebSocket 连接错误:', error);
    });
    
    socket.on('reconnect', (attemptNumber) => {
        console.log('WebSocket 重连成功，尝试次数:', attemptNumber);
    });
    
    socket.on('reconnect_error', (error) => {
        console.error('WebSocket 重连失败:', error);
    });
    
    socket.on('progress', (data) => {
        updateProgress(data);
    });
}

// 更新进度
function updateProgress(data) {
    console.log('进度更新:', data);
    
    progressBarFill.style.width = `${data.percent}%`;
    progressText.textContent = data.message;
    progressDetail.textContent = `${data.current} / ${data.total}`;
    
    // 根据状态显示不同的消息
    if (data.status === 'extracting') {
        progressText.textContent = `📄 ${data.message}`;
    } else if (data.status === 'translating') {
        progressText.textContent = `🌏 ${data.message}`;
        tokenStats.style.display = 'block';
    } else if (data.status === 'converting') {
        progressText.textContent = `⚙️ ${data.message}`;
        tokenStats.style.display = 'block';
    } else if (data.status === 'completed') {
        progressText.textContent = `✅ ${data.message}`;
    }
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
    const files = dt.files;
    
    if (files.length > 1) {
        // 多个文件 - 批量模式
        handleBatchFileSelect(Array.from(files));
    } else if (files.length === 1) {
        // 单个文件
        handleFileSelect(files[0]);
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
                handleBatchFileSelect(Array.from(e.target.files));
            }
        });
    }
}

// 处理文件选择
function handleFileSelect(file) {
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
    isBatchMode = false;
    
    const dropText = dropZone.querySelector('.drop-text');
    dropText.innerHTML = `✓ 已选择: <strong>${file.name}</strong>`;
    dropText.style.color = 'var(--success-color)';
    
    optionsSection.style.display = 'block';
    optionsSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// 处理批量文件选择
function handleBatchFileSelect(files) {
    // 验证文件
    const maxFiles = 10;
    if (files.length > maxFiles) {
        showError(`最多支持同时上传${maxFiles}个文件`);
        return;
    }

    const maxSize = 50 * 1024 * 1024;
    const validFiles = [];
    const invalidFiles = [];

    for (const file of files) {
        if (!file.type.includes('pdf') && !file.name.toLowerCase().endsWith('.pdf')) {
            invalidFiles.push(`${file.name} (不是PDF)`);
        } else if (file.size > maxSize) {
            invalidFiles.push(`${file.name} (超过50MB)`);
        } else {
            validFiles.push(file);
        }
    }

    if (invalidFiles.length > 0) {
        showError(`以下文件无效:\n${invalidFiles.join('\n')}`);
        if (validFiles.length === 0) return;
    }

    selectedFiles = validFiles;
    selectedFile = null;
    isBatchMode = true;

    const dropText = dropZone.querySelector('.drop-text');
    dropText.innerHTML = `✓ 已选择 <strong>${validFiles.length}</strong> 个文件:<br>` +
        validFiles.map(f => `<small>• ${f.name}</small>`).join('<br>');
    dropText.style.color = 'var(--success-color)';

    optionsSection.style.display = 'block';
    optionsSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// 设置转换按钮
function setupConvertButton() {
    convertBtn.addEventListener('click', startConversion);
}

// 开始转换
async function startConversion() {
    if (!selectedFile && selectedFiles.length === 0) {
        showError('请先选择PDF文件');
        return;
    }

    if (isBatchMode && selectedFiles.length > 0) {
        startBatchConversion();
    } else {
        startSingleConversion();
    }
}

// 单文件转换
async function startSingleConversion() {
    const translate = document.getElementById('translateOption').checked;
    const addWrapper = document.getElementById('wrapperOption').checked;
    const pages = document.getElementById('pagesInput').value.trim();

    optionsSection.style.display = 'none';
    progressSection.style.display = 'block';
    resultSection.style.display = 'none';
    errorSection.style.display = 'none';
    tokenStats.style.display = 'none';

    updateProgress({
        percent: 5,
        current: 0,
        total: 100,
        message: '准备上传文件...',
        status: 'preparing'
    });

    try {
        const formData = new FormData();
        formData.append('file', selectedFile);
        formData.append('translate', translate);
        formData.append('add_wrapper', addWrapper);
        if (pages) {
            formData.append('pages', pages);
        }

        updateProgress({
            percent: 10,
            current: 1,
            total: 100,
            message: '正在上传文件...',
            status: 'uploading'
        });

        const response = await fetch('/api/convert', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || '转换失败');
        }

        const result = await response.json();
        
        if (result.task_id) {
            currentTaskId = result.task_id;
            socket.emit('join_task', { task_id: result.task_id });
        }

        setTimeout(() => {
            showResult(result);
        }, 500);

    } catch (error) {
        console.error('转换错误:', error);
        showError(error.message || '转换过程中出现错误');
    }
}

// 批量转换
async function startBatchConversion() {
    const translate = document.getElementById('translateOption').checked;
    const addWrapper = document.getElementById('wrapperOption').checked;
    const pages = document.getElementById('pagesInput').value.trim();

    optionsSection.style.display = 'none';
    progressSection.style.display = 'block';
    resultSection.style.display = 'none';
    errorSection.style.display = 'none';
    tokenStats.style.display = 'none';

    updateProgress({
        percent: 5,
        current: 0,
        total: selectedFiles.length,
        message: `准备批量处理 ${selectedFiles.length} 个文件...`,
        status: 'preparing'
    });

    try {
        const formData = new FormData();
        
        // 添加所有文件
        for (const file of selectedFiles) {
            formData.append('files', file);
        }
        
        formData.append('translate', translate);
        formData.append('add_wrapper', addWrapper);
        if (pages) {
            formData.append('pages', pages);
        }

        updateProgress({
            percent: 10,
            current: 0,
            total: selectedFiles.length,
            message: '正在上传文件...',
            status: 'uploading'
        });

        const response = await fetch('/api/batch-convert', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || '批量转换失败');
        }

        const result = await response.json();
        
        if (result.batch_id) {
            currentTaskId = result.batch_id;
            socket.emit('join_task', { task_id: result.batch_id });
        }

        setTimeout(() => {
            showBatchResult(result);
        }, 500);

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

    // 使用 Prism.js 高亮显示代码
    codeContent.textContent = result.content;
    if (window.Prism) {
        Prism.highlightElement(codeContent);
    }
    
    // 统计行数
    const lines = result.content.split('\n').length;
    codeLines.textContent = `${lines} 行`;

    // 显示统计信息
    if (result.stats) {
        document.getElementById('resultPages').textContent = 
            `${result.stats.processed_pages} / ${result.stats.total_pages}`;
        document.getElementById('resultTokens').textContent = 
            result.stats.total_tokens.toLocaleString();
        document.getElementById('resultCost').textContent = 
            `$${result.stats.estimated_cost.toFixed(4)}`;
        document.getElementById('resultTime').textContent = 
            `${result.stats.processing_time}s`;
        
        // 更新Token统计（如果在进度中显示）
        document.getElementById('promptTokens').textContent = 
            result.stats.prompt_tokens.toLocaleString();
        document.getElementById('completionTokens').textContent = 
            result.stats.completion_tokens.toLocaleString();
        document.getElementById('totalTokens').textContent = 
            result.stats.total_tokens.toLocaleString();
        document.getElementById('estimatedCost').textContent = 
            `$${result.stats.estimated_cost.toFixed(4)}`;
    }

    // 设置下载按钮
    downloadBtn.onclick = () => {
        window.location.href = downloadUrl;
    };

    resultSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// 显示错误
function showError(message) {
    progressSection.style.display = 'none';
    optionsSection.style.display = 'none';
    errorSection.style.display = 'block';
    errorMessage.textContent = message;
    
    errorSection.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

// 复制到剪贴板（增强版，支持多种方式）
function copyToClipboard() {
    if (!latexContent) {
        showCopyMessage('没有可复制的内容', false);
        return;
    }

    const btn = event.target.closest('button');
    const originalHTML = btn.innerHTML;

    // 方法1: 使用现代 Clipboard API
    if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(latexContent)
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
        textarea.value = latexContent;
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
    toast.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: ${type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#3b82f6'};
        color: white;
        padding: 1rem 1.5rem;
        border-radius: 0.5rem;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
        z-index: 10000;
        animation: slideIn 0.3s ease;
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
function toggleFullscreen() {
    const codePreview = document.querySelector('.code-preview');
    codePreview.classList.toggle('fullscreen');
    
    const btn = event.target.closest('button');
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

    // 更新统计信息
    document.getElementById('resultPages').textContent = stats.total_pages;
    document.getElementById('resultTokens').textContent = stats.total_tokens.toLocaleString();
    document.getElementById('resultCost').textContent = `$${stats.total_cost.toFixed(4)}`;
    document.getElementById('resultTime').textContent = `${stats.total_time.toFixed(1)}s`;

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
            </div>
        </div>
        <div class="batch-results-list">
            ${results.map((r, idx) => `
                <div class="batch-result-item ${r.success ? 'success' : 'error'}">
                    <div class="batch-result-header">
                        <span class="batch-result-icon">${r.success ? '✅' : '❌'}</span>
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
                            <span>📄 ${r.stats.processed_pages} 页</span>
                            <span>🔤 ${r.stats.total_tokens.toLocaleString()} tokens</span>
                            <span>💰 $${r.stats.estimated_cost.toFixed(4)}</span>
                            <span>⏱️ ${r.stats.processing_time}s</span>
                        </div>
                    ` : `
                        <div class="batch-result-error">错误: ${r.error}</div>
                    `}
                </div>
            `).join('')}
        </div>
    `;

    resultSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// 下载批量结果
function downloadBatchResults(batchId) {
    window.location.href = `/api/download-batch/${batchId}`;
}

// 重置应用
function resetApp() {
    selectedFile = null;
    selectedFiles = [];
    downloadUrl = null;
    latexContent = null;
    currentTaskId = null;
    isBatchMode = false;

    const dropText = dropZone.querySelector('.drop-text');
    dropText.innerHTML = '拖拽PDF文件到这里';
    dropText.style.color = '';

    fileInput.value = '';
    const batchInput = document.getElementById('batchFileInput');
    if (batchInput) batchInput.value = '';
    
    document.getElementById('translateOption').checked = false;
    document.getElementById('wrapperOption').checked = true;
    document.getElementById('pagesInput').value = '';

    optionsSection.style.display = 'none';
    progressSection.style.display = 'none';
    resultSection.style.display = 'none';
    errorSection.style.display = 'none';
    tokenStats.style.display = 'none';

    window.scrollTo({ top: 0, behavior: 'smooth' });
}

// LaTeX本地渲染（使用KaTeX）
function renderLatex(content = null) {
    const contentToRender = content || latexContent;
    
    if (!contentToRender) {
        showToast('没有可渲染的LaTeX代码', 'error');
        return;
    }

    // 保存到localStorage供渲染页面使用
    localStorage.setItem('latexContent', contentToRender);
    
    // 在新窗口打开渲染页面
    window.open('/render', '_blank', 'width=1400,height=900');
}

// 为批量结果渲染特定文件
function renderBatchFile(fileContent, filename) {
    if (!fileContent) {
        showToast('无法获取文件内容', 'error');
        return;
    }
    
    // 保存到localStorage
    localStorage.setItem('latexContent', fileContent);
    localStorage.setItem('latexFilename', filename);
    
    // 打开渲染页面
    window.open('/render', '_blank', 'width=1400,height=900');
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