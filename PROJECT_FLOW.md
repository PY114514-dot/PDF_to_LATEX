# PDF2LaTeX 项目流程详解

## 📚 目录
1. [项目架构](#项目架构)
2. [PDF转LaTeX流程](#pdf转latex流程)
3. [图片转LaTeX流程](#图片转latex流程)
4. [核心技术](#核心技术)
5. [数据流向](#数据流向)

---

## 🏗️ 项目架构

### 整体架构
```
前端 (HTML/JS) ←→ WebSocket + HTTP API ←→ Flask 后端 ←→ 核心处理模块 ←→ LLM API
                                              ↓
                                          历史管理
                                              ↓
                                        文件存储系统
```

### 核心模块

| 模块 | 文件 | 功能 |
|------|------|------|
| **Web应用** | `app_enhanced.py` | Flask主程序，路由管理，WebSocket通信 |
| **PDF处理** | `pdf2latex_enhanced.py` | PDF文本提取和LaTeX转换 |
| **图片处理** | `image2latex_enhanced.py` | 图片OCR识别和LaTeX转换 |
| **OCR引擎** | `ocr_client.py` | Tesseract + Vision API混合OCR |
| **LLM客户端** | `clients.py` | 统一的LLM调用接口 |
| **配置管理** | `config.py` | API密钥和系统设置 |
| **历史管理** | `history_manager.py` | 转换历史记录 |

---

## 📄 PDF转LaTeX流程

### 流程图
```
1. 用户上传PDF
        ↓
2. 前端获取PDF页数
        ↓
3. 用户选择页码范围/模型
        ↓
4. 开始转换 (WebSocket建立)
        ↓
5. PDF文本提取 (pdfplumber/PyPDF2)
        ↓
6. 文本质量检测
        ↓
7. LLM转换为LaTeX (可选翻译)
        ↓
8. 生成.tex文件
        ↓
9. 返回结果给前端
```

### 详细步骤

#### 第1步：文件上传
**文件**: `app_enhanced.py` → `/api/convert` 路由

```python
# 前端通过 FormData 上传PDF文件
POST /api/convert
Content-Type: multipart/form-data

参数:
- file: PDF文件
- pages: 页码范围 (如 "1-3,5,7-9")
- model: 模型名称 (如 "deepseek-chat")
- translate: 是否翻译 (true/false)
- add_wrapper: 是否添加LaTeX文档包装
- task_id: 任务ID (用于WebSocket通信)
```

#### 第2步：获取PDF页数
**文件**: `app_enhanced.py` → `/api/get-pdf-pages` 路由

```python
# 使用 PyPDF2 快速读取PDF页数
with open(filepath, 'rb') as pdf_file:
    pdf_reader = PyPDF2.PdfReader(pdf_file)
    total_pages = len(pdf_reader.pages)
```

**前端显示**: "共 X 页"

#### 第3步：PDF文本提取
**文件**: `pdf2latex_enhanced.py` → `extract_text_from_pdf()` 方法

**策略**: 多方法提取 + 质量检测

```python
提取方法优先级:
1. pdfplumber (首选) - 效果最好
   ↓ (如果质量低)
2. PyPDF2 (备用) - 兼容性好

质量检测标准:
- 可读字符比例
- 乱码字符检测
- 文本长度
```

**关键代码流程**:
```python
# 1. 只提取用户选择的页面
pages_to_extract = [0, 1, 2]  # 用户选择 1-3 页

# 2. 使用 pdfplumber 提取
with pdfplumber.open(pdf_path) as pdf:
    for page_num in pages_to_extract:
        page = pdf.pages[page_num]
        text = page.extract_text()
        
        # 3. 检查文本质量
        quality = self._check_text_quality(text)
        
        # 4. 如果质量低，尝试 PyPDF2 备用
        if quality < 0.5:
            # 使用 PyPDF2 重新提取
            backup_text = pypdf2_extract(page_num)
            if backup_quality > quality:
                text = backup_text
```

**实时进度**:
```python
self._emit_progress(
    'extracting',
    idx + 1,
    total_pages,
    f'已提取 {idx + 1}/{total_pages} 页',
    'success',
    f'✓ 第 {page_num + 1} 页提取完成 (质量: {quality:.0%})'
)
```

#### 第4步：LLM转换为LaTeX
**文件**: `pdf2latex_enhanced.py` → `convert_text_to_latex()` 方法

**转换流程**:
```python
# 1. 检查文本质量
quality = self._check_text_quality(text)

# 2. 如果需要翻译，先翻译
if translate:
    text = self.translate_text(text, page_num, total_pages)

# 3. 构建提示词
system_prompt = """你是一个专业的LaTeX转换助手。
要求：
1. 识别数学公式，使用LaTeX数学环境
2. 识别文本结构，使用对应的LaTeX命令
3. 不要输出文档结构命令"""

user_prompt = f"""请将以下文本转换为LaTeX格式：
{text}
只输出LaTeX内容代码。"""

# 4. 调用LLM
response = await self.client.chat(
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ],
    temperature=0.3,
    max_tokens=4000
)

# 5. 提取LaTeX内容
latex_content = response['choices'][0]['message']['content']

# 6. 清理多余的文档结构
latex_content = self._clean_document_structure(latex_content)
```

**Token统计**:
```python
# 记录每次调用的Token使用
self.prompt_tokens += usage.get('prompt_tokens', 0)
self.completion_tokens += usage.get('completion_tokens', 0)
self.total_tokens += usage.get('total_tokens', 0)

# 计算成本
input_cost = (prompt_tokens / 1_000_000) * price_per_million_input
output_cost = (completion_tokens / 1_000_000) * price_per_million_output
```

#### 第5步：生成LaTeX文件
**文件**: `pdf2latex_enhanced.py` → `convert_pdf()` 方法

```python
# 1. 组装所有页面的LaTeX内容
latex_content = []

if add_document_wrapper:
    latex_content.append(r"\documentclass{article}")
    latex_content.append(r"\usepackage{amsmath,amssymb}")
    if translate:
        latex_content.append(r"\usepackage{xeCJK}")
    latex_content.append(r"\begin{document}")

# 2. 添加每页内容
for page_num in pages:
    latex_content.append(f"% ===== 第 {page_num + 1} 页 =====")
    latex_content.append(converted_latex)
    latex_content.append("")

if add_document_wrapper:
    latex_content.append(r"\end{document}")

# 3. 写入文件
with open(output_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(latex_content))
```

#### 第6步：返回结果
**文件**: `app_enhanced.py` → `/api/convert` 路由

```python
# 1. 读取生成的LaTeX内容
with open(output_path, 'r', encoding='utf-8') as f:
    latex_content = f.read()

# 2. 保存历史记录
history_manager.add_record({
    'filename': filename,
    'model': model,
    'translated': translate,
    'pages': pages_str,
    'output_file': str(output_path),
    'stats': {...}
})

# 3. 通过WebSocket发送完成状态
socketio.emit('progress', {
    'task_id': task_id,
    'status': 'completed',
    'result': {
        'content': latex_content,
        'download_url': f'/api/download/{output_filename}',
        'stats': {...}
    }
}, room=task_id)

# 4. 通过HTTP返回结果
return jsonify({
    'success': True,
    'content': latex_content,
    'stats': {...}
})
```

---

## 🖼️ 图片转LaTeX流程

### 流程图
```
1. 用户上传图片/粘贴截图
        ↓
2. 前端预览图片
        ↓
3. 用户选择OCR引擎/模型
        ↓
4. 开始转换 (WebSocket建立)
        ↓
5. OCR识别 (Tesseract/Vision API)
        ↓
6. 检测内容类型 (公式/文本/混合)
        ↓
7. LLM转换为LaTeX
        ↓
8. 生成.tex文件
        ↓
9. 返回结果给前端
```

### 详细步骤

#### 第1步：图片上传
**文件**: `app_enhanced.py` → `/api/convert-image` 路由

```python
POST /api/convert-image
Content-Type: multipart/form-data

参数:
- file: 图片文件
- model: LLM模型 (如 "deepseek-chat")
- translate: 是否翻译
- ocr_provider: OCR引擎 ('mixed' | 'tesseract' | 'vision')
- add_document_wrapper: 是否添加文档包装
- task_id: 任务ID
```

#### 第2步：OCR识别
**文件**: `ocr_client.py` → `recognize()` 方法

**混合识别策略**:
```python
# 1. 检测内容类型
content_type = detect_content_type(image)
# 结果: 'formula' | 'text' | 'mixed'

# 2. 根据内容类型选择OCR引擎
if content_type == 'formula':
    # 数学公式优先用 Vision API
    provider = 'vision' if has_vision_api else 'tesseract'
else:
    # 纯文字先试 Tesseract
    provider = 'tesseract'

# 3. 执行OCR识别
if provider == 'tesseract':
    text, quality = tesseract_ocr(image)
    
    # 如果质量低，降级到 Vision API
    if quality < 0.3 and has_vision_api:
        text, quality = await vision_api_ocr(image)
        provider = 'vision'
else:
    text, quality = await vision_api_ocr(image)
```

**Tesseract OCR流程**:
```python
# 1. 图片预处理
processed_image = preprocess_image(image, enhance=True)
# 操作: 缩放、灰度化、增强对比度、二值化

# 2. OCR识别
text = pytesseract.image_to_string(
    processed_image, 
    lang='eng+chi_sim'  # 英文+中文简体
)

# 3. 获取置信度
data = pytesseract.image_to_data(processed_image, output_type=DICT)
confidences = [int(conf) for conf in data['conf'] if conf != '-1']
avg_confidence = sum(confidences) / len(confidences)
quality_score = avg_confidence / 100.0
```

**Vision API OCR流程**:
```python
# 1. 图片转Base64
image_base64 = image_to_base64(image)

# 2. 构建请求
payload = {
    "model": "gpt-4o" or "gemini-2.0-flash-exp",
    "messages": [{
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": "请识别这张图片中的所有内容..."
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": image_base64,
                    "detail": "high"
                }
            }
        ]
    }],
    "temperature": 0.1,
    "max_tokens": 4000
}

# 3. 发送请求
response = await client.post(f"{base_url}/chat/completions", ...)
text = response['choices'][0]['message']['content']

# 4. 估算质量分数
if len(text) < 10:
    quality_score = 0.5
elif len(text) < 50:
    quality_score = 0.7
elif len(text) < 200:
    quality_score = 0.85
else:
    quality_score = 0.95
```

#### 第3步：内容类型检测
**文件**: `ocr_client.py` → `detect_content_type()` 方法

```python
# 1. 快速OCR检测
text = pytesseract.image_to_string(image, lang='eng+chi_sim')

# 2. 检测数学符号和公式特征
math_patterns = [
    r'[\+\-\*/=<>∫∑∏√∂∇]',  # 数学运算符
    r'\\[a-zA-Z]+',          # LaTeX命令
    r'\^|\{|\}|_',           # 上下标和大括号
    r'[α-ωΑ-Ω]',            # 希腊字母
    r'\d+[a-zA-Z]+\d*'       # 数学变量
]

math_count = sum(len(re.findall(pattern, text)) for pattern in math_patterns)
math_ratio = math_count / max(len(text), 1)

# 3. 判断内容类型
if math_ratio > 0.3:
    return 'formula'      # 公式为主
elif math_ratio > 0.05:
    return 'mixed'        # 混合内容
else:
    return 'text'         # 纯文字
```

#### 第4步：LLM转换为LaTeX
**文件**: `image2latex_enhanced.py` → `convert_to_latex()` 方法

**根据内容类型调整提示词**:
```python
if content_type == 'formula':
    system_prompt = """你是一个数学公式LaTeX专家。
    任务：将数学公式转换为标准的LaTeX格式。
    要求：
    1. 使用标准的LaTeX数学环境
    2. 行内公式用 $...$，独立公式用 $$...$$
    3. 不要添加任何解释"""

elif content_type == 'text':
    system_prompt = """你是一个文档LaTeX转换专家。
    任务：将文本内容转换为标准的LaTeX格式。
    要求：
    1. 使用适当的LaTeX环境
    2. 保留段落和换行"""

else:  # mixed
    system_prompt = """你是一个LaTeX转换专家。
    任务：将内容（包含文字和数学公式）转换为标准的LaTeX格式。
    要求：
    1. 文字部分使用普通文本
    2. 数学公式使用LaTeX数学环境
    3. 保持原有的结构和排版"""

# 调用LLM
response = await self.llm_client.chat(
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"请转换以下内容:\n\n{text}"}
    ],
    temperature=0.1,
    max_tokens=4000
)

latex_content = response['choices'][0]['message']['content']
```

#### 第5步：生成LaTeX文件
**文件**: `image2latex_enhanced.py` → `convert_image()` 方法

```python
# 1. 添加文档包装
if add_document_wrapper:
    latex_content = self._wrap_latex_document(latex_content)

# _wrap_latex_document 方法:
def _wrap_latex_document(self, content: str) -> str:
    return f"""\\documentclass{{article}}
\\usepackage{{amsmath}}
\\usepackage{{amssymb}}
\\usepackage{{ctex}}  % 中文支持
\\usepackage{{geometry}}
\\geometry{{a4paper, margin=1in}}

\\begin{{document}}

{content}

\\end{{document}}
"""

# 2. 保存文件
output_path.write_text(latex_content, encoding='utf-8')
```

#### 第6步：返回结果
**文件**: `app_enhanced.py` → `/api/convert-image` 路由

```python
# 1. 保存历史记录
history_manager.add_entry({
    'timestamp': timestamp,
    'filename': filename,
    'model': model,
    'ocr_provider': result['ocr_result']['provider'],
    'ocr_quality': result['ocr_result']['quality'],
    'content_type': result['ocr_result']['content_type'],
    'tokens': result['usage_stats']['total_tokens'],
    'elapsed_time': result['elapsed_time']
})

# 2. 通过WebSocket发送完成状态
socketio.emit('progress', {
    'task_id': task_id,
    'status': 'completed',
    'result': {
        'content': latex_content,
        'ocr_result': {
            'provider': 'vision' or 'tesseract',
            'quality': 0.85,
            'content_type': 'mixed'
        },
        'stats': {...}
    }
}, room=task_id)
```

---

## 🔧 核心技术

### 1. WebSocket实时通信
**技术**: Flask-SocketIO

**用途**: 实时进度更新、终端日志显示

```python
# 后端发送进度
socketio.emit('progress', {
    'task_id': 'task_123',
    'status': 'extracting',
    'current': 3,
    'total': 10,
    'percent': 30,
    'message': '正在提取第 3/10 页...',
    'log_type': 'info',
    'log_message': '📄 第 3 页提取完成 (质量: 85%)'
}, room='task_123')

# 前端监听进度
socket.on('progress', (data) => {
    updateProgressBar(data.percent);
    addTerminalLog(data.log_type, data.log_message);
});
```

### 2. 多方法PDF提取
**技术**: pdfplumber + PyPDF2 + 质量检测

**优势**:
- pdfplumber: 处理复杂PDF，提取质量高
- PyPDF2: 兼容性好，速度快
- 质量检测: 自动选择最佳结果

### 3. 混合OCR策略
**技术**: Tesseract (本地) + Vision API (云端)

**优势**:
- Tesseract: 免费、快速、支持中英文
- Vision API: 识别率高、支持数学公式
- 自动降级: Tesseract质量低时自动切换到Vision API

### 4. 统一LLM接口
**技术**: `LLMClient` 封装

**支持的模型**:
- DeepSeek (Chat, Reasoner, Math)
- OpenAI (GPT-4o, GPT-4o Mini, GPT-5.2)
- 智谱 (GLM-4.6, GLM-4.7)
- Google Gemini (3 Pro)
- 豆包 (Doubao)

**统一调用方式**:
```python
response = await client.chat(
    messages=[...],
    temperature=0.3,
    max_tokens=4000
)
```

### 5. 页码范围解析
**功能**: 支持 "1-3,5,7-9" 格式

```javascript
function parsePageInput(input) {
    const ranges = input.split(',');
    const pages = [];
    
    for (let range of ranges) {
        range = range.trim();
        if (range.includes('-')) {
            const [start, end] = range.split('-');
            for (let i = parseInt(start); i <= parseInt(end); i++) {
                pages.push(i);
            }
        } else {
            pages.push(parseInt(range));
        }
    }
    
    return [...new Set(pages)].sort((a, b) => a - b);
}
```

---

## 🔄 数据流向

### PDF转换数据流
```
用户上传PDF文件
    ↓
[前端] 读取文件 → 获取页数 → 显示给用户
    ↓
[前端] 用户选择页码、模型 → 建立WebSocket连接 → 发送HTTP请求
    ↓
[后端] 接收文件 → 保存到 uploads/ 目录
    ↓
[PDF处理器] 提取指定页面文本 → 发送进度到前端
    ↓
[PDF处理器] 检查文本质量 → 发送质量日志
    ↓
[LLM客户端] 调用API转换为LaTeX → 统计Token
    ↓
[PDF处理器] 组装LaTeX文档 → 保存到 outputs/ 目录
    ↓
[后端] 保存历史记录 → 发送完成状态 → 返回结果
    ↓
[前端] 显示LaTeX代码 → 提供下载/预览
```

### 图片转换数据流
```
用户上传图片/粘贴截图
    ↓
[前端] 读取图片 → 显示预览
    ↓
[前端] 用户选择OCR引擎、模型 → 建立WebSocket连接 → 发送HTTP请求
    ↓
[后端] 接收文件 → 保存到 uploads/ 目录
    ↓
[OCR客户端] 检测内容类型 → 选择OCR引擎
    ↓
[OCR客户端] 图片预处理 → OCR识别 → 发送质量日志
    ↓
[图片处理器] 根据内容类型调整提示词
    ↓
[LLM客户端] 调用API转换为LaTeX → 统计Token
    ↓
[图片处理器] 添加文档包装 → 保存到 outputs/ 目录
    ↓
[后端] 保存历史记录 → 发送完成状态 → 返回结果
    ↓
[前端] 显示LaTeX代码 → 提供下载/预览
```

### WebSocket通信流
```
[前端] 连接WebSocket
    ↓
[后端] handle_connect() → 记录连接
    ↓
[前端] socket.emit('join_task', {task_id: 'task_123'})
    ↓
[后端] handle_join_task() → 加入房间
    ↓
[处理器] 每个步骤调用 progress_callback()
    ↓
[后端] progress_callback() → socketio.emit('progress', data, room='task_123')
    ↓
[前端] socket.on('progress') → 更新UI
    ↓
[处理器] 转换完成
    ↓
[后端] socketio.emit('progress', {status: 'completed', result: {...}})
    ↓
[前端] 显示结果 → 隐藏进度条
```

---

## 📊 进度状态说明

### PDF转换状态
- `preparing`: 准备中
- `uploading`: 上传中
- `extracting`: 提取PDF文本
- `converting`: 转换为LaTeX
- `translating`: 翻译中（如果勾选翻译）
- `completed`: 完成

### 图片转换状态
- `preparing`: 准备中
- `uploading`: 上传中
- `extracting`: OCR识别
- `converting`: 转换为LaTeX
- `completed`: 完成

### 日志类型
- `info`: 普通信息（蓝色）
- `success`: 成功信息（绿色）
- `error`: 错误信息（红色）
- `warning`: 警告信息（黄色）
- `quality`: 质量检测（紫色）
- `progress`: 进度信息（青色）

---

## 🎯 关键优化点

1. **只提取需要的页面**: 用户选择1-3页，就只读取这3页，不浪费资源
2. **质量检测与备用方案**: PDF提取失败或质量低时自动切换方法
3. **混合OCR策略**: 先用免费的Tesseract，质量低再用付费Vision API
4. **实时进度显示**: 每个步骤都通过WebSocket实时反馈
5. **Token统计**: 精确统计每次LLM调用的Token使用和成本
6. **历史记录管理**: 自动保存转换历史，支持查看和重新下载
7. **中文文件名支持**: 正确处理中文文件名的上传、显示和下载
8. **错误重试机制**: LLM调用失败时自动重试3次

---

## 🔑 配置说明

### 必需的API Key
至少需要配置一个LLM的API Key：
- `DEEPSEEK_API_KEY`: DeepSeek模型（推荐，性价比高）
- `OPENAI_API_KEY`: OpenAI模型（GPT-4o, GPT-5.2）
- `ZHIPU_API_KEY`: 智谱GLM模型
- `GEMINI_API_KEY`: Google Gemini模型
- `DOUBAO_API_KEY`: 字节豆包模型

### OCR配置
图片转换需要配置OCR引擎：
- **Tesseract** (免费): 安装 Tesseract-OCR 程序
- **Vision API** (付费): 配置 `OPENAI_API_KEY` 或 `GEMINI_API_KEY`
- **混合模式** (推荐): 同时配置Tesseract和Vision API

---

## 📝 总结

这个项目通过以下技术实现了高质量的PDF/图片到LaTeX转换：

1. **多方法文本提取**: pdfplumber + PyPDF2 + 质量检测
2. **混合OCR识别**: Tesseract + Vision API 智能切换
3. **强大的LLM转换**: 支持10+种主流大模型
4. **实时进度反馈**: WebSocket + 终端日志显示
5. **智能内容检测**: 自动识别公式/文本/混合内容
6. **完善的历史管理**: 记录所有转换历史和统计信息
7. **用户友好界面**: 拖拽上传、实时预览、一键下载

项目的核心优势在于**多层次的质量保证机制**和**灵活的引擎选择**，确保在各种场景下都能获得最佳的转换效果。
