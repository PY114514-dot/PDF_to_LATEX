#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF2LaTeX Web应用 - 增强版
支持实时进度、Token统计、美化展示
"""

import os
import time
import threading
import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List
from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename as werkzeug_secure_filename
from pdf2latex_enhanced import PDF2LaTeXEnhanced
from image2latex_enhanced import Image2LaTeXEnhanced
from clients import LLMClient
from config import settings
from history_manager import history_manager, preference_learner
from task_manager import async_task_manager
from latex_utils import merge_tex_contents
from latex_syntax import check_latex_syntax, fix_latex_syntax, validate_latex, score_latex_quality
from error_handler import DetailedErrorCollector, create_error_context
from knowledge_graph import analyze_paper_structure, get_core_theorems
from mind_map import generate_mind_map_from_latex, MindMapLayout
from bilingual_reader import create_bilingual_view
import re
import unicodedata

app = Flask(__name__, template_folder='../frontend/templates', static_folder='../frontend/static')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'pdf2latex-secret-key')
CORS(app)
socketio = SocketIO(
    app, 
    cors_allowed_origins="*",
    ping_timeout=300,  # 5分钟ping超时
    ping_interval=25,  # 25秒ping间隔
    async_mode='threading'
)

# 配置
# 使用绝对路径，确保无论从哪里启动都能正确找到文件
_BACKEND_DIR = Path(__file__).parent.resolve()
_PROJECT_ROOT = _BACKEND_DIR.parent
UPLOAD_FOLDER = _PROJECT_ROOT / 'uploads'
OUTPUT_FOLDER = _PROJECT_ROOT / 'outputs'
UPLOAD_FOLDER.mkdir(exist_ok=True)
OUTPUT_FOLDER.mkdir(exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

ALLOWED_EXTENSIONS = {'pdf'}
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'bmp', 'tiff', 'gif'}
MAX_BATCH_PDF_FILES = 5

# 存储转换任务的状态
conversion_tasks = {}

PAPER_AGENT_REQUIRED_INSTRUCTIONS = [
    "背景设置为学术专家，对论文给出建议。",
    "确保真实性，回答中的数学公式必须出自原文；若原文没有对应公式，可以明确说明并不提供。",
    "数学公式的推导必须严格遵循论文中的内容，可以解释但不能更改论文中的证明。"
]


def allowed_file(filename):
    """检查文件扩展名是否允许"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def allowed_image_file(filename):
    """检查图片文件扩展名是否允许"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def secure_filename(filename):
    """
    支持中文的安全文件名处理
    保留中文字符，只移除危险字符
    """
    if not filename:
        return 'unnamed'
    
    # 获取文件名和扩展名
    if '.' in filename:
        name, ext = filename.rsplit('.', 1)
    else:
        name, ext = filename, ''
    
    # 移除路径分隔符和危险字符
    dangerous_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|', '\0', '\n', '\r', '\t']
    for char in dangerous_chars:
        name = name.replace(char, '_')
        ext = ext.replace(char, '_')
    
    # 移除前后空格和点
    name = name.strip('. ')
    ext = ext.strip('. ')
    
    # 如果文件名为空，使用默认名称
    if not name:
        name = 'unnamed'
    
    # 限制文件名长度（Windows 最大路径长度限制）
    max_name_length = 200
    if len(name) > max_name_length:
        name = name[:max_name_length]
    
    # 重新组合
    if ext:
        return f"{name}.{ext}"
    return name


def _sanitize_task_label(raw: str) -> str:
    """生成适合 task_id 的短标签（仅字母数字、下划线、连字符）。"""
    if not raw:
        return 'task'
    text = unicodedata.normalize('NFKD', raw)
    text = re.sub(r'[^\w\-]+', '_', text, flags=re.UNICODE)
    text = re.sub(r'_+', '_', text).strip('_.-')
    return text[:48] or 'task'


def build_task_id(prefix: str, source_filename: str, timestamp: int) -> str:
    """按文件名生成可读 task_id。"""
    stem = Path(source_filename or '').stem
    label = _sanitize_task_label(stem)
    return f"{prefix}_{label}_{timestamp}"


def build_output_filename(source_filename: str, translate: bool = False, index: int = None) -> str:
    """按源文件名生成输出 tex 名称，重名自动加序号。"""
    safe_source = secure_filename(source_filename)
    stem = Path(safe_source).stem or 'output'
    stem = stem.strip() or 'output'
    suffix = '_cn' if translate else ''
    index_suffix = f"_{index + 1}" if index is not None else ''

    base_name = f"{stem}{index_suffix}{suffix}"
    candidate = f"{base_name}.tex"
    sequence = 2
    while (OUTPUT_FOLDER / candidate).exists():
        candidate = f"{base_name}_{sequence}.tex"
        sequence += 1
    return candidate


def parse_pages_input(pages_str, max_pages: int = None):
    """
    解析页码输入，支持格式: 1,3,5 或 1-3,5,7-9。
    返回 0-based 且去重排序后的页码列表。

    Args:
        pages_str: 页码字符串
        max_pages: 最大页数限制。当传入实际PDF总页数时，可以精确限制；
                   为 None 时使用硬限制 5000（防止 DoS）
    """
    HARD_LIMIT = 5000  # 防止 DoS 的硬限制

    if not pages_str or not pages_str.strip():
        return None

    effective_limit = max_pages if max_pages is not None else HARD_LIMIT

    pages = set()
    parts = [part.strip() for part in pages_str.split(',') if part.strip()]
    if not parts:
        return None

    for part in parts:
        if '-' in part:
            chunks = [chunk.strip() for chunk in part.split('-')]
            if len(chunks) != 2 or not all(chunk.isdigit() for chunk in chunks):
                raise ValueError(f"无效的页码范围: {part}")

            start, end = int(chunks[0]), int(chunks[1])
            if start <= 0 or end <= 0:
                raise ValueError(f"页码必须大于0: {part}")
            if start > end:
                raise ValueError(f"页码范围起始不能大于结束: {part}")
            if end - start + 1 > effective_limit:
                raise ValueError(f"页码范围过大: 最多 {effective_limit} 页")

            for page in range(start, end + 1):
                pages.add(page - 1)
        else:
            if not part.isdigit():
                raise ValueError(f"无效的页码: {part}")

            page = int(part)
            if page <= 0:
                raise ValueError(f"页码必须大于0: {part}")
            if page > effective_limit:
                raise ValueError(f"页码超出范围: 最多 {effective_limit} 页")
            pages.add(page - 1)

    return sorted(pages)


def _extract_algorithm_blocks_from_latex(latex_content: str, max_blocks: int = 6) -> List[str]:
    """提取 LaTeX 中与算法相关的大段内容，供智能体重点参考。"""
    text = (latex_content or '').strip()
    if not text:
        return []

    blocks: List[str] = []

    # 1) 优先匹配 algorithm / algorithm* 环境
    env_pattern = re.compile(
        r"\\begin\{algorithm\*?\}[\s\S]*?\\end\{algorithm\*?\}",
        re.IGNORECASE
    )
    for m in env_pattern.finditer(text):
        snippet = m.group(0).strip()
        if snippet:
            blocks.append(snippet[:2500])
        if len(blocks) >= max_blocks:
            return blocks

    # 2) 匹配 algorithmic 环境
    algic_pattern = re.compile(
        r"\\begin\{algorithmic\}[\s\S]*?\\end\{algorithmic\}",
        re.IGNORECASE
    )
    for m in algic_pattern.finditer(text):
        snippet = m.group(0).strip()
        if snippet and snippet not in blocks:
            blocks.append(snippet[:2500])
        if len(blocks) >= max_blocks:
            return blocks

    # 3) 回退：按段落抓取包含 Algorithm 关键词的长段
    paragraphs = re.split(r"\n\s*\n", text)
    for para in paragraphs:
        if re.search(r"algorithm|algo\.|procedure|pseudo", para, flags=re.IGNORECASE):
            cleaned = para.strip()
            if len(cleaned) >= 120:
                blocks.append(cleaned[:2500])
        if len(blocks) >= max_blocks:
            break

    return blocks[:max_blocks]


def _latex_to_text(latex_content: str, max_chars: int = 120000) -> tuple[str, bool]:
    """将 LaTeX 内容转换为可读的纯文本，供学术智能体分析。"""
    text = latex_content or ''
    if not text:
        return '', False

    # 移除注释
    text = re.sub(r'%[^\n]*', '', text)

    # 移除文档结构和导言区命令
    text = re.sub(r'\\documentclass(\[[^\]]*\])?\{[^}]+\}', '', text)
    text = re.sub(r'\\usepackage(\[[^\]]*\])?\{[^}]+\}', '', text)
    text = re.sub(r'\\begin\{document\}', '', text)
    text = re.sub(r'\\end\{document\}', '', text)
    text = re.sub(r'\\title\{[^}]*\}', '', text)
    text = re.sub(r'\\author\{[^}]*\}', '', text)
    text = re.sub(r'\\date\{[^}]*\}', '', text)
    text = re.sub(r'\\maketitle', '', text)
    text = re.sub(r'\\centering', '', text)
    text = re.sub(r'\\newpage', '\n\n', text)
    text = re.sub(r'\\pagebreak', '\n\n', text)

    # 将 equation 等数学环境转为文本描述
    text = re.sub(r'\\begin\{equation\*?\}([\s\S]*?)\\end\{equation\*?\}',
                  lambda m: f'[数学公式: {m.group(1).strip()}]', text)
    text = re.sub(r'\\begin\{align\*?\}([\s\S]*?)\\end\{align\*?\}',
                  lambda m: f'[数学公式: {m.group(1).strip()}]', text)
    text = re.sub(r'\\begin\{gather\*?\}([\s\S]*?)\\end\{gather\*?\}',
                  lambda m: f'[数学公式: {m.group(1).strip()}]', text)
    text = re.sub(r'\$\$([\s\S]*?)\$\$',
                  lambda m: f'[数学公式: {m.group(1).strip()}]', text)
    text = re.sub(r'\$([^$]+)\$', r'\1', text)
    text = re.sub(r'\\\[([\s\S]*?)\\\\]', r'\1', text)
    text = re.sub(r'\\\(([\s\S]*?)\\\)', r'\1', text)

    # 移除表格（保留 caption）
    text = re.sub(r'\\begin\{table\*?\}([\s\S]*?)\\end\{table\*?\}',
                  lambda m: re.sub(r'\\caption\{([^}]*)\}', r'表: \1', m.group(0)), text)
    text = re.sub(r'\\begin\{tabular\*?\}\{[^}]*\}([\s\S]*?)\\end\{tabular\*?\}', '', text)

    # 将 itemize/enumerate 转换为列表符号
    text = re.sub(r'\\begin\{itemize\}', '', text)
    text = re.sub(r'\\end\{itemize\}', '\n', text)
    text = re.sub(r'\\begin\{enumerate\}', '', text)
    text = re.sub(r'\\end\{enumerate\}', '\n', text)
    text = re.sub(r'\\item\s+', '• ', text)

    # 转换章节标题
    text = re.sub(r'\\section\{([^}]+)\}', r'\n\n=== \1 ===\n\n', text)
    text = re.sub(r'\\subsection\{([^}]+)\}', r'\n\n== \1 ==\n\n', text)
    text = re.sub(r'\\subsubsection\{([^}]+)\}', r'\n\n= \1 =\n\n', text)

    # 移除图片引用
    text = re.sub(r'\\begin\{figure\*?\}([\s\S]*?)\\end\{figure\*?\}', '', text)
    text = re.sub(r'\\includegraphics(\[[^\]]*\])?\{[^}]*\}', '', text)

    # 移除字体和样式命令
    text = re.sub(r'\\textbf\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\textit\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\emph\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\mathrm\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\mathbf\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\mathsf\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\texttt\{([^}]*)\}', r'\1', text)

    # 移除其他常用命令
    text = re.sub(r'\\label\{[^}]*\}', '', text)
    text = re.sub(r'\\ref\{[^}]*\}', '', text)
    text = re.sub(r'\\cite\{[^}]*\}', '', text)
    text = re.sub(r'\\footnote\{[^}]*\}', '', text)
    text = re.sub(r'\\thanks\{[^}]*\}', '', text)
    text = re.sub(r'\\hspace\*?\{[^}]*\}', ' ', text)
    text = re.sub(r'\\vspace\*?\{[^}]*\}', '\n', text)
    text = re.sub(r'\\newline', '\n', text)
    text = re.sub(r'\\quad', ' ', text)
    text = re.sub(r'\\qquad', '  ', text)
    text = re.sub(r'\\hfill', '', text)
    text = re.sub(r'\\dotfill', '', text)

    # 移除 LaTeX 命令符号（保留大括号内的内容）
    text = re.sub(r'\\[a-zA-Z]+\s*', '', text)
    text = re.sub(r'\\\\\s*', '\n', text)

    # 清理多余空白
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = text.strip()

    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars]

    return text, truncated


def _build_paper_agent_prompts(source_text: str, total_pages: int, analysis_focus: str, algorithm_blocks: List[str] = None) -> Dict[str, str]:
    """构建论文智能阅读提示词（包含硬性约束）。"""
    guardrails = "\n".join([f"{idx}. {item}" for idx, item in enumerate(PAPER_AGENT_REQUIRED_INSTRUCTIONS, start=1)])
    algorithm_blocks = algorithm_blocks or []

    highlighted_blocks = "\n\n".join([
        f"[重点算法块 {idx + 1}]\n{block}"
        for idx, block in enumerate(algorithm_blocks)
    ]) or "未提供额外 LaTeX 算法块。"

    system_prompt = f"""你是数学与机器学习方向的学术专家，擅长论文精读与方法分析。

