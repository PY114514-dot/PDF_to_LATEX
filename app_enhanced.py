#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF2LaTeX Web应用 - 增强版
支持实时进度、Token统计、美化展示
"""

import os
import time
from pathlib import Path
from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename as werkzeug_secure_filename
from pdf2latex_enhanced import PDF2LaTeXEnhanced
from image2latex_enhanced import Image2LaTeXEnhanced
from config import settings
from history_manager import history_manager
import re
import unicodedata

app = Flask(__name__)
app.config['SECRET_KEY'] = 'pdf2latex-secret-key'
CORS(app)
socketio = SocketIO(
    app, 
    cors_allowed_origins="*",
    ping_timeout=300,  # 5分钟ping超时
    ping_interval=25,  # 25秒ping间隔
    async_mode='threading'
)

# 配置
UPLOAD_FOLDER = Path('uploads')
OUTPUT_FOLDER = Path('outputs')
UPLOAD_FOLDER.mkdir(exist_ok=True)
OUTPUT_FOLDER.mkdir(exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

ALLOWED_EXTENSIONS = {'pdf'}
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'bmp', 'tiff', 'gif'}

# 存储转换任务的状态
conversion_tasks = {}


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


@app.route('/')
def index():
    """主页"""
    return render_template('index_enhanced.html')


@app.route('/render')
def render_page():
    """LaTeX渲染页面"""
    return render_template('latex_render.html')


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
        model = request.form.get('model', 'deepseek-chat')  # 获取模型参数
        task_id = request.form.get('task_id', '')  # 获取前端传来的task_id
        
        # 解析页码
        pages = None
        if pages_str:
            try:
                pages = [int(p.strip()) - 1 for p in pages_str.split(',') if p.strip()]
            except ValueError:
                return jsonify({'error': '页码格式错误'}), 400
        
        # 保存文件
        filename = secure_filename(file.filename)
        timestamp = int(time.time())
        if not task_id:  # 如果前端没有传task_id，则生成一个
            task_id = f"task_{timestamp}"
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
            converter = PDF2LaTeXEnhanced(model=model)
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        
        # 设置进度回调
        def callback(status, current, total, message, log_type='info', log_message=None, tokens=None):
            progress_callback(task_id, status, current, total, message, log_type, log_message, tokens)
        
        converter.set_progress_callback(callback)
        
        # 生成输出文件名
        suffix = "_cn" if translate else ""
        output_filename = f"{timestamp}_{Path(filename).stem}{suffix}.tex"
        output_path = app.config['OUTPUT_FOLDER'] / output_filename
        
        # 执行转换
        result = converter.convert_pdf(
            pdf_path=str(filepath),
            output_path=str(output_path),
            pages=pages,
            add_document_wrapper=add_wrapper,
            translate=translate,
            task_id=task_id
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
                'estimated_cost': result.get('estimated_cost', 0),
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
            'download_url': f'/api/download/{output_filename}',
            'stats': {
                'total_pages': result.get('total_pages', 0),
                'processed_pages': result.get('processed_pages', 0),
                'total_tokens': result.get('total_tokens', 0),
                'prompt_tokens': result.get('prompt_tokens', 0),
                'completion_tokens': result.get('completion_tokens', 0),
                'estimated_cost': result.get('estimated_cost', 0),
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
        max_files = 10
        if len(files) > max_files:
            return jsonify({'error': f'最多支持同时上传{max_files}个文件'}), 400
        
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
        model = request.form.get('model', 'deepseek-chat')  # 获取模型参数
        
        # 解析页码
        pages = None
        if pages_str:
            try:
                pages = [int(p.strip()) - 1 for p in pages_str.split(',') if p.strip()]
            except ValueError:
                return jsonify({'error': '页码格式错误'}), 400
        
        # 创建批量任务ID
        timestamp = int(time.time())
        batch_id = f"batch_{timestamp}"
        
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
                    converter = PDF2LaTeXEnhanced(model=model)
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
                output_filename = f"{timestamp}_{idx}_{Path(filename).stem}{suffix}.tex"
                output_path = app.config['OUTPUT_FOLDER'] / output_filename
                
                # 执行转换
                result = converter.convert_pdf(
                    pdf_path=str(filepath),
                    output_path=str(output_path),
                    pages=pages,
                    add_document_wrapper=add_wrapper,
                    translate=translate,
                    task_id=task_id
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
                    'stats': {
                        'total_pages': result.get('total_pages', 0),
                        'processed_pages': result.get('processed_pages', 0),
                        'total_tokens': result.get('total_tokens', 0),
                        'prompt_tokens': result.get('prompt_tokens', 0),
                        'completion_tokens': result.get('completion_tokens', 0),
                        'estimated_cost': result.get('estimated_cost', 0),
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
                        'estimated_cost': result.get('estimated_cost', 0),
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
            'total_cost': sum(r.get('stats', {}).get('estimated_cost', 0) for r in results if r.get('success', False)),
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
        history = history_manager.get_history(limit=limit)
        return jsonify({
            'success': True,
            'history': history
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
        model = request.form.get('model', 'deepseek-chat')
        translate_raw = request.form.get('translate', 'false')
        translate = translate_raw.lower() == 'true'
        ocr_provider = request.form.get('ocr_provider', 'mixed')  # 'mixed' | 'tesseract' | 'vision'
        add_wrapper = request.form.get('add_document_wrapper', 'true').lower() == 'true'
        
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
            progress_callback=callback
        )
        
        # 执行转换（同步包装异步）
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        output_filename = f"{timestamp}_{Path(filename).stem}.tex"
        output_path = OUTPUT_FOLDER / output_filename
        
        result = loop.run_until_complete(
            converter.convert_image(
                str(filepath),
                output_path=str(output_path),
                ocr_provider=ocr_provider if ocr_provider != 'mixed' else None,
                add_document_wrapper=add_wrapper
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
        
        # 计算成本（根据模型）
        usage = result['usage_stats']
        estimated_cost = 0.0
        
        # DeepSeek 定价 (per 1M tokens)
        if 'deepseek' in model.lower():
            input_cost_per_m = 0.14  # $0.14 per 1M input tokens
            output_cost_per_m = 0.28  # $0.28 per 1M output tokens
            estimated_cost = (
                usage.get('prompt_tokens', 0) * input_cost_per_m / 1_000_000 +
                usage.get('completion_tokens', 0) * output_cost_per_m / 1_000_000
            )
        else:
            # 其他模型使用通用估算
            estimated_cost = usage.get('total_tokens', 0) * 0.002 / 1000
        
        # 构建统一的stats结构
        stats = {
            'processed_pages': 1,  # 图片按1页计
            'total_pages': 1,
            'prompt_tokens': usage.get('prompt_tokens', 0),
            'completion_tokens': usage.get('completion_tokens', 0),
            'total_tokens': usage.get('total_tokens', 0),
            'estimated_cost': estimated_cost,
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
        model = request.form.get('model', 'deepseek-chat')
        translate = request.form.get('translate', 'false').lower() == 'true'
        ocr_provider = request.form.get('ocr_provider', 'mixed')
        add_wrapper = request.form.get('add_document_wrapper', 'true').lower() == 'true'
        
        # 创建进度回调
        def callback(status, current, total, message, log_type='info', log_message=None, tokens=None):
            progress_callback(task_id, status, current, total, message, log_type, log_message, tokens)
        
        # 创建转换器
        converter = Image2LaTeXEnhanced(
            model_name=model,
            translate=translate,
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
                add_document_wrapper=add_wrapper
            )
        )
        
        loop.close()
        
        # 清理上传文件
        for filepath in uploaded_paths:
            try:
                os.remove(filepath)
            except:
                pass
        
        # 计算总成本和统计信息
        total_cost = 0.0
        total_tokens = 0
        total_time = 0.0
        
        # DeepSeek 定价
        input_cost_per_m = 0.14 if 'deepseek' in model.lower() else 0.002
        output_cost_per_m = 0.28 if 'deepseek' in model.lower() else 0.002
        
        # 处理每个结果，添加统一的stats结构
        processed_results = []
        for res in result.get('results', []):
            if res.get('success'):
                usage = res.get('usage_stats', {})
                estimated_cost = (
                    usage.get('prompt_tokens', 0) * input_cost_per_m / 1_000_000 +
                    usage.get('completion_tokens', 0) * output_cost_per_m / 1_000_000
                )
                
                total_cost += estimated_cost
                total_tokens += usage.get('total_tokens', 0)
                total_time += res.get('elapsed_time', 0)
                
                # 添加统一的stats结构
                res['stats'] = {
                    'processed_pages': 1,
                    'total_pages': 1,
                    'prompt_tokens': usage.get('prompt_tokens', 0),
                    'completion_tokens': usage.get('completion_tokens', 0),
                    'total_tokens': usage.get('total_tokens', 0),
                    'estimated_cost': estimated_cost,
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
                'total_cost': total_cost,
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
