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
import shutil
import subprocess
import tempfile
import uuid
import logging
import secrets
from pathlib import Path
from typing import Any, Dict, List
from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename as werkzeug_secure_filename
from pdf2latex_enhanced import PDF2LaTeXEnhanced
from clients import LLMClient
from config import settings

# API Key 必须不落入持久任务 JSON；仅供当前进程正在执行的任务使用。
_transient_task_api_keys = {}
from history_manager import history_manager, preference_learner
from task_manager import async_task_manager
from latex_utils import merge_tex_contents, replace_latex_page_block, validate_latex_page
from latex_syntax import check_latex_syntax, fix_latex_syntax, validate_latex, score_latex_quality
from error_handler import DetailedErrorCollector, create_error_context
from costs import calculate_llm_cost
import re
import unicodedata

app = Flask(__name__, template_folder='../frontend/templates', static_folder='../frontend/static')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY') or secrets.token_urlsafe(32)
CORS(app, origins=settings.CORS_ORIGINS)
socketio = SocketIO(
    app, 
    cors_allowed_origins=settings.CORS_ORIGINS,
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
MAX_BATCH_PDF_FILES = 5

# 存储转换任务的状态
conversion_tasks = {}
conversion_tasks_lock = threading.RLock()
CONVERSION_TASK_TTL_SECONDS = 60 * 60
MAX_CONVERSION_TASKS = 200
logger = logging.getLogger(__name__)

if not settings.validate():
    logger.warning(
        "No LLM API key is configured. Local text conversion remains available, "
        "but translation and LLM formula reconstruction will be unavailable."
    )


def _cleanup_conversion_tasks() -> None:
    """Retain active tasks and bound completed task metadata in memory."""
    now = time.time()
    with conversion_tasks_lock:
        expired = [
            task_id for task_id, task in conversion_tasks.items()
            if task.get('status') in {'completed', 'error', 'failed'}
            and now - task.get('completed_at', task.get('updated_at', now)) > CONVERSION_TASK_TTL_SECONDS
        ]
        for task_id in expired:
            conversion_tasks.pop(task_id, None)

        if len(conversion_tasks) > MAX_CONVERSION_TASKS:
            terminal = sorted(
                (
                    (task.get('completed_at', task.get('updated_at', 0)), task_id)
                    for task_id, task in conversion_tasks.items()
                    if task.get('status') in {'completed', 'error', 'failed'}
                )
            )
            for _, task_id in terminal[:len(conversion_tasks) - MAX_CONVERSION_TASKS]:
                conversion_tasks.pop(task_id, None)


def _create_conversion_task(task_id: str, **data: Any) -> None:
    _cleanup_conversion_tasks()
    now = time.time()
    with conversion_tasks_lock:
        conversion_tasks[task_id] = {
            **data, 'created_at': now, 'updated_at': now,
        }


def _finish_conversion_task(task_id: str, status: str) -> None:
    """Mark terminal task state so TTL/capacity cleanup can reclaim it."""
    now = time.time()
    with conversion_tasks_lock:
        task = conversion_tasks.get(task_id)
        if task is not None:
            task.update(status=status, updated_at=now, completed_at=now)
    _cleanup_conversion_tasks()

PAPER_AGENT_REQUIRED_INSTRUCTIONS = []


def allowed_file(filename):
    """检查文件扩展名是否允许"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


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


def _latex_compile_errors(log: str) -> List[Dict[str, Any]]:
    """Extract actionable compiler errors without exposing temporary paths."""
    errors: List[Dict[str, Any]] = []
    current_line = None
    raw_lines = (log or '').splitlines()
    lines: List[str] = []
    index = 0
    while index < len(raw_lines):
        raw_line = raw_lines[index]
        # TeX wraps long diagnostics at its print-width. Join the continuation
        # before parsing so a Windows temporary path cannot truncate messages.
        if re.search(r'\.tex:\d+:', raw_line):
            joined = raw_line.strip()
            while index + 1 < len(raw_lines):
                next_line = raw_lines[index + 1].strip()
                if not next_line or re.search(r'\.tex:\d+:|^! |^l\.', next_line):
                    break
                joined += next_line
                index += 1
            lines.append(joined)
        else:
            lines.append(raw_line)
        index += 1

    for raw_line in lines:
        clean_line = raw_line.replace('\r', '').strip()
        file_line_match = re.search(r'\.tex:(\d+):\s*(.+)', clean_line)
        if file_line_match:
            message = file_line_match.group(2).strip()
            if 'Fatal error' in message:
                continue
            errors.append({
                'line': int(file_line_match.group(1)),
                'message': message,
            })
            current_line = int(file_line_match.group(1))
            continue
        line_match = re.search(r'^l\.(\d+)\s*(.*)$', raw_line.strip())
        if line_match:
            current_line = int(line_match.group(1))
            if errors and errors[-1]['line'] is None:
                errors[-1]['line'] = current_line
            continue
        if raw_line.startswith('! '):
            errors.append({
                'line': current_line,
                'message': raw_line[2:].strip(),
            })

    return errors[:10]


def _select_latex_compiler(latex_content: str, template_name: str) -> str | None:
    """Prefer XeLaTeX for Chinese documents; otherwise use the faster pdfLaTeX."""
    needs_unicode = (
        template_name == 'cn-article'
        or 'xeCJK' in latex_content
        or bool(re.search(r'[\u4e00-\u9fff]', latex_content))
    )
    candidates = ('xelatex', 'pdflatex') if needs_unicode else ('pdflatex', 'xelatex')
    return next((compiler for compiler in candidates if shutil.which(compiler)), None)


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
        if re.fullmatch(r'-\d+', part):
            raise ValueError(f"页码必须大于0: {part}")
        if re.fullmatch(r'\d+\s*-\s*-\d+', part):
            raise ValueError(f"页码必须大于0: {part}")
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


def _get_pdf_page_count(pdf_path: Path) -> int:
    """Read the page count once so page-specific operations can validate input."""
    import PyPDF2
    with pdf_path.open('rb') as pdf_file:
        return len(PyPDF2.PdfReader(pdf_file).pages)



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
    
    logger.info(
        "Task progress task_id=%s status=%s current=%s total=%s message=%s tokens=%s",
        task_id, status, current, total, log_message or message, tokens,
    )
    socketio.emit('progress', progress_data, room=task_id)
    
    # 更新任务状态
    with conversion_tasks_lock:
        if task_id in conversion_tasks:
            task = conversion_tasks[task_id]
            task.update(progress_data)
            task['updated_at'] = time.time()
            if status in {'completed', 'error', 'failed'}:
                task['completed_at'] = time.time()
    _cleanup_conversion_tasks()

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
            'cost': result.get('cost', {}),
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
    translation_prompt = payload.get('translation_prompt', '')
    api_key = _transient_task_api_keys.pop(task_id, '')
    reasoning_effort = payload.get('reasoning_effort', '')

    try:
        if not pdf_path or not Path(pdf_path).exists():
            raise FileNotFoundError('源文件不存在，无法恢复任务')

        async_task_manager.update_task(task_id, status='processing', error=None)

        converter = PDF2LaTeXEnhanced(
            model=model, translation_prompt=translation_prompt,
            api_key=api_key, reasoning_effort=reasoning_effort,
        )

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
            'page_diagnostics': result.get('page_diagnostics', []),
            'download_url': f"/api/download/{Path(output_path).name}",
            'stats': {
                'total_pages': result.get('total_pages', 0),
                'processed_pages': result.get('processed_pages', 0),
                'total_tokens': result.get('total_tokens', 0),
                'prompt_tokens': result.get('prompt_tokens', 0),
                'completion_tokens': result.get('completion_tokens', 0),
                'cost': result.get('cost', {}),
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
        _create_conversion_task(
            task_id,
            status='processing', current=0, total=100, percent=0,
        )
        
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
                'cost': result.get('cost', {}),
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
            'page_diagnostics': result.get('page_diagnostics', []),
            'download_url': f'/api/download/{output_filename}',
            'stats': {
                'total_pages': result.get('total_pages', 0),
                'processed_pages': result.get('processed_pages', 0),
                'total_tokens': result.get('total_tokens', 0),
                'prompt_tokens': result.get('prompt_tokens', 0),
                'completion_tokens': result.get('completion_tokens', 0),
                'cost': result.get('cost', {}),
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
        _finish_conversion_task(task_id, 'completed')
        return jsonify(result_data)
    
    except Exception as e:
        logger.exception("PDF conversion failed for task %s", task_id)
        progress_callback(task_id, 'error', 0, 1, str(e), 'error', str(e))
        return jsonify({'error': str(e)}), 500
    
    finally:
        # 清理上传的文件
        try:
            if filepath and filepath.exists():
                os.remove(filepath)
        except OSError as exc:
            logger.warning("Failed to remove temporary upload %s: %s", filepath, exc)


@app.route('/api/download/<path:filename>')
def download_file(filename):
    """下载生成的LaTeX文件"""
    try:
        output_folder = app.config['OUTPUT_FOLDER'].resolve()
        filepath = (output_folder / filename).resolve()
        if filepath.parent != output_folder or not filepath.is_file() or filepath.suffix.lower() != '.tex':
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
        _create_conversion_task(
            batch_id,
            status='processing', total_files=len(files),
            completed_files=0, results=[],
        )
        
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
                        'cost': result.get('cost', {}),
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
                        'cost': result.get('cost', {}),
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
        successful_costs = [
            r.get('stats', {}).get('cost', {})
            for r in results if r.get('success', False)
        ]
        if successful_costs and all(cost.get('pricing_configured') for cost in successful_costs):
            total_stats['cost'] = {
                'pricing_configured': True,
                'currency': successful_costs[0].get('currency', 'CNY'),
                'total_cost': round(sum(cost.get('total_cost', 0) for cost in successful_costs), 6),
            }
        else:
            total_stats['cost'] = {'pricing_configured': False}
        
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
        
        _finish_conversion_task(batch_id, 'completed')
        return jsonify(batch_result)
    
    except Exception as e:
        logger.exception("Batch PDF conversion failed for task %s", batch_id)
        _finish_conversion_task(batch_id, 'error')
        return jsonify({'error': str(e)}), 500
    
    finally:
        # 清理上传的文件
        for filepath in uploaded_files:
            try:
                if filepath.exists():
                    os.remove(filepath)
            except OSError as exc:
                logger.warning("Failed to remove temporary upload %s: %s", filepath, exc)


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
        except OSError as exc:
            logger.warning("Failed to remove temporary upload %s: %s", filepath, exc)


@app.route('/api/retry-page', methods=['POST'])
def retry_pdf_page():
    """Reconvert one selected PDF page and replace only its LaTeX block."""
    filepath = None
    try:
        if 'file' not in request.files:
            return jsonify({'error': '请重新选择原始 PDF 后再重试该页。'}), 400

        file = request.files['file']
        if not file.filename or not allowed_file(file.filename):
            return jsonify({'error': '重试时只支持原始 PDF 文件。'}), 400

        try:
            page_num = int(request.form.get('page', '0'))
        except ValueError:
            return jsonify({'error': '重试页码无效。'}), 400
        if page_num < 1:
            return jsonify({'error': '重试页码必须大于 0。'}), 400

        document = request.form.get('latex_content', '')
        if not document.strip():
            return jsonify({'error': '当前 LaTeX 内容为空，无法仅重试单页。'}), 400

        model = request.form.get('model', settings.DEFAULT_MODEL)
        translate = request.form.get('translate', 'false').lower() == 'true'
        quality_mode = request.form.get('quality_mode', 'standard')
        translation_prompt = request.form.get('translation_prompt', '').strip()
        api_key = request.form.get('api_key', '').strip()
        reasoning_effort = request.form.get('reasoning_effort', '').strip()
        if quality_mode not in {'standard', 'high'}:
            return jsonify({'error': '重试质量模式无效。'}), 400

        filename = secure_filename(file.filename)
        filepath = app.config['UPLOAD_FOLDER'] / f"retry_{uuid.uuid4().hex}_{filename}"
        file.save(filepath)
        total_pages = _get_pdf_page_count(filepath)
        if page_num > total_pages:
            return jsonify({'error': f'第 {page_num} 页不存在；该 PDF 共 {total_pages} 页。'}), 400

        converter = PDF2LaTeXEnhanced(model=model, translation_prompt=translation_prompt)
        page_index = page_num - 1
        page_text = converter.extract_text_from_pdf(str(filepath), [page_index])[page_index]
        if not page_text.strip():
            return jsonify({
                'error': f'第 {page_num} 页未提取到可转换文本。请改用 OCR 或保留原文。'
            }), 422

        latex_page = converter.convert_text_to_latex(
            page_text,
            page_index,
            total_pages,
            translate=translate,
            quality_mode=quality_mode,
            force_llm=quality_mode == 'high',
        )
        validation = validate_latex_page(latex_page)
        page_diagnostic = {
            'page': page_num,
            'status': 'warning' if validation['warnings_count'] else 'success',
            **validation,
        }
        updated_document = replace_latex_page_block(document, page_num, latex_page)

        retry_source_name = f"{Path(filename).stem}_retry_p{page_num}.pdf"
        output_filename = build_output_filename(retry_source_name, translate=translate)
        output_path = app.config['OUTPUT_FOLDER'] / output_filename
        output_path.write_text(updated_document, encoding='utf-8')

        logger.info(
            "Page retry completed page=%s model=%s quality_mode=%s tokens=%s",
            page_num, model, quality_mode, converter.total_tokens,
        )
        return jsonify({
            'success': True,
            'content': updated_document,
            'filename': output_filename,
            'download_url': f'/api/download/{output_filename}',
            'page_diagnostic': page_diagnostic,
            'stats': {
                'prompt_tokens': converter.prompt_tokens,
                'completion_tokens': converter.completion_tokens,
                'total_tokens': converter.total_tokens,
                'cost': calculate_llm_cost(
                    converter.model_name,
                    converter.prompt_tokens,
                    converter.completion_tokens,
                ),
            },
        })
    except ValueError as exc:
        logger.info("Page retry rejected: %s", exc)
        return jsonify({'error': str(exc)}), 400
    except Exception:
        logger.exception("Page retry failed")
        return jsonify({'error': '重试该页失败。请检查模型配置或稍后再试。'}), 500
    finally:
        if filepath:
            try:
                filepath.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("Failed to remove page retry upload %s: %s", filepath, exc)



@app.route('/api/review-page-source', methods=['POST'])
def review_page_source():
    """Extract one PDF page for review without invoking translation or LLM conversion."""
    filepath = None
    try:
        if 'file' not in request.files:
            return jsonify({'error': '请重新选择原始 PDF 后再查看提取文本。'}), 400
        file = request.files['file']
        if not file.filename or not allowed_file(file.filename):
            return jsonify({'error': '审校时只支持原始 PDF 文件。'}), 400
        try:
            page_num = int(request.form.get('page', '0'))
        except ValueError:
            return jsonify({'error': '页码无效。'}), 400
        if page_num < 1:
            return jsonify({'error': '页码必须大于 0。'}), 400

        filename = secure_filename(file.filename)
        filepath = app.config['UPLOAD_FOLDER'] / f"review_{uuid.uuid4().hex}_{filename}"
        file.save(filepath)
        total_pages = _get_pdf_page_count(filepath)
        if page_num > total_pages:
            return jsonify({'error': f'第 {page_num} 页不存在；该 PDF 共 {total_pages} 页。'}), 400

        converter = PDF2LaTeXEnhanced(model=settings.DEFAULT_MODEL)
        text = converter.extract_text_from_pdf(str(filepath), [page_num - 1])[page_num - 1]
        logger.info("Review source extracted page=%s chars=%s", page_num, len(text))
        return jsonify({'success': True, 'page': page_num, 'extracted_text': text})
    except Exception:
        logger.exception("Review source extraction failed")
        return jsonify({'error': '读取该页提取文本失败，请检查 PDF 或 OCR 配置。'}), 500
    finally:
        if filepath:
            try:
                filepath.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("Failed to remove review upload %s: %s", filepath, exc)


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
        translation_prompt = request.form.get('translation_prompt', '').strip()

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
            'quality_mode': quality_mode,
            'translation_prompt': translation_prompt,
            'reasoning_effort': reasoning_effort,
        }
        if api_key:
            _transient_task_api_keys[task_id] = api_key
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
        logger.exception("Batch PDF conversion failed for task %s", batch_id)
        _finish_conversion_task(batch_id, 'error')
        return jsonify({'error': str(e)}), 500


@app.route('/api/latex/compile', methods=['POST'])
def compile_latex_api():
    """Compile editor content and return a short, line-aware diagnostic report."""
    try:
        data = request.get_json(silent=True) or {}
        latex_content = (data.get('latex') or '').strip()
        template_name = (data.get('template') or 'article').lower()
        if not latex_content:
            return jsonify({'error': '请提供 LaTeX 内容'}), 400
        if len(latex_content) > 2_000_000:
            return jsonify({'error': 'LaTeX 内容过大，最大支持 2 MB'}), 413

        compiler = _select_latex_compiler(latex_content, template_name)
        if not compiler:
            return jsonify({
                'success': False,
                'error': '未找到 LaTeX 编译器。请安装 TeX Live 或 MiKTeX 后重试。',
                'errors': [],
            }), 503

        source = latex_content
        if not re.search(r'\\documentclass(?:\[[^\]]*\])?\{', source):
            from latex_utils import wrap_with_template
            source = wrap_with_template(
                source,
                template_name=template_name,
                use_chinese=template_name == 'cn-article',
            )

        with tempfile.TemporaryDirectory(prefix='pdf2latex_compile_') as temp_dir:
            workdir = Path(temp_dir)
            tex_path = workdir / 'document.tex'
            tex_path.write_text(source, encoding='utf-8')
            command = [
                compiler,
                '-interaction=nonstopmode',
                '-halt-on-error',
                '-file-line-error',
                '-no-shell-escape',
                '-output-directory', str(workdir),
                str(tex_path),
            ]
            completed = subprocess.run(
                command,
                cwd=workdir,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=90,
            )
            log = (completed.stdout or '') + '\n' + (completed.stderr or '')
            pdf_path = workdir / 'document.pdf'
            if completed.returncode != 0 or not pdf_path.exists():
                errors = _latex_compile_errors(log)
                return jsonify({
                    'success': False,
                    'compiler': compiler,
                    'errors': errors,
                    'error': errors[0]['message'] if errors else 'LaTeX 编译失败，请检查日志和语法。',
                }), 422

            output_filename = f'preview_{uuid.uuid4().hex}.pdf'
            output_path = app.config['OUTPUT_FOLDER'] / output_filename
            shutil.copyfile(pdf_path, output_path)
            return jsonify({
                'success': True,
                'compiler': compiler,
                'filename': output_filename,
                'pdf_url': f'/api/latex/preview/{output_filename}',
            })
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': '编译超时（90 秒）', 'errors': []}), 408
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/latex/preview/<filename>', methods=['GET'])
def preview_compiled_latex(filename):
    """Serve a generated preview PDF inline, with filename traversal blocked."""
    if Path(filename).name != filename or not filename.endswith('.pdf'):
        return jsonify({'error': '无效的预览文件名'}), 400
    filepath = app.config['OUTPUT_FOLDER'] / filename
    if not filepath.is_file():
        return jsonify({'error': '预览文件不存在'}), 404
    return send_file(filepath, mimetype='application/pdf', as_attachment=False)


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
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(name)s | %(message)s')
    logger.info("PDF2LaTeX starting at http://%s:5000", settings.APP_HOST)
    logger.info("Upload directory: %s | Output directory: %s", UPLOAD_FOLDER.absolute(), OUTPUT_FOLDER.absolute())
    socketio.run(app, debug=settings.APP_DEBUG, host=settings.APP_HOST, port=5000)