你必须严格遵守以下硬性指令：
{guardrails}

输出要求：
1. 只基于提供的论文原文内容回答，不得编造。
2. 当涉及公式或推导时，必须给出对应原文片段证据；若找不到证据，明确写“原文未提供”。
3. 输出必须是合法 JSON，不要输出任何 JSON 之外的文本。
4. 若提供了“重点算法块”，你必须优先参考其中的 Algorithm/algorithmic 内容来识别算法流程与伪代码。
5. 对算法、公式、复杂度、推导的描述必须与原文或重点算法块一致，不得改写证明逻辑。
"""

    user_prompt = f"""请基于以下论文文本生成结构化分析（页数：{total_pages}，分析重点：{analysis_focus}）。

请输出 JSON，结构必须为：
{{
  "summary": "string，200~400字的摘要",
  "outline": ["string", "..."],
  "mindmap_markdown": "string，使用 markdown 层级列表表示思维导图",
  "algorithms": [
    {{
      "name": "算法名称",
      "problem": "要解决的问题",
      "core_idea": "核心思想",
      "steps": ["步骤1", "步骤2"],
      "pseudocode": "可选，伪代码；若原文没有可写空字符串",
      "complexity": "可选，复杂度；若原文没有可写原文未提供",
      "formulas": [
        {{
          "latex": "必须来自原文的公式（LaTeX）",
          "meaning": "公式含义说明",
          "evidence": "原文中支持该公式的片段"
        }}
      ],
      "derivation": "严格按原文推导过程的解释；若原文未给出完整推导，必须明确说明",
      "paper_advice": "以学术专家身份给出的改进建议"
    }}
  ],
  "limitations": ["string", "..."],
  "evidence_note": "说明哪些结论有直接证据，哪些地方原文未提供"
}}

注意：
- 若论文里不存在某个算法或公式，对应字段可为空数组或“原文未提供”。
- 禁止臆造任何公式、定理、证明和实验结果。
- 若“重点算法块”中出现 Algorithm/algorithmic 内容，优先把这些内容映射到 algorithms 字段。

原 LaTeX 中重点算法块（已标记）：
{highlighted_blocks}

