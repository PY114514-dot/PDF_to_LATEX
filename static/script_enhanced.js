// PDF2LaTeX Enhanced - 增强版前端脚本

let selectedFile = null;
let selectedFiles = [];  // 批量文件
let selectedImages = [];  // 图片文件
let downloadUrl = null;
let latexContent = null;
let socket = null;
let currentTaskId = null;
let isBatchMode = false;  // 是否批量模式
let isImageMode = false;  // 是否图片模式

// 货币设置
const USD_TO_CNY_RATE = 7.2;  // 美元到人民币汇率

// 货币转换函数
function formatCurrency(usdAmount) {
    const cnyAmount = usdAmount * USD_TO_CNY_RATE;
    return `¥${cnyAmount.toFixed(2)}`;
}

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
    setupImageInput();
    setupBatchFileInput();
    setupPasteImage();
    setupConvertButton();
    initWebSocket();
    loadAvailableModels();
    loadHistory();
});

// 初始化WebSocket
function initWebSocket() {
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
        console.log('✅ WebSocket 已连接');
    });
    
    socket.on('disconnect', (reason) => {
        console.warn('⚠️ WebSocket 已断开:', reason);
        // 如果是ping timeout，尝试重连
        if (reason === 'ping timeout' || reason === 'transport close') {
            console.log('🔄 尝试重新连接...');
            setTimeout(() => socket.connect(), 1000);
        }
    });
    
    socket.on('connect_error', (error) => {
        console.error('❌ WebSocket 连接错误:', error.message);
    });
    
    socket.on('reconnect', (attemptNumber) => {
        console.log('✅ WebSocket 重连成功，尝试次数:', attemptNumber);
    });
    
    socket.on('reconnect_error', (error) => {
        console.error('❌ WebSocket 重连失败:', error.message);
    });
    
    socket.on('reconnect_attempt', () => {
        console.log('🔄 WebSocket 尝试重连...');
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
        'success': '✓',
        'warning': '⚠',
        'error': '✗',
        'quality': '📊',
        'progress': '⚙'
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

function clearTerminalLog() {
    const terminalBody = document.getElementById('terminalBody');
    terminalBody.innerHTML = '<div class="terminal-line"><span class="terminal-prompt">$</span><span class="terminal-text">日志已清空</span></div>';
}

// 更新进度
function updateProgress(data) {
    console.log('进度更新:', data);
    
    // 如果有token信息，更新token统计显示
    if (data.tokens) {
        document.getElementById('promptTokens').textContent = (data.tokens.prompt_tokens || 0).toLocaleString();
        document.getElementById('completionTokens').textContent = (data.tokens.completion_tokens || 0).toLocaleString();
        document.getElementById('totalTokens').textContent = (data.tokens.total_tokens || 0).toLocaleString();
        document.getElementById('estimatedCost').textContent = formatCurrency(data.tokens.estimated_cost || 0);
    }
    
    // 显示终端日志
    // 如果有log_message就用log_message，否则对于某些状态使用message
    const shouldShowLog = data.log_message || ['preparing', 'uploading', 'extracting', 'converting', 'translating', 'processing', 'completed'].includes(data.status);
    
    if (shouldShowLog) {
        const logMessage = data.log_message || data.message;
        const logType = data.log_type || getDefaultLogType(data.status);
        addTerminalLog(logType, logMessage);
    }
    
    // 平滑动画更新进度条
    progressBarFill.style.transition = 'width 0.3s ease';
    progressBarFill.style.width = `${Math.min(data.percent || 0, 100)}%`;
    
    // 根据状态显示不同的消息和图标
    let message = data.message || '';
    let icon = '';
    
    switch (data.status) {
        case 'preparing':
            icon = '⏳';
            break;
        case 'uploading':
            icon = '📤';
            break;
        case 'extracting':
            icon = '📄';
            message = data.message;
            break;
        case 'translating':
            icon = '🌏';
            tokenStats.style.display = 'block';
            break;
        case 'converting':
            icon = '⚙️';
            tokenStats.style.display = 'block';
            break;
        case 'processing':
            icon = '🔄';
            break;
        case 'completed':
            icon = '✅';
            progressBarFill.style.width = '100%';
            break;
        default:
            icon = '📊';
    }
    
    // 更新文本（如果消息中没有图标，则添加）
    if (!message.match(/^[📄📤⏳🌏⚙️✅🔄📊📦📸]/)) {
        progressText.textContent = `${icon} ${message}`;
    } else {
        progressText.textContent = message;
    }
    
    // 更新详细信息 - 显示页码/图片进度
    if (data.status === 'uploading') {
        // 上传时显示百分比
        progressDetail.textContent = `${data.percent || 0}%`;
    } else if (data.status === 'converting' || data.status === 'translating') {
        // 转换/翻译时显示页码/图片进度
        if (data.current !== undefined && data.total !== undefined) {
            // 如果是图片模式，显示"第 x/y 张"，否则显示"第 x/y 页"
            const unit = isImageMode ? '张' : '页';
            progressDetail.textContent = `第 ${data.current}/${data.total} ${unit}`;
            progressDetail.style.fontSize = '1.1rem';
            progressDetail.style.fontWeight = '600';
            progressDetail.style.color = 'var(--primary-color)';
        } else {
            progressDetail.textContent = '处理中...';
        }
    } else if (data.status === 'extracting') {
        // 提取时显示页码
        if (data.current !== undefined && data.total !== undefined) {
            progressDetail.textContent = `${data.current} / ${data.total} 页`;
        } else {
            progressDetail.textContent = '提取中...';
        }
    } else if (data.status === 'completed') {
        // 完成时显示完成标记
        if (data.total !== undefined) {
            const unit = isImageMode ? '张图片' : '页';
            progressDetail.textContent = `✓ 已完成 ${data.total} ${unit}`;
        } else {
            progressDetail.textContent = '✓ 已完成';
        }
        progressDetail.style.color = 'var(--success-color)';
    } else {
        // 其他情况显示当前/总数
        if (data.current !== undefined && data.total !== undefined) {
            progressDetail.textContent = `${data.current} / ${data.total}`;
        } else {
            progressDetail.textContent = '处理中...';
        }
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
                handleBatchFileSelect(Array.from(e.target.files));
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
    isBatchMode = false;
    
    const dropText = dropZone.querySelector('.drop-text');
    dropText.innerHTML = `✓ 已选择: <strong>${file.name}</strong> <span style="color: #888;">(正在检测页数...)</span>`;
    dropText.style.color = 'var(--success-color)';
    
    optionsSection.style.display = 'block';
    
    // 获取PDF页数
    try {
        const pageCount = await getPdfPageCount(file);
        dropText.innerHTML = `✓ 已选择: <strong>${file.name}</strong> <span style="color: #888;">(共 ${pageCount} 页)</span>`;
        
        // 更新页码输入提示
        const pagesInput = document.getElementById('pagesInput');
        pagesInput.placeholder = `例如: 1-3,5,7-9 (共${pageCount}页)`;
    } catch (error) {
        console.error('获取页数失败:', error);
        dropText.innerHTML = `✓ 已选择: <strong>${file.name}</strong>`;
    }
    
    optionsSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// 处理批量文件选择
async function handleBatchFileSelect(files) {
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
    dropText.innerHTML = `✓ 已选择 <strong>${validFiles.length}</strong> 个文件 <span style="color: #888;">(正在检测页数...)</span>`;
    dropText.style.color = 'var(--success-color)';
    
    optionsSection.style.display = 'block';
    
    // 异步获取所有文件的页数
    try {
        const fileInfos = await Promise.all(
            validFiles.map(async (file) => {
                try {
                    const pageCount = await getPdfPageCount(file);
                    return { name: file.name, pages: pageCount };
                } catch (error) {
                    console.error(`获取${file.name}页数失败:`, error);
                    return { name: file.name, pages: '?' };
                }
            })
        );
        
        const totalPages = fileInfos.reduce((sum, info) => sum + (typeof info.pages === 'number' ? info.pages : 0), 0);
        
        dropText.innerHTML = `✓ 已选择 <strong>${validFiles.length}</strong> 个文件 <span style="color: #888;">(共 ${totalPages} 页)</span>:<br>` +
            fileInfos.map(info => `<small>• ${info.name} (${info.pages}页)</small>`).join('<br>');
    } catch (error) {
        console.error('批量获取页数失败:', error);
        dropText.innerHTML = `✓ 已选择 <strong>${validFiles.length}</strong> 个文件:<br>` +
            validFiles.map(f => `<small>• ${f.name}</small>`).join('<br>');
    }

    optionsSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// 设置转换按钮
function setupConvertButton() {
    convertBtn.addEventListener('click', startConversion);
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
    const model = document.getElementById('modelSelect').value;

    optionsSection.style.display = 'none';
    progressSection.style.display = 'block';
    resultSection.style.display = 'none';
    errorSection.style.display = 'none';
    tokenStats.style.display = 'none';
    
    // 生成task_id并提前加入room
    const timestamp = Date.now();
    const taskId = `task_${timestamp}`;
    currentTaskId = taskId;
    socket.emit('join_task', { task_id: taskId });
    
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
        message: '📤 准备上传文件...',
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
        formData.append('file', selectedFile);
        formData.append('translate', translate);
        formData.append('add_wrapper', addWrapper);
        formData.append('model', model);
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
                    message: `📤 正在上传文件... ${formatBytes(e.loaded)} / ${formatBytes(e.total)}`,
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
                message: '✅ 文件上传完成，开始处理...',
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
            
            xhr.open('POST', '/api/convert');
            xhr.timeout = 1800000; // 30分钟超时（翻译需要更长时间）
            xhr.send(formData);
        });

        const result = await uploadPromise;

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
    const translate = document.getElementById('translateOption').checked;
    const addWrapper = document.getElementById('wrapperOption').checked;
    const pagesInput = document.getElementById('pagesInput').value.trim();
    const model = document.getElementById('modelSelect').value;

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
    addTerminalLog('info', `开始批量转换 ${selectedFiles.length} 个文件...`);

    updateProgress({
        percent: 0,
        current: 0,
        total: selectedFiles.length,
        message: `📦 准备批量处理 ${selectedFiles.length} 个文件...`,
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
        formData.append('model', model);
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
                    message: `📤 正在上传 ${selectedFiles.length} 个文件... ${formatBytes(e.loaded)} / ${formatBytes(e.total)}`,
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
                message: '✅ 文件上传完成，开始批量处理...',
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
        
        // 不再直接调用 showBatchResult，等待 WebSocket 的 'completed' 事件
        // WebSocket 会在转换完成时自动调用 showBatchResult
        console.log('批量转换请求已发送，等待 WebSocket 完成通知...');

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

    // 显示统计信息（使用人民币）
    if (result.stats) {
        // 处理页数显示 - 如果是图片则显示"1 张"，否则显示"x / y"
        const pagesText = isImageMode 
            ? `${result.stats.processed_pages || 1} 张`
            : `${result.stats.processed_pages || 0} / ${result.stats.total_pages || 0}`;
        document.getElementById('resultPages').textContent = pagesText;
        
        document.getElementById('resultTokens').textContent = 
            (result.stats.total_tokens || 0).toLocaleString();
        document.getElementById('resultCost').textContent = 
            formatCurrency(result.stats.estimated_cost || 0);
        document.getElementById('resultTime').textContent = 
            `${result.stats.processing_time || 0}s`;
        
        // 更新Token统计（如果在进度中显示）
        document.getElementById('promptTokens').textContent = 
            (result.stats.prompt_tokens || 0).toLocaleString();
        document.getElementById('completionTokens').textContent = 
            (result.stats.completion_tokens || 0).toLocaleString();
        document.getElementById('totalTokens').textContent = 
            (result.stats.total_tokens || 0).toLocaleString();
        document.getElementById('estimatedCost').textContent = 
            formatCurrency(result.stats.estimated_cost || 0);
    } else {
        // 如果没有stats，显示默认值
        const pagesText = isImageMode ? '1 张' : '0 / 0';
        document.getElementById('resultPages').textContent = pagesText;
        document.getElementById('resultTokens').textContent = '0';
        document.getElementById('resultCost').textContent = '¥0.00';
        document.getElementById('resultTime').textContent = '0s';
        
        document.getElementById('promptTokens').textContent = '0';
        document.getElementById('completionTokens').textContent = '0';
        document.getElementById('totalTokens').textContent = '0';
        document.getElementById('estimatedCost').textContent = '¥0.00';
    }

    // 设置下载按钮
    downloadBtn.onclick = () => {
        window.location.href = downloadUrl;
    };

    // 刷新历史记录
    loadHistory();

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

    // 更新统计信息（使用人民币）
    const pagesText = isImageMode 
        ? `${stats.total_pages || stats.successful_files || 0} 张`
        : `${stats.total_pages || 0}`;
    document.getElementById('resultPages').textContent = pagesText;
    document.getElementById('resultTokens').textContent = (stats.total_tokens || 0).toLocaleString();
    document.getElementById('resultCost').textContent = formatCurrency(stats.total_cost || 0);
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
                            <span>💰 ${formatCurrency(r.stats.estimated_cost)}</span>
                            <span>⏱️ ${r.stats.processing_time}s</span>
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
    safeStorage.setItem('latexContent', contentToRender);
    
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
    safeStorage.setItem('latexContent', fileContent);
    safeStorage.setItem('latexFilename', filename);
    
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

// ==================== 历史记录功能 ====================

// 加载历史记录
async function loadHistory() {
    const historyList = document.getElementById('historyList');
    
    try {
        const response = await fetch('/api/history?limit=10');
        const data = await response.json();
        
        if (data.success && data.history && data.history.length > 0) {
            historyList.innerHTML = data.history.map((record, index) => {
                const date = new Date(record.timestamp);
                const dateStr = date.toLocaleString('zh-CN');
                const model = record.model || 'unknown';
                const translated = record.translated ? '是' : '否';
                const pages = record.pages || 'all';
                const cost = record.stats?.estimated_cost || 0;
                const tokens = record.stats?.total_tokens || 0;
                
                return `
                    <div class="history-item" onclick="viewHistory(${index})">
                        <div class="history-icon">📄</div>
                        <div class="history-info">
                            <div class="history-filename">${record.filename}</div>
                            <div class="history-meta">
                                <span>🤖 ${model}</span>
                                <span>🌏 翻译: ${translated}</span>
                                <span>📄 页码: ${pages}</span>
                                <span>💰 ${formatCurrency(cost)}</span>
                                <span>🔢 ${tokens.toLocaleString()} tokens</span>
                                <span>⏰ ${dateStr}</span>
                            </div>
                        </div>
                        <div class="history-actions" onclick="event.stopPropagation()">
                            <button class="history-action-btn primary" onclick="downloadHistory(${index})">
                                📥 下载
                            </button>
                            <button class="history-action-btn secondary" onclick="viewHistory(${index})">
                                👁️ 查看
                            </button>
                        </div>
                    </div>
                `;
            }).join('');
        } else {
            historyList.innerHTML = `
                <div class="history-empty">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
                    </svg>
                    <p>暂无历史记录</p>
                </div>
            `;
        }
    } catch (error) {
        console.error('加载历史记录失败:', error);
        historyList.innerHTML = `
            <div class="history-empty">
                <p>加载历史记录失败</p>
            </div>
        `;
    }
}

// 刷新历史记录
function refreshHistory() {
    loadHistory();
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
                const fileResponse = await fetch(`/api/download/${filename}`);
                const latexContent = await fileResponse.text();
                
                // 保存到localStorage并打开渲染页面
                safeStorage.setItem('latexContent', latexContent);
                safeStorage.setItem('latexFilename', filename);
                
                // 在新窗口打开渲染页面
                window.open('/render', '_blank', 'width=1400,height=900');
            }
        } else {
            alert('记录不存在');
        }
    } catch (error) {
        console.error('查看历史记录失败:', error);
        alert('查看失败: ' + error.message);
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
                window.location.href = `/api/download/${filename}`;
            }
        } else {
            alert('记录不存在');
        }
    } catch (error) {
        console.error('下载历史记录失败:', error);
        alert('下载失败: ' + error.message);
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
    dropText.innerHTML = `✓ 已选择图片: <strong>${file.name}</strong>`;
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

// 处理批量文件选择（支持图片和PDF混合）
function handleBatchFileSelect(event) {
    const files = Array.from(event.target.files);
    if (files.length === 0) return;
    
    // 检查文件类型
    const hasImages = files.some(f => isImageFile(f));
    const hasPDFs = files.some(f => f.name.toLowerCase().endsWith('.pdf'));
    
    if (hasImages && hasPDFs) {
        alert('批量转换不支持混合PDF和图片，请分别上传');
        return;
    }
    
    selectedFile = null;
    selectedFiles = files;
    isImageMode = hasImages;
    isBatchMode = true;
    
    // 更新拖放区域提示
    const dropText = dropZone.querySelector('.drop-text');
    dropText.innerHTML = `✓ 已选择 <strong>${files.length}</strong> 个${hasImages ? '图片' : 'PDF'}文件`;
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
        dropText.innerHTML = `✓ 已选择 <strong>${selectedImages.length}</strong> 个图片`;
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
            dropText.innerHTML = `✓ 已粘贴截图: <strong>${file.name}</strong>`;
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
                pasteHint.textContent = '✅ 截图已粘贴！';
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
    socket.emit('join_task', { task_id: currentTaskId });
    addTerminalLog('info', `开始图片转换任务: ${currentTaskId}`);
    
    // 初始化进度
    updateProgress({
        percent: 0,
        current: 0,
        total: 100,
        message: '📸 准备识别图片...',
        status: 'preparing'
    });
    
    const formData = new FormData();
    formData.append('task_id', currentTaskId);
    formData.append('file', selectedFile);
    formData.append('model', document.getElementById('modelSelect').value);
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
    socket.emit('join_task', { task_id: currentTaskId });
    addTerminalLog('info', `开始批量图片转换任务: ${currentTaskId} (共 ${selectedImages.length} 张)`);
    
    // 初始化进度
    updateProgress({
        percent: 0,
        current: 0,
        total: selectedImages.length,
        message: `📸 准备识别 ${selectedImages.length} 张图片...`,
        status: 'preparing'
    });
    
    const formData = new FormData();
    formData.append('task_id', currentTaskId);
    selectedImages.forEach(file => {
        formData.append('files', file);
    });
    formData.append('model', document.getElementById('modelSelect').value);
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
        addTerminalLog('success', `✅ 批量转换完成！共处理 ${result.successful_images} 张图片`);
        
    } catch (error) {
        console.error('批量转换失败:', error);
        showError(error.message);
    }
}