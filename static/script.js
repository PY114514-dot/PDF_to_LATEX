// PDF2LaTeX 前端交互逻辑

let selectedFile = null;
let downloadUrl = null;
let latexContent = null;

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
const codeContent = document.querySelector('#codeContent code');
const codeLines = document.getElementById('codeLines');
const downloadBtn = document.getElementById('downloadBtn');
const errorMessage = document.getElementById('errorMessage');

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    setupDragAndDrop();
    setupFileInput();
    setupConvertButton();
});

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
    
    if (files.length > 0) {
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

// 处理文件选择
function handleFileSelect(file) {
    // 检查文件类型
    if (!file.type.includes('pdf') && !file.name.toLowerCase().endsWith('.pdf')) {
        showError('请选择PDF文件');
        return;
    }

    // 检查文件大小 (50MB)
    const maxSize = 50 * 1024 * 1024;
    if (file.size > maxSize) {
        showError('文件大小超过50MB限制');
        return;
    }

    selectedFile = file;
    
    // 更新UI
    const dropText = dropZone.querySelector('.drop-text');
    dropText.textContent = `已选择: ${file.name}`;
    dropText.style.color = 'var(--success-color)';
    
    // 显示选项
    optionsSection.style.display = 'block';
    optionsSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// 设置转换按钮
function setupConvertButton() {
    convertBtn.addEventListener('click', startConversion);
}

// 开始转换
async function startConversion() {
    if (!selectedFile) {
        showError('请先选择PDF文件');
        return;
    }

    // 获取选项
    const translate = document.getElementById('translateOption').checked;
    const addWrapper = document.getElementById('wrapperOption').checked;
    const pages = document.getElementById('pagesInput').value.trim();

    // 隐藏选项，显示进度
    optionsSection.style.display = 'none';
    progressSection.style.display = 'block';
    resultSection.style.display = 'none';
    errorSection.style.display = 'none';

    // 更新进度文本
    updateProgress(10, translate ? '正在上传文件...' : '正在上传文件...');

    try {
        // 准备表单数据
        const formData = new FormData();
        formData.append('file', selectedFile);
        formData.append('translate', translate);
        formData.append('add_wrapper', addWrapper);
        if (pages) {
            formData.append('pages', pages);
        }

        updateProgress(30, translate ? '正在翻译并转换...' : '正在转换为LaTeX...');

        // 发送请求
        const response = await fetch('/api/convert', {
            method: 'POST',
            body: formData
        });

        updateProgress(90, '处理结果...');

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || '转换失败');
        }

        const result = await response.json();
        
        updateProgress(100, '完成！');

        // 显示结果
        setTimeout(() => {
            showResult(result);
        }, 500);

    } catch (error) {
        console.error('转换错误:', error);
        showError(error.message || '转换过程中出现错误');
    }
}

// 更新进度
function updateProgress(percent, text) {
    progressBarFill.style.width = `${percent}%`;
    progressText.textContent = text;
}

// 显示结果
function showResult(result) {
    progressSection.style.display = 'none';
    resultSection.style.display = 'block';

    // 保存数据
    downloadUrl = result.download_url;
    latexContent = result.content;

    // 显示代码
    codeContent.textContent = result.content;
    
    // 统计行数
    const lines = result.content.split('\n').length;
    codeLines.textContent = `${lines} 行`;

    // 设置下载按钮
    downloadBtn.onclick = () => {
        window.location.href = downloadUrl;
    };

    // 滚动到结果
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

// 复制到剪贴板（兼容多种方式）
function copyToClipboard() {
    if (!latexContent) {
        alert('没有可复制的内容');
        return;
    }

    const btn = event.target.closest('button');
    const originalHTML = btn.innerHTML;

    // 方法1: 使用现代 Clipboard API
    if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(latexContent)
            .then(() => {
                showCopySuccess(btn, originalHTML);
            })
            .catch(err => {
                console.error('Clipboard API 失败:', err);
                // 如果失败，尝试备用方法
                fallbackCopy(btn, originalHTML);
            });
    } else {
        // 不支持 Clipboard API，使用备用方法
        fallbackCopy(btn, originalHTML);
    }
}

// 备用复制方法
function fallbackCopy(btn, originalHTML) {
    try {
        // 创建临时 textarea
        const textarea = document.createElement('textarea');
        textarea.value = latexContent;
        textarea.style.position = 'fixed';
        textarea.style.top = '0';
        textarea.style.left = '0';
        textarea.style.width = '1px';
        textarea.style.height = '1px';
        textarea.style.padding = '0';
        textarea.style.border = 'none';
        textarea.style.outline = 'none';
        textarea.style.boxShadow = 'none';
        textarea.style.background = 'transparent';
        textarea.style.opacity = '0';
        
        document.body.appendChild(textarea);
        
        // 选择文本
        if (navigator.userAgent.match(/ipad|ipod|iphone/i)) {
            // iOS 设备特殊处理
            const range = document.createRange();
            range.selectNodeContents(textarea);
            const selection = window.getSelection();
            selection.removeAllRanges();
            selection.addRange(range);
            textarea.setSelectionRange(0, textarea.value.length);
        } else {
            textarea.select();
        }
        
        // 执行复制
        const successful = document.execCommand('copy');
        document.body.removeChild(textarea);
        
        if (successful) {
            showCopySuccess(btn, originalHTML);
        } else {
            showCopyError(btn, originalHTML);
        }
    } catch (err) {
        console.error('备用复制方法失败:', err);
        showCopyError(btn, originalHTML);
    }
}

// 显示复制成功
function showCopySuccess(btn, originalHTML) {
    btn.innerHTML = `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <polyline points="20 6 9 17 4 12"></polyline>
        </svg>
        已复制
    `;
    btn.style.background = 'var(--success-color)';
    btn.style.color = 'white';
    
    setTimeout(() => {
        btn.innerHTML = originalHTML;
        btn.style.background = '';
        btn.style.color = '';
    }, 2000);
}

// 显示复制失败
function showCopyError(btn, originalHTML) {
    btn.innerHTML = `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="12" y1="8" x2="12" y2="12"></line>
            <line x1="12" y1="16" x2="12.01" y2="16"></line>
        </svg>
        复制失败
    `;
    btn.style.background = 'var(--error-color)';
    btn.style.color = 'white';
    
    setTimeout(() => {
        btn.innerHTML = originalHTML;
        btn.style.background = '';
        btn.style.color = '';
        
        // 提示用户手动复制
        if (confirm('自动复制失败，是否打开新窗口以便手动复制？')) {
            const newWindow = window.open('', '_blank');
            newWindow.document.write('<pre style="white-space: pre-wrap; word-wrap: break-word; font-family: monospace; padding: 20px;">' + 
                latexContent.replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</pre>');
            newWindow.document.title = 'LaTeX 代码 - 请手动复制';
        }
    }, 2000);
}

// 重置应用
function resetApp() {
    selectedFile = null;
    downloadUrl = null;
    latexContent = null;

    // 重置UI
    const dropText = dropZone.querySelector('.drop-text');
    dropText.textContent = '拖拽PDF文件到这里';
    dropText.style.color = '';

    fileInput.value = '';
    document.getElementById('translateOption').checked = false;
    document.getElementById('wrapperOption').checked = true;
    document.getElementById('pagesInput').value = '';

    // 隐藏所有区域
    optionsSection.style.display = 'none';
    progressSection.style.display = 'none';
    resultSection.style.display = 'none';
    errorSection.style.display = 'none';

    // 滚动到顶部
    window.scrollTo({ top: 0, behavior: 'smooth' });
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

// 页面加载时检查API
checkApiStatus();