论文原文如下：
{source_text}
"""

    return {
        'system_prompt': system_prompt,
        'user_prompt': user_prompt
    }


def _parse_paper_agent_json(raw_content: str) -> Dict[str, Any]:
    """从模型输出中提取 JSON，失败时返回兜底结构。"""
    content = (raw_content or '').strip()
    if not content:
        return {
            'summary': '',
            'outline': [],
            'mindmap_markdown': '',
            'algorithms': [],
            'limitations': [],
            'evidence_note': '',
            'raw_response': ''
        }

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        start = content.find('{')
        end = content.rfind('}')
        if start >= 0 and end > start:
            try:
                parsed = json.loads(content[start:end + 1])
            except json.JSONDecodeError:
                parsed = None
        else:
            parsed = None

    if not isinstance(parsed, dict):
        return {
            'summary': '',
            'outline': [],
            'mindmap_markdown': '',
            'algorithms': [],
            'limitations': [],
            'evidence_note': '',
            'raw_response': content
        }

    return {
        'summary': str(parsed.get('summary', '') or ''),
        'outline': parsed.get('outline', []) if isinstance(parsed.get('outline', []), list) else [],
        'mindmap_markdown': str(parsed.get('mindmap_markdown', '') or ''),
        'algorithms': parsed.get('algorithms', []) if isinstance(parsed.get('algorithms', []), list) else [],
        'limitations': parsed.get('limitations', []) if isinstance(parsed.get('limitations', []), list) else [],
        'evidence_note': str(parsed.get('evidence_note', '') or ''),
        'raw_response': content
    }


def progress_callback(task_id, status, current, total, message, log_type='info', log_message=None, tokens=None):
    """进度回调函数"""
    progress_data = {
        'task_id': task_id,
        'status': status,
        'current': current,
        'total': total,
        'percent': int((current / total * 100)) if total > 0 else 0,
        'message': message,
        'log_type': log_type,
        'log_message': log_message or message
    }
    
    # 如果提供了token信息，添加到进度数据中
    if tokens:
        progress_data['tokens'] = tokens
    
    print(f"[进度回调] task_id={task_id}, status={status}, {current}/{total}, log_msg={log_message}, tokens={tokens}")
    socketio.emit('progress', progress_data, room=task_id)
    
    # 更新任务状态
    if task_id in conversion_tasks:
        conversion_tasks[task_id].update(progress_data)

    # 更新可恢复任务状态
    async_task_manager.update_progress(task_id, status, current, total, message, tokens=tokens)


def _save_async_pdf_history(filename, model, translate, pages_str, output_path, result):
    """保存异步 PDF 任务的历史记录。"""
    history_manager.add_record({
        'filename': filename,
        'model': model,
        'translated': translate,
        'pages': pages_str if pages_str else 'all',
        'output_file': str(output_path),
        'stats': {
            'total_pages': result.get('total_pages', 0),
            'processed_pages': result.get('processed_pages', 0),
            'total_tokens': result.get('total_tokens', 0),
            'processing_time': result.get('processing_time', 0)
        }
    })


def _run_async_pdf_task(task_id: str):
    """后台执行 PDF 异步任务。"""
    task = async_task_manager.get_task(task_id)
    if not task:
        return

    payload = task.get('payload', {})
    pdf_path = payload.get('pdf_path')
    output_path = payload.get('output_path')
    filename = payload.get('filename')
    model = payload.get('model', settings.DEFAULT_MODEL)
    translate = payload.get('translate', False)
    pages_str = payload.get('pages_str', '')
    pages = payload.get('pages')
    add_wrapper = payload.get('add_wrapper', True)
    template_name = payload.get('template_name', 'article')
    quality_mode = payload.get('quality_mode', 'standard')

    try:
        if not pdf_path or not Path(pdf_path).exists():
            raise FileNotFoundError('源文件不存在，无法恢复任务')

        async_task_manager.update_task(task_id, status='processing', error=None)

        converter = PDF2LaTeXEnhanced(model=model)

        def callback(status, current, total, message, log_type='info', log_message=None, tokens=None):
            progress_callback(task_id, status, current, total, message, log_type, log_message, tokens)

        converter.set_progress_callback(callback)
        result = converter.convert_pdf(
            pdf_path=str(pdf_path),
            output_path=str(output_path),
            pages=pages,
            add_document_wrapper=add_wrapper,
            translate=translate,
            task_id=task_id,
            template_name=template_name,
            quality_mode=quality_mode
        )

        latex_content = Path(result['output_path']).read_text(encoding='utf-8')
        result_data = {
            'success': True,
            'task_id': task_id,
            'filename': Path(output_path).name,
            'content': latex_content,
            'source_text': result.get('source_text', ''),
            'download_url': f"/api/download/{Path(output_path).name}",
            'stats': {
                'total_pages': result.get('total_pages', 0),
                'processed_pages': result.get('processed_pages', 0),
                'total_tokens': result.get('total_tokens', 0),
                'prompt_tokens': result.get('prompt_tokens', 0),
                'completion_tokens': result.get('completion_tokens', 0),
                'processing_time': result.get('processing_time', 0)
            }
        }

        _save_async_pdf_history(filename, model, translate, pages_str, output_path, result)
        async_task_manager.set_completed(task_id, result_data)

        total_pages = result.get('total_pages', 0)
        socketio.emit('progress', {
            'task_id': task_id,
            'status': 'completed',
            'current': total_pages,
            'total': total_pages,
            'percent': 100,
            'message': f'✅ 异步任务完成！共处理 {total_pages} 页',
            'log_type': 'success',
            'log_message': f'✅ 异步任务完成！共处理 {total_pages} 页',
            'result': result_data
        }, room=task_id)
    except Exception as e:
        async_task_manager.set_failed(task_id, str(e))
        socketio.emit('progress', {
            'task_id': task_id,
            'status': 'error',
            'current': 0,
            'total': 1,
            'percent': 0,
            'message': f'❌ 异步任务失败: {str(e)}',
            'log_type': 'error',
            'log_message': f'❌ 异步任务失败: {str(e)}'
        }, room=task_id)


def _start_async_pdf_task(task_id: str):
    threading.Thread(target=_run_async_pdf_task, args=(task_id,), daemon=True).start()


@app.route('/')
def index():
    """主页"""
    return render_template('index_enhanced.html')


@app.route('/render')
def render_page():
    """LaTeX渲染页面"""
    return render_template('latex_render.html')


@app.route('/paper-agent-view')
def paper_agent_view_page():
    """学术智能体分析结果页面"""
    return render_template('paper_agent_view.html')


@socketio.on('connect')
def handle_connect():
    """WebSocket连接"""
    print('客户端已连接')


@socketio.on('disconnect')
def handle_disconnect():
    """WebSocket断开"""
    print('客户端已断开')


@socketio.on('heartbeat')
def handle_heartbeat(data):
    """处理客户端心跳"""
    # 返回心跳响应，保持连接活跃
    emit('heartbeat_response', {'timestamp': data.get('timestamp')})


@socketio.on('join_task')
def handle_join_task(data):
    """加入任务房间"""
    task_id = data.get('task_id')
    if task_id:
        from flask_socketio import join_room
        join_room(task_id)
        print(f'客户端加入任务: {task_id}')


@app.route('/api/convert', methods=['POST'])
def convert_pdf():
    """转换PDF为LaTeX"""
    filepath = None
    
    try:
        # 检查文件
        if 'file' not in request.files:
            return jsonify({'error': '没有上传文件'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': '文件名为空'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': '只支持PDF文件'}), 400
        
        # 获取参数
        translate = request.form.get('translate', 'false').lower() == 'true'
        pages_str = request.form.get('pages', '')
        add_wrapper = request.form.get('add_wrapper', 'true').lower() == 'true'
        model = request.form.get('model', settings.DEFAULT_MODEL)  # 获取模型参数
        task_id = request.form.get('task_id', '')  # 获取前端传来的task_id
        template_name = request.form.get('template', 'article')
        quality_mode = request.form.get('quality_mode', 'standard')
        translation_prompt = request.form.get('translation_prompt', '').strip()
        
        # 解析页码
        pages = None
        if pages_str:
            try:
                pages = parse_pages_input(pages_str)
            except ValueError as e:
                return jsonify({'error': str(e)}), 400
        
        # 保存文件
        filename = secure_filename(file.filename)
        timestamp = int(time.time())
        if not task_id:  # 如果前端没有传task_id，则生成一个
            task_id = build_task_id('task', filename, timestamp)
        unique_filename = f"{timestamp}_{filename}"
        filepath = app.config['UPLOAD_FOLDER'] / unique_filename
        file.save(filepath)
        
        # 初始化任务状态
        conversion_tasks[task_id] = {
            'status': 'processing',
            'current': 0,
            'total': 100,
            'percent': 0
        }
        
        # 创建转换器（支持模型选择）
        try:
            converter = PDF2LaTeXEnhanced(model=model, translation_prompt=translation_prompt)
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        
        # 设置进度回调
        def callback(status, current, total, message, log_type='info', log_message=None, tokens=None):
            progress_callback(task_id, status, current, total, message, log_type, log_message, tokens)
        
        converter.set_progress_callback(callback)
        
        # 生成输出文件名
        suffix = "_cn" if translate else ""
        output_filename = build_output_filename(filename, translate=translate)
        output_path = app.config['OUTPUT_FOLDER'] / output_filename
        
        # 执行转换
        result = converter.convert_pdf(
            pdf_path=str(filepath),
            output_path=str(output_path),
            pages=pages,
            add_document_wrapper=add_wrapper,
            translate=translate,
            task_id=task_id,
            template_name=template_name,
            quality_mode=quality_mode
        )
        
        # 读取生成的LaTeX内容
        with open(result['output_path'], 'r', encoding='utf-8') as f:
            latex_content = f.read()
        
        # 保存到历史记录
        history_manager.add_record({
            'filename': filename,
            'model': model,
            'translated': translate,
            'pages': pages_str if pages_str else 'all',
            'output_file': str(output_path),
            'stats': {
                'total_pages': result.get('total_pages', 0),
                'processed_pages': result.get('processed_pages', 0),
                'total_tokens': result.get('total_tokens', 0),
                'processing_time': result.get('processing_time', 0)
            }
        })
        
        # 清理孤立文件
        history_manager.clean_orphan_files(
            app.config['UPLOAD_FOLDER'],
            app.config['OUTPUT_FOLDER']
        )
        
        # 构建结果数据
        result_data = {
            'success': True,
            'task_id': task_id,
            'filename': output_filename,
            'content': latex_content,
            'source_text': result.get('source_text', ''),
            'download_url': f'/api/download/{output_filename}',
            'stats': {
                'total_pages': result.get('total_pages', 0),
                'processed_pages': result.get('processed_pages', 0),
                'total_tokens': result.get('total_tokens', 0),
                'prompt_tokens': result.get('prompt_tokens', 0),
                'completion_tokens': result.get('completion_tokens', 0),
                'processing_time': result.get('processing_time', 0)
            }
        }
        
        # 发送完成状态到前端（通过WebSocket，包含结果数据）
        total_pages = result.get('total_pages', 0)
        socketio.emit('progress', {
            'task_id': task_id,
            'status': 'completed',
            'current': total_pages,
            'total': total_pages,
            'percent': 100,
            'message': f'✅ 转换完成！共处理 {total_pages} 页',
            'log_type': 'success',
            'log_message': f'✅ 转换完成！共处理 {total_pages} 页',
            'result': result_data  # 包含完整的结果数据
        }, room=task_id)
        
        # 返回结果
        return jsonify(result_data)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
    finally:
        # 清理上传的文件
        try:
            if filepath and filepath.exists():
                os.remove(filepath)
        except:
            pass


@app.route('/api/download/<path:filename>')
def download_file(filename):
    """下载生成的LaTeX文件"""
    try:
        filepath = app.config['OUTPUT_FOLDER'] / filename
        if not filepath.exists():
            return jsonify({'error': '文件不存在'}), 404

        # 使用 RFC 2231 编码中文文件名
        from urllib.parse import quote
        encoded_filename = quote(filename.encode('utf-8'))

        response = send_file(
            filepath,
            as_attachment=True,
            download_name=filename,
            mimetype='application/x-tex'
        )

        # 设置支持中文的 Content-Disposition header
        response.headers['Content-Disposition'] = f"attachment; filename*=UTF-8''{encoded_filename}"

        return response
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/batch-convert', methods=['POST'])
def batch_convert_pdf():
    """批量转换PDF为LaTeX"""
    uploaded_files = []
    
    try:
        # 获取所有上传的文件
        if 'files' not in request.files:
            return jsonify({'error': '没有上传文件'}), 400
        
        files = request.files.getlist('files')
        
        if not files or len(files) == 0:
            return jsonify({'error': '文件列表为空'}), 400
        
        # 限制批量数量
        if len(files) > MAX_BATCH_PDF_FILES:
            return jsonify({'error': f'最多支持同时上传{MAX_BATCH_PDF_FILES}个PDF文件'}), 400

        # 校验重复文件名（视为非“不同PDF”）
        normalized_names = []
        for f in files:
            if f and f.filename:
                normalized_names.append(secure_filename(f.filename).lower())
        if len(normalized_names) != len(set(normalized_names)):
            return jsonify({'error': '检测到重复PDF文件名，请上传不同的PDF文件'}), 400
        
        # 验证所有文件
        for file in files:
            if not file.filename:
                continue
            if not allowed_file(file.filename):
                return jsonify({'error': f'文件 {file.filename} 不是PDF格式'}), 400
        
        # 获取参数
        translate = request.form.get('translate', 'false').lower() == 'true'
        pages_str = request.form.get('pages', '')
        add_wrapper = request.form.get('add_wrapper', 'true').lower() == 'true'
        model = request.form.get('model', settings.DEFAULT_MODEL)  # 获取模型参数
        template_name = request.form.get('template', 'article')
        quality_mode = request.form.get('quality_mode', 'standard')
        translation_prompt = request.form.get('translation_prompt', '').strip()
        
        # 解析页码
        pages = None
        if pages_str:
            try:
                pages = parse_pages_input(pages_str)
            except ValueError as e:
                return jsonify({'error': str(e)}), 400
        
        # 创建批量任务ID（优先使用前端传入，确保WebSocket房间一致）
        timestamp = int(time.time())
        batch_id = request.form.get('task_id', '').strip() or f"batch_{timestamp}"
        
        # 初始化批量任务状态
        conversion_tasks[batch_id] = {
            'status': 'processing',
            'total_files': len(files),
            'completed_files': 0,
            'results': []
        }
        
        results = []
        
        # 处理每个文件
        for idx, file in enumerate(files):
            if not file.filename:
                continue
            
            try:
                filename = secure_filename(file.filename)
                unique_filename = f"{timestamp}_{idx}_{filename}"
                filepath = app.config['UPLOAD_FOLDER'] / unique_filename
                file.save(filepath)
                
                uploaded_files.append(filepath)
                
                # 发送进度：正在处理第几个文件
                task_id = f"{batch_id}_file_{idx}"
                
                def callback(status, current, total, message, log_type='info', log_message=None, tokens=None):
                    progress_callback(batch_id, status, idx + 1, len(files), 
                                    f'[{idx + 1}/{len(files)}] {filename}: {message}',
                                    log_type, log_message)
                
                # 创建转换器（支持模型选择）
                try:
                    converter = PDF2LaTeXEnhanced(model=model, translation_prompt=translation_prompt)
                except ValueError as e:
                    results.append({
                        'filename': file.filename,
                        'success': False,
                        'error': str(e)
                    })
                    continue
                converter.set_progress_callback(callback)
                
                # 生成输出文件名
                suffix = "_cn" if translate else ""
                output_filename = build_output_filename(filename, translate=translate, index=idx)
                output_path = app.config['OUTPUT_FOLDER'] / output_filename
                
                # 执行转换
                result = converter.convert_pdf(
                    pdf_path=str(filepath),
                    output_path=str(output_path),
                    pages=pages,
                    add_document_wrapper=add_wrapper,
                    translate=translate,
                    task_id=task_id,
                    template_name=template_name,
                    quality_mode=quality_mode
                )
                
                # 读取内容
                with open(result['output_path'], 'r', encoding='utf-8') as f:
                    latex_content = f.read()
                
                # 添加到结果
                file_result = {
                    'filename': filename,
                    'output_filename': output_filename,
                    'download_url': f'/api/download/{output_filename}',
                    'content': latex_content,
                    'source_text': result.get('source_text', ''),
                    'stats': {
                        'total_pages': result.get('total_pages', 0),
                        'processed_pages': result.get('processed_pages', 0),
                        'total_tokens': result.get('total_tokens', 0),
                        'prompt_tokens': result.get('prompt_tokens', 0),
                        'completion_tokens': result.get('completion_tokens', 0),
                        'processing_time': result.get('processing_time', 0)
                    },
                    'success': True
                }
                
                results.append(file_result)
                
                # 保存到历史记录
                history_manager.add_record({
                    'filename': filename,
                    'model': model,
                    'translated': translate,
                    'pages': pages_str if pages_str else 'all',
                    'output_file': str(output_path),
                    'batch': True,
                    'batch_id': batch_id,
                    'stats': {
                        'total_pages': result.get('total_pages', 0),
                        'processed_pages': result.get('processed_pages', 0),
                        'total_tokens': result.get('total_tokens', 0),
                        'processing_time': result.get('processing_time', 0)
                    }
                })
                
                # 更新批量任务进度
                conversion_tasks[batch_id]['completed_files'] = idx + 1
                conversion_tasks[batch_id]['results'].append(file_result)
                
            except Exception as e:
                # 单个文件失败不影响其他文件
                results.append({
                    'filename': file.filename,
                    'success': False,
                    'error': str(e)
                })
        
        # 计算总体统计
        total_stats = {
            'total_files': len(files),
            'successful_files': sum(1 for r in results if r.get('success', False)),
            'failed_files': sum(1 for r in results if not r.get('success', False)),
            'total_pages': sum(r.get('stats', {}).get('total_pages', 0) for r in results if r.get('success', False)),
            'total_tokens': sum(r.get('stats', {}).get('total_tokens', 0) for r in results if r.get('success', False)),
            'total_time': sum(r.get('stats', {}).get('processing_time', 0) for r in results if r.get('success', False))
        }
        
        # 清理孤立文件
        history_manager.clean_orphan_files(
            app.config['UPLOAD_FOLDER'],
            app.config['OUTPUT_FOLDER']
        )
        
        # 构建批量转换结果
        batch_result = {
            'success': True,
            'batch_id': batch_id,
            'results': results,
            'total_stats': total_stats
        }
        
        # 发送完成进度（包含结果数据）
        socketio.emit('progress', {
            'task_id': batch_id,
            'status': 'completed',
            'current': len(files),
            'total': len(files),
            'percent': 100,
            'message': f'✅ 批量转换完成！成功 {total_stats["successful_files"]}/{total_stats["total_files"]} 个文件',
            'log_type': 'success',
            'log_message': f'✅ 批量转换完成！成功 {total_stats["successful_files"]}/{total_stats["total_files"]} 个文件',
            'result': batch_result
        }, room=batch_id)
        
        return jsonify(batch_result)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
    finally:
        # 清理上传的文件
        for filepath in uploaded_files:
            try:
                if filepath.exists():
                    os.remove(filepath)
            except:
                pass


@app.route('/api/download-batch/<batch_id>')
def download_batch(batch_id):
    """打包下载批量转换的结果"""
    import zipfile
    from io import BytesIO
    
    try:
        if batch_id not in conversion_tasks:
            return jsonify({'error': '批量任务不存在'}), 404
        
        task = conversion_tasks[batch_id]
        results = task.get('results', [])
        
        if not results:
            return jsonify({'error': '没有可下载的文件'}), 404
        
        # 创建ZIP文件
        zip_buffer = BytesIO()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for result in results:
                if result.get('success', False):
                    output_filename = result['output_filename']
                    filepath = app.config['OUTPUT_FOLDER'] / output_filename

                    if filepath.exists():
                        # 添加文件到ZIP
                        zip_file.write(filepath, output_filename)
        
        zip_buffer.seek(0)
        
        # 中文文件名编码
        from urllib.parse import quote
        zip_filename = f'{batch_id}_results.zip'
        encoded_filename = quote(zip_filename.encode('utf-8'))
        
        response = send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=zip_filename
        )
        
        # 设置支持中文的 Content-Disposition header
        response.headers['Content-Disposition'] = f"attachment; filename*=UTF-8''{encoded_filename}"
        
        return response
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/status', methods=['GET'])
def status():
    """检查API状态"""
    return jsonify({
        'status': 'running',
        'message': 'PDF2LaTeX Enhanced API is running'
    })


@app.route('/api/public-config', methods=['GET'])
def get_public_config():
    """返回前端可安全读取的公开配置。"""
    return jsonify({
        'success': True,
        'config': {
            'default_model': settings.DEFAULT_MODEL
        }
    })


@app.route('/api/models', methods=['GET'])
def get_models():
    """获取可用的模型列表"""
    try:
        models = settings.get_available_models()
        return jsonify({
            'success': True,
            'models': models
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/history', methods=['GET'])
def get_history():
    """获取历史记录"""
    try:
        limit = request.args.get('limit', 10, type=int)
        offset = request.args.get('offset', 0, type=int)
        history = history_manager.get_history(limit=limit, offset=offset)
        return jsonify({
            'success': True,
            'history': history,
            'total': len(history_manager.history),
            'limit': limit,
            'offset': offset
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/history/<int:index>', methods=['GET'])
def get_history_record(index):
    """获取指定索引的历史记录"""
    try:
        record = history_manager.get_record(index)
        if record:
            return jsonify({
                'success': True,
                'record': record
            })
        else:
            return jsonify({'error': '记录不存在'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/history/<int:index>', methods=['DELETE'])
def delete_history_record(index):
    """删除指定索引的历史记录"""
    try:
        deleted = history_manager.delete_record(index)
        if deleted:
            return jsonify({'success': True})
        return jsonify({'error': '记录不存在'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/history/clear', methods=['POST'])
def clear_history():
    """清空历史记录"""
    try:
        history_manager.clear_history()
        return jsonify({
            'success': True,
            'message': '历史记录已清空'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/get-pdf-pages', methods=['POST'])
def get_pdf_pages():
    """获取PDF文件的页数"""
    filepath = None
    
    try:
        # 检查文件
        if 'file' not in request.files:
            return jsonify({'error': '没有上传文件'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': '文件名为空'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': '只支持PDF文件'}), 400
        
        # 保存临时文件
        filename = secure_filename(file.filename)
        timestamp = int(time.time())
        unique_filename = f"temp_{timestamp}_{filename}"
        filepath = app.config['UPLOAD_FOLDER'] / unique_filename
        file.save(filepath)
        
        # 读取PDF页数
        import PyPDF2
        with open(filepath, 'rb') as pdf_file:
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            total_pages = len(pdf_reader.pages)
        
        return jsonify({
            'success': True,
            'total_pages': total_pages,
            'filename': file.filename
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
    finally:
        # 清理临时文件
        try:
            if filepath and filepath.exists():
                os.remove(filepath)
        except:
            pass


@app.route('/api/convert-image', methods=['POST'])
def convert_image():
    """单张图片转LaTeX"""
    try:
        # 获取参数
        task_id = request.form.get('task_id')
        if not task_id:
            timestamp = int(time.time())
            task_id = f"task_{timestamp}"
        
        # 注意：客户端已通过 socket.emit('join_task') 加入房间
        # 不需要在这里再次加入（request.sid 在HTTP请求中不可用）
        
        # 检查文件
        if 'file' not in request.files:
            return jsonify({'error': '没有上传文件'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': '文件名为空'}), 400
        
        if not allowed_image_file(file.filename):
            return jsonify({'error': '不支持的图片格式'}), 400
        
        # 保存上传的图片
        filename = secure_filename(file.filename)
        timestamp = int(time.time())
        unique_filename = f"{timestamp}_{filename}"
        filepath = UPLOAD_FOLDER / unique_filename
        file.save(filepath)
        
        # 获取其他参数
        model = request.form.get('model', settings.DEFAULT_MODEL)
        translate_raw = request.form.get('translate', 'false')
        translate = translate_raw.lower() == 'true'
        ocr_provider = request.form.get('ocr_provider', 'mixed')  # 'mixed' | 'tesseract' | 'vision'
        add_wrapper = request.form.get('add_document_wrapper', 'true').lower() == 'true'
        template_name = request.form.get('template', 'article')
        quality_mode = request.form.get('quality_mode', 'standard')
        translation_prompt = request.form.get('translation_prompt', '').strip()
        
        # 调试日志
        print(f"[图片转换] 原始参数: translate_raw='{translate_raw}' (type={type(translate_raw)})")
        print(f"[图片转换] 解析后参数: model={model}, translate={translate}, ocr_provider={ocr_provider}, add_wrapper={add_wrapper}")
        
        # 创建进度回调
        def callback(status, current, total, message, log_type='info', log_message=None, tokens=None):
            progress_callback(task_id, status, current, total, message, log_type, log_message, tokens)
        
        # 创建转换器
        converter = Image2LaTeXEnhanced(
            model_name=model,
            translate=translate,
            translation_prompt=translation_prompt,
            progress_callback=callback
        )
        
        # 执行转换（同步包装异步）
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        output_filename = build_output_filename(filename, translate=False)
        output_path = OUTPUT_FOLDER / output_filename
        
        result = loop.run_until_complete(
            converter.convert_image(
                str(filepath),
                output_path=str(output_path),
                ocr_provider=ocr_provider if ocr_provider != 'mixed' else None,
                add_document_wrapper=add_wrapper,
                template_name=template_name,
                quality_mode=quality_mode
            )
        )
        
        loop.close()
        
        # 清理上传文件
        try:
            os.remove(filepath)
        except:
            pass
        
        if not result['success']:
            return jsonify(result), 400
        
        # 读取生成的LaTeX内容
        latex_content = Path(result['output_file']).read_text(encoding='utf-8')
        
        # 保存到历史记录
        history_entry = {
            'timestamp': timestamp,
            'filename': filename,
            'model': model,
            'ocr_provider': result['ocr_result']['provider'],
            'ocr_quality': result['ocr_result']['quality'],
            'content_type': result['ocr_result']['content_type'],
            'translate': translate,
            'output_file': output_filename,
            'tokens': result['usage_stats'].get('total_tokens', 0),
            'elapsed_time': result['elapsed_time']
        }
        history_manager.add_entry(history_entry)
        
        usage = result['usage_stats']
        
        # 构建统一的stats结构
        stats = {
            'processed_pages': 1,  # 图片按1页计
            'total_pages': 1,
            'prompt_tokens': usage.get('prompt_tokens', 0),
            'completion_tokens': usage.get('completion_tokens', 0),
            'total_tokens': usage.get('total_tokens', 0),
            'processing_time': round(result['elapsed_time'], 2)
        }
        
        # 构建结果数据
        image_result = {
            'success': True,
            'task_id': task_id,
            'filename': output_filename,
            'content': latex_content,
            'download_url': f'/api/download/{output_filename}',
            'latex_content': latex_content,
            'output_file': output_filename,
            'ocr_result': result['ocr_result'],
            'source_text': result.get('source_text', ''),
            'stats': stats,  # 使用统一的stats结构
            'usage_stats': usage,  # 保留原始usage_stats
            'elapsed_time': result['elapsed_time']
        }
        
        # 发送完成状态到前端（通过WebSocket）
        socketio.emit('progress', {
            'task_id': task_id,
            'status': 'completed',
            'current': 1,
            'total': 1,
            'percent': 100,
            'message': f'✅ 图片转换完成！',
            'log_type': 'success',
            'log_message': f'✅ 图片转换完成！OCR引擎: {result["ocr_result"]["provider"]}, 质量: {result["ocr_result"]["quality"]:.1%}',
            'result': image_result
        }, room=task_id)
        
        return jsonify(image_result)
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/convert-images', methods=['POST'])
def convert_images():
    """批量图片转LaTeX"""
    try:
        # 获取参数
        task_id = request.form.get('task_id')
        if not task_id:
            timestamp = int(time.time())
            task_id = f"task_{timestamp}"
        
        # 注意：客户端已通过 socket.emit('join_task') 加入房间
        # 不需要在这里再次加入（request.sid 在HTTP请求中不可用）
        
        # 检查文件
        if 'files' not in request.files:
            return jsonify({'error': '没有上传文件'}), 400
        
        files = request.files.getlist('files')
        if not files or all(f.filename == '' for f in files):
            return jsonify({'error': '文件列表为空'}), 400
        
        # 保存所有上传的图片
        uploaded_paths = []
        timestamp = int(time.time())
        
        for file in files:
            if file and allowed_image_file(file.filename):
                filename = secure_filename(file.filename)
                unique_filename = f"{timestamp}_{filename}"
                filepath = UPLOAD_FOLDER / unique_filename
                file.save(filepath)
                uploaded_paths.append(str(filepath))
        
        if not uploaded_paths:
            return jsonify({'error': '没有有效的图片文件'}), 400
        
        # 获取其他参数
        model = request.form.get('model', settings.DEFAULT_MODEL)
        translate = request.form.get('translate', 'false').lower() == 'true'
        ocr_provider = request.form.get('ocr_provider', 'mixed')
        add_wrapper = request.form.get('add_document_wrapper', 'true').lower() == 'true'
        template_name = request.form.get('template', 'article')
        quality_mode = request.form.get('quality_mode', 'standard')
        translation_prompt = request.form.get('translation_prompt', '').strip()
        
        # 创建进度回调
        def callback(status, current, total, message, log_type='info', log_message=None, tokens=None):
            progress_callback(task_id, status, current, total, message, log_type, log_message, tokens)
        
        # 创建转换器
        converter = Image2LaTeXEnhanced(
            model_name=model,
            translate=translate,
            translation_prompt=translation_prompt,
            progress_callback=callback
        )
        
        # 执行批量转换
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        result = loop.run_until_complete(
            converter.batch_convert_images(
                uploaded_paths,
                output_dir=str(OUTPUT_FOLDER),
                ocr_provider=ocr_provider if ocr_provider != 'mixed' else None,
                add_document_wrapper=add_wrapper,
                template_name=template_name,
                quality_mode=quality_mode
            )
        )
        
        loop.close()
        
        # 清理上传文件
        for filepath in uploaded_paths:
            try:
                os.remove(filepath)
            except:
                pass
        
        # 汇总统计信息（不再计算成本）
        total_tokens = 0
        total_time = 0.0
        
        # 处理每个结果，添加统一的stats结构
        processed_results = []
        for res in result.get('results', []):
            if res.get('success'):
                usage = res.get('usage_stats', {})
                total_tokens += usage.get('total_tokens', 0)
                total_time += res.get('elapsed_time', 0)
                
                # 添加统一的stats结构
                res['stats'] = {
                    'processed_pages': 1,
                    'total_pages': 1,
                    'prompt_tokens': usage.get('prompt_tokens', 0),
                    'completion_tokens': usage.get('completion_tokens', 0),
                    'total_tokens': usage.get('total_tokens', 0),
                    'processing_time': round(res.get('elapsed_time', 0), 2)
                }
                
                # 添加下载URL
                if res.get('output_file'):
                    filename = Path(res['output_file']).name
                    res['download_url'] = f'/api/download/{filename}'
            
            processed_results.append(res)
        
        # 构建批量结果
        batch_result = {
            'success': True,
            'total_images': result.get('total_images', 0),
            'successful_images': result.get('successful_images', 0),
            'failed_images': result.get('failed_images', 0),
            'results': processed_results,
            'total_stats': {
                'total_files': result.get('total_images', 0),
                'successful_files': result.get('successful_images', 0),
                'total_pages': result.get('successful_images', 0),  # 图片按成功数量计
                'total_tokens': total_tokens,
                'total_time': round(total_time, 2)
            }
        }
        
        # 发送完成状态到前端（通过WebSocket）
        socketio.emit('progress', {
            'task_id': task_id,
            'status': 'completed',
            'current': len(uploaded_paths),
            'total': len(uploaded_paths),
            'percent': 100,
            'message': f'✅ 批量转换完成！成功 {result.get("successful_images", 0)}/{result.get("total_images", 0)} 张图片',
            'log_type': 'success',
            'log_message': f'✅ 批量转换完成！成功 {result.get("successful_images", 0)}/{result.get("total_images", 0)} 张图片',
            'result': batch_result
        }, room=task_id)
        
        return jsonify(batch_result)
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/convert-async', methods=['POST'])
def convert_pdf_async():
    """异步转换 PDF，可恢复任务。"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': '没有上传文件'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': '文件名为空'}), 400
        if not allowed_file(file.filename):
            return jsonify({'error': '只支持PDF文件'}), 400

        translate = request.form.get('translate', 'false').lower() == 'true'
        pages_str = request.form.get('pages', '')
        add_wrapper = request.form.get('add_wrapper', 'true').lower() == 'true'
        model = request.form.get('model', settings.DEFAULT_MODEL)
        template_name = request.form.get('template', 'article')
        quality_mode = request.form.get('quality_mode', 'standard')

        pages = None
        if pages_str:
            try:
                pages = parse_pages_input(pages_str)
            except ValueError as e:
                return jsonify({'error': str(e)}), 400

        filename = secure_filename(file.filename)
        timestamp = int(time.time())
        task_id = request.form.get('task_id', '').strip() or build_task_id('async', filename, timestamp)

        upload_name = f"async_{timestamp}_{filename}"
        filepath = app.config['UPLOAD_FOLDER'] / upload_name
        file.save(filepath)

        output_filename = build_output_filename(filename, translate=translate)
        output_path = app.config['OUTPUT_FOLDER'] / output_filename

        payload = {
            'filename': filename,
            'pdf_path': str(filepath),
            'output_path': str(output_path),
            'model': model,
            'translate': translate,
            'pages_str': pages_str,
            'pages': pages,
            'add_wrapper': add_wrapper,
            'template_name': template_name,
            'quality_mode': quality_mode
        }
        async_task_manager.create_task(task_id, payload)
        _start_async_pdf_task(task_id)

        return jsonify({
            'success': True,
            'task_id': task_id,
            'status': 'queued',
            'message': '异步任务已创建，可通过 /api/task/<task_id> 查询进度'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/task/<task_id>', methods=['GET'])
def get_task_status(task_id):
    """查询异步任务状态。"""
    task = async_task_manager.get_task(task_id)
    if not task:
        return jsonify({'error': '任务不存在'}), 404
    return jsonify({'success': True, 'task': task})


@app.route('/api/tasks', methods=['GET'])
def list_tasks():
    """任务中心：查询异步任务列表。"""
    try:
        limit = request.args.get('limit', 50, type=int)
        tasks = async_task_manager.list_tasks(limit=limit)
        return jsonify({'success': True, 'tasks': tasks, 'count': len(tasks)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/task/<task_id>/resume', methods=['POST'])
def resume_task(task_id):
    """恢复失败或中断的任务。"""
    task = async_task_manager.get_task(task_id)
    if not task:
        return jsonify({'error': '任务不存在'}), 404

    status = task.get('status')
    if status in ('processing', 'extracting', 'converting', 'translating'):
        return jsonify({'error': '任务正在执行中'}), 400
    if status == 'completed':
        return jsonify({'error': '任务已完成，无需恢复'}), 400

    payload = task.get('payload', {})
    pdf_path = payload.get('pdf_path')
    if not pdf_path or not Path(pdf_path).exists():
        return jsonify({'error': '源文件不存在，无法恢复任务'}), 400

    async_task_manager.update_task(task_id, status='queued', error=None, result=None)
    _start_async_pdf_task(task_id)
    return jsonify({'success': True, 'task_id': task_id, 'status': 'queued'})


@app.route('/api/merge-outputs', methods=['POST'])
def merge_outputs():
    """多文件合并为单个 LaTeX 文件。"""
    try:
        data = request.get_json(silent=True) or {}
        filenames = data.get('filenames', [])
        if not filenames or not isinstance(filenames, list):
            return jsonify({'error': '请提供要合并的文件名列表'}), 400

        template_name = data.get('template', 'article')
        use_chinese = bool(data.get('use_chinese', True))
        merged_name = data.get('merged_name', '')

        contents = []
        for name in filenames:
            path = app.config['OUTPUT_FOLDER'] / Path(name).name
            if not path.exists():
                continue
            contents.append(path.read_text(encoding='utf-8'))

        if not contents:
            return jsonify({'error': '未找到可合并的有效文件'}), 404

        merged_content = merge_tex_contents(contents, template_name=template_name, use_chinese=use_chinese)
        timestamp = int(time.time())
        safe_name = secure_filename(merged_name).strip() if merged_name else ''
        if not safe_name:
            safe_name = f'merged_{timestamp}.tex'
        if not safe_name.endswith('.tex'):
            safe_name = f'{safe_name}.tex'

        output_path = app.config['OUTPUT_FOLDER'] / safe_name
        output_path.write_text(merged_content, encoding='utf-8')

        return jsonify({
            'success': True,
            'filename': safe_name,
            'download_url': f'/api/download/{safe_name}',
            'content': merged_content
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/paper-agent', methods=['POST'])
def paper_agent():
    """PDF 学术阅读智能体：摘要、大纲、思维导图与算法分析。"""
    filepath = None
    try:
        latex_only_mode = False
        source_filename = 'latex'

        # 支持纯 LaTeX 模式（不需要上传 PDF）
        if 'file' in request.files and request.files['file'].filename:
            file = request.files['file']
            if not allowed_file(file.filename):
                return jsonify({'error': '仅支持PDF文件'}), 400
            source_filename = file.filename
        elif 'latex_content' in request.form:
            latex_content = request.form.get('latex_content', '').strip()
            if not latex_content:
                return jsonify({'error': '没有提供 LaTeX 内容'}), 400
            latex_only_mode = True
        else:
            return jsonify({'error': '请提供 PDF 文件或 LaTeX 内容'}), 400

        pages_str = request.form.get('pages', '').strip()
        model = request.form.get('model', settings.DEFAULT_MODEL)
        analysis_focus = request.form.get('analysis_focus', 'all').strip() or 'all'
        latex_content = request.form.get('latex_content', '') if not latex_only_mode else request.form.get('latex_content', '').strip()
        task_id = request.form.get('task_id', '').strip() or f"paper_{int(time.time())}"

        def emit_paper_progress(status: str, current: int, total: int, message: str, log_type: str = 'info'):
            percent = int((current / total) * 100) if total > 0 else 0
            log_message = f"[PaperAgent] {message}"
            print(log_message)
            socketio.emit('progress', {
                'task_id': task_id,
                'status': status,
                'current': current,
                'total': total,
                'percent': percent,
                'message': message,
                'log_type': log_type,
                'log_message': log_message
            }, room=task_id)

        pages = None
        if pages_str:
            try:
                pages = parse_pages_input(pages_str)
            except ValueError as e:
                return jsonify({'error': str(e)}), 400

        try:
            converter = PDF2LaTeXEnhanced(model=model)
        except ValueError as e:
            return jsonify({'error': str(e)}), 400

        def paper_progress_callback(status, current, total, message, log_type='info', log_message=None, tokens=None):
            msg = log_message or message
            emit_paper_progress(status, current, total, msg, log_type=log_type)

        converter.set_progress_callback(paper_progress_callback)

        if latex_only_mode:
            # 纯 LaTeX 模式：直接转换 LaTeX 为文本
            emit_paper_progress('preparing', 1, 5, '准备分析 LaTeX 内容...')
            source_text, truncated = _latex_to_text(latex_content)
            if not source_text:
                return jsonify({'error': 'LaTeX 内容为空或解析失败'}), 400
            algorithm_blocks = _extract_algorithm_blocks_from_latex(latex_content)
            total_pages = 1
            if algorithm_blocks:
                emit_paper_progress('processing', 2, 5, f'检测到 {len(algorithm_blocks)} 段算法块，已注入提示词', 'quality')
            emit_paper_progress('processing', 3, 5, 'LaTeX 解析完成，开始AI学术阅读分析...', 'progress')
        else:
            # PDF 模式：上传 PDF 并提取文本
            timestamp = int(time.time())
            filename = secure_filename(file.filename)
            filepath = app.config['UPLOAD_FOLDER'] / f"paper_agent_{timestamp}_{filename}"
            file.save(filepath)

            emit_paper_progress('preparing', 1, 5, '已上传PDF，准备提取文本...')

            converter.set_progress_callback(paper_progress_callback)
            emit_paper_progress('extracting', 2, 5, '开始提取PDF文本...', 'progress')

            pages_text = converter.extract_text_from_pdf(str(filepath), pages=pages)
            selected_pages = pages if pages else list(range(len(pages_text)))

            chunks: List[str] = []
            for page_idx in selected_pages:
                if 0 <= page_idx < len(pages_text):
                    text = (pages_text[page_idx] or '').strip()
                    if text:
                        chunks.append(f"[第 {page_idx + 1} 页]\n{text}")

            if not chunks:
                return jsonify({'error': 'PDF文本提取失败，无法进行学术阅读分析'}), 400

            source_text = "\n\n".join(chunks)
            emit_paper_progress('processing', 3, 5, '文本提取完成，开始AI学术阅读分析...', 'progress')
            max_chars = 120000
            truncated = False
            if len(source_text) > max_chars:
                source_text = source_text[:max_chars]
                truncated = True

            algorithm_blocks = _extract_algorithm_blocks_from_latex(latex_content)
            if algorithm_blocks:
                emit_paper_progress('processing', 3, 5, f'检测到 {len(algorithm_blocks)} 段算法块，已注入提示词', 'quality')
            total_pages = len(selected_pages)

        prompts = _build_paper_agent_prompts(
            source_text=source_text,
            total_pages=total_pages,
            analysis_focus=analysis_focus,
            algorithm_blocks=algorithm_blocks
        )

        response = asyncio.run(
            converter.client.chat(
                messages=[
                    {'role': 'system', 'content': prompts['system_prompt']},
                    {'role': 'user', 'content': prompts['user_prompt']}
                ],
                temperature=0.2,
                max_tokens=5000
            )
        )

        usage = response.get('usage', {}) if isinstance(response, dict) else {}
        parsed = _parse_paper_agent_json(LLMClient.extract_content(response))
        emit_paper_progress('processing', 4, 5, 'AI分析完成，整理结构化结果...', 'progress')

        # 调试日志：记录AI返回的算法数据
        print(f"[PaperAgent] AI返回的算法块数量: {len(parsed.get('algorithms', []))}")
        for idx, algo in enumerate(parsed.get('algorithms', [])[:3]):  # 仅打印前3个
            print(f"[PaperAgent] 算法 {idx + 1}: {algo.get('name', '未命名')}")
            if algo.get('formulas'):
                print(f"  - 公式数量: {len(algo['formulas'])}")
                for jdx, f in enumerate(algo['formulas'][:2]):
                    print(f"    公式 {jdx + 1}: {f.get('latex', '无LaTeX')[:100]}")

        result_payload = {
            'success': True,
            'task_id': task_id,
            'mode': 'latex-academic-agent' if latex_only_mode else 'pdf-academic-agent',
            'source_filename': source_filename,
            'model': model,
            'analysis_focus': analysis_focus,
            'pages': pages_str if pages_str else 'all',
            'total_pages_analyzed': total_pages,
            'source_text_chars': len(source_text),
            'source_truncated': truncated,
            'algorithm_blocks_detected': len(algorithm_blocks),
            'prompt_guardrails': PAPER_AGENT_REQUIRED_INSTRUCTIONS,
            'result': {
                'summary': parsed['summary'],
                'outline': parsed['outline'],
                'mindmap_markdown': parsed['mindmap_markdown'],
                'algorithms': parsed['algorithms'],
                'limitations': parsed['limitations'],
                'evidence_note': parsed['evidence_note'],
                'raw_response': parsed['raw_response']
            },
            'stats': {
                'prompt_tokens': usage.get('prompt_tokens', 0),
                'completion_tokens': usage.get('completion_tokens', 0),
                'total_tokens': usage.get('total_tokens', 0)
            }
        }

        emit_paper_progress('completed', 5, 5, '学术阅读完成', 'success')

        return jsonify(result_payload)
    except Exception as e:
        try:
            socketio.emit('progress', {
                'task_id': request.form.get('task_id', '').strip() or 'paper_unknown',
                'status': 'error',
                'current': 0,
                'total': 1,
                'percent': 0,
                'message': f'学术阅读失败: {str(e)}',
                'log_type': 'error',
                'log_message': f'[PaperAgent] 学术阅读失败: {str(e)}'
            })
            print(f"[PaperAgent] 学术阅读失败: {str(e)}")
        except Exception:
            pass
        return jsonify({'error': str(e)}), 500
    finally:
        try:
            if filepath and filepath.exists():
                os.remove(filepath)
        except Exception:
            pass


# ==================== LaTeX 语法检查与纠错 API ====================

@app.route('/api/latex/check', methods=['POST'])
def check_latex_syntax_api():
    """检查 LaTeX 语法错误"""
    try:
        data = request.get_json(silent=True) or {}
        latex_content = data.get('latex', '')

        if not latex_content:
            return jsonify({'error': '请提供 LaTeX 内容'}), 400

        errors = check_latex_syntax(latex_content)

        return jsonify({
            'success': True,
            'error_count': len(errors),
            'errors': [
                {
                    'type': e.error_type,
                    'message': e.message,
                    'line': e.line,
                    'position': e.position,
                    'severity': e.severity,
                    'original': e.original,
                    'suggestion': e.suggestion
                }
                for e in errors
            ]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/latex/fix', methods=['POST'])
def fix_latex_syntax_api():
    """自动修复 LaTeX 语法错误"""
    try:
        data = request.get_json(silent=True) or {}
        latex_content = data.get('latex', '')

        if not latex_content:
            return jsonify({'error': '请提供 LaTeX 内容'}), 400

        fixed_content, remaining_errors = fix_latex_syntax(latex_content)

        return jsonify({
            'success': True,
            'original_errors': len(check_latex_syntax(latex_content)),
            'remaining_errors': len(remaining_errors),
            'fixed_content': fixed_content,
            'errors': [
                {
                    'type': e.error_type,
                    'message': e.message,
                    'line': e.line,
                    'severity': e.severity
                }
                for e in remaining_errors
            ]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/latex/validate', methods=['POST'])
def validate_latex_api():
    """验证 LaTeX 并返回详细报告"""
    try:
        data = request.get_json(silent=True) or {}
        latex_content = data.get('latex', '')

        if not latex_content:
            return jsonify({'error': '请提供 LaTeX 内容'}), 400

        report = validate_latex(latex_content)

        return jsonify({
            'success': True,
            'valid': report['valid'],
            'errors_count': report['errors_count'],
            'warnings_count': report['warnings_count'],
            'fix_suggestions': report['fix_suggestions']
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== 用户偏好管理 API ====================

@app.route('/api/preferences', methods=['GET'])
def get_preferences():
    """获取用户偏好设置"""
    try:
        prefs = preference_learner.get_all_preferences()
        return jsonify({
            'success': True,
            'preferences': prefs
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/preferences', methods=['POST'])
def update_preferences():
    """更新用户偏好设置"""
    try:
        data = request.get_json(silent=True) or {}

        for key, value in data.items():
            preference_learner.update_preference(key, value)

        return jsonify({
            'success': True,
            'message': '偏好已更新'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/preferences/terminology', methods=['GET'])
def get_terminology():
    """获取术语映射"""
    try:
        terminology = preference_learner.preferences.terminology
        return jsonify({
            'success': True,
            'terminology': terminology
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/preferences/terminology', methods=['POST'])
def add_terminology():
    """添加术语映射"""
    try:
        data = request.get_json(silent=True) or {}
        source = data.get('source', '').strip()
        target = data.get('target', '').strip()

        if not source or not target:
            return jsonify({'error': '请提供 source 和 target 术语'}), 400

        preference_learner.learn_terminology(source, target)

        return jsonify({
            'success': True,
            'message': f'术语映射已添加: {source} -> {target}'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/preferences/terminology/<path:source>', methods=['DELETE'])
def delete_terminology(source):
    """删除术语映射"""
    try:
        source = source.strip().lower()
        if source in preference_learner.preferences.terminology:
            del preference_learner.preferences.terminology[source]
            preference_learner._save_preferences()
            return jsonify({'success': True, 'message': f'已删除术语映射: {source}'})

        return jsonify({'error': '术语映射不存在'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/preferences/reset', methods=['POST'])
def reset_preferences():
    """重置所有偏好设置"""
    try:
        preference_learner.reset_preferences()
        return jsonify({'success': True, 'message': '偏好已重置'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/preferences/learn', methods=['POST'])
def learn_from_history():
    """从历史记录学习用户偏好"""
    try:
        data = request.get_json(silent=True) or {}
        record_index = data.get('record_index')

        if record_index is not None:
            # 从指定历史记录学习
            record = history_manager.get_record(int(record_index))
            if record:
                preference_learner.learn_from_record(record)
                return jsonify({'success': True, 'message': '已从历史记录学习偏好'})

        # 从所有历史记录学习
        for record in history_manager.get_history(limit=20):
            preference_learner.learn_from_record(record)

        return jsonify({'success': True, 'message': '已从所有历史记录学习偏好'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== 转换错误详情 API ====================

@app.route('/api/convert/detail-error', methods=['POST'])
def get_conversion_error_detail():
    """获取转换错误的详细报告（按页分类）"""
    try:
        data = request.get_json(silent=True) or {}
        errors = data.get('errors', [])

        collector = DetailedErrorCollector()

        for err in errors:
            collector.add_error(
                page_num=err.get('page', 0),
                error_type=err.get('type', 'unknown'),
                message=err.get('message', ''),
                recoverable=err.get('recoverable', True),
                retry_count=err.get('retry_count', 0)
            )

        summary = collector.get_summary()
        summary['formatted'] = collector.format_for_user()

        return jsonify({
            'success': True,
            'detail': summary
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== 论文结构知识图谱 API ====================

@app.route('/api/paper/knowledge-graph', methods=['POST'])
def get_knowledge_graph():
    """
    分析论文结构，构建知识图谱
    返回定理、引理及其依赖关系，用于可视化
    """
    try:
        data = request.get_json(silent=True) or {}
        latex_content = data.get('latex', '')

        if not latex_content:
            return jsonify({'error': '请提供 LaTeX 内容'}), 400

        graph_data = analyze_paper_structure(latex_content)

        return jsonify({
            'success': True,
            'graph': graph_data,
            'core_theorems': get_core_theorems(latex_content, top_n=5)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/paper/mind-map', methods=['POST'])
def get_paper_mind_map():
    """
    生成论文思维导图
    返回 Mermaid 格式的思维导图代码
    """
    try:
        data = request.get_json(silent=True) or {}
        latex_content = data.get('latex', '')
        layout = data.get('layout', 'hierarchical')
        include_proofs = data.get('include_proofs', False)

        if not latex_content:
            return jsonify({'error': '请提供 LaTeX 内容'}), 400

        # 转换为 MindMapLayout 枚举
        layout_map = {
            'hierarchical': MindMapLayout.HIERARCHICAL,
            'dependency': MindMapLayout.DEPENDENCY,
            'timeline': MindMapLayout.TIMELINE,
            'classification': MindMapLayout.CLASSIFICATION,
        }
        layout_enum = layout_map.get(layout, MindMapLayout.HIERARCHICAL)

        result = generate_mind_map_from_latex(
            latex_content,
            layout=layout,
            include_proofs=include_proofs
        )

        return jsonify({
            'success': True,
            'mermaid': result['mermaid'],
            'summary': result['summary'],
            'layouts_available': ['hierarchical', 'dependency', 'timeline', 'classification']
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/paper/core-theorems', methods=['POST'])
def get_paper_core_theorems():
    """获取论文的核心定理（被引用最多的）"""
    try:
        data = request.get_json(silent=True) or {}
        latex_content = data.get('latex', '')
        top_n = data.get('top_n', 5)

        if not latex_content:
            return jsonify({'error': '请提供 LaTeX 内容'}), 400

        theorems = get_core_theorems(latex_content, top_n=top_n)

        return jsonify({
            'success': True,
            'core_theorems': theorems
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== 渐进式双语对照阅读 API ====================

@app.route('/api/bilingual/view', methods=['POST'])
def get_bilingual_view():
    """
    创建双语对照视图
    将原文和译文按段落对齐，支持 hover 显示原文
    """
    try:
        data = request.get_json(silent=True) or {}
        original_content = data.get('original', '')
        translated_content = data.get('translated', '')

        if not original_content:
            return jsonify({'error': '请提供原文内容'}), 400

        if not translated_content:
            # 如果没有提供译文，返回原文分段（用于单语阅读）
            translated_content = original_content

        result = create_bilingual_view(original_content, translated_content)

        return jsonify({
            'success': True,
            'view': result
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== 转换质量评分 API ====================

@app.route('/api/latex/quality', methods=['POST'])
def get_latex_quality_score():
    """
    评估 LaTeX 转换质量
    返回 0-100 分及具体问题点
    """
    try:
        data = request.get_json(silent=True) or {}
        latex_content = data.get('latex', '')

        if not latex_content:
            return jsonify({'error': '请提供 LaTeX 内容'}), 400

        quality_report = score_latex_quality(latex_content)

        return jsonify({
            'success': True,
            'quality': quality_report
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/latex/quality-full', methods=['POST'])
def get_latex_quality_full():
    """
    综合评估：质量评分 + 语法检查 + 问题修复建议
    """
    try:
        data = request.get_json(silent=True) or {}
        latex_content = data.get('latex', '')

        if not latex_content:
            return jsonify({'error': '请提供 LaTeX 内容'}), 400

        # 质量评分
        quality = score_latex_quality(latex_content)

        # 语法检查
        syntax_errors = check_latex_syntax(latex_content)

        # 自动修复
        fixed_content, remaining_errors = fix_latex_syntax(latex_content)

        return jsonify({
            'success': True,
            'quality': quality,
            'syntax_check': {
                'error_count': len(syntax_errors),
                'errors': [
                    {
                        'type': e.error_type,
                        'message': e.message,
                        'line': e.line,
                        'severity': e.severity
                    }
                    for e in syntax_errors
                ]
            },
            'auto_fix': {
                'remaining_errors': len(remaining_errors),
                'fixed_content': fixed_content
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print("=" * 60)
    print("PDF2LaTeX + Image2LaTeX 增强版启动中...")
    print("=" * 60)
    print(f"上传目录: {UPLOAD_FOLDER.absolute()}")
    print(f"输出目录: {OUTPUT_FOLDER.absolute()}")
    print("=" * 60)
    print("访问地址: http://localhost:5000")
    print("新功能:")
    print("  ✓ 实时进度显示")
    print("  ✓ Token用量统计")
    print("  ✓ 美化代码展示")
    print("  ✓ 图片OCR识别 (DeepSeek Vision + Tesseract)")
    print("  ✓ 截图粘贴支持")
    print("按 Ctrl+C 停止服务器")
    print("=" * 60)
    
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
