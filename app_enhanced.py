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
from werkzeug.utils import secure_filename
from pdf2latex_enhanced import PDF2LaTeXEnhanced

app = Flask(__name__)
app.config['SECRET_KEY'] = 'pdf2latex-secret-key'
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# 配置
UPLOAD_FOLDER = Path('uploads')
OUTPUT_FOLDER = Path('outputs')
UPLOAD_FOLDER.mkdir(exist_ok=True)
OUTPUT_FOLDER.mkdir(exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

ALLOWED_EXTENSIONS = {'pdf'}

# 存储转换任务的状态
conversion_tasks = {}


def allowed_file(filename):
    """检查文件扩展名是否允许"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def progress_callback(task_id, status, current, total, message):
    """进度回调函数"""
    progress_data = {
        'task_id': task_id,
        'status': status,
        'current': current,
        'total': total,
        'percent': int((current / total * 100)) if total > 0 else 0,
        'message': message
    }
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
        
        # 创建转换器
        converter = PDF2LaTeXEnhanced()
        
        # 设置进度回调
        def callback(status, current, total, message):
            progress_callback(task_id, status, current, total, message)
        
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
        
        # 返回结果
        return jsonify({
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
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
    finally:
        # 清理上传的文件
        try:
            if filepath and filepath.exists():
                os.remove(filepath)
        except:
            pass


@app.route('/api/download/<filename>')
def download_file(filename):
    """下载生成的LaTeX文件"""
    try:
        filepath = app.config['OUTPUT_FOLDER'] / filename
        if not filepath.exists():
            return jsonify({'error': '文件不存在'}), 404
        
        return send_file(
            filepath,
            as_attachment=True,
            download_name=filename,
            mimetype='application/x-tex'
        )
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
                
                def callback(status, current, total, message):
                    progress_callback(batch_id, status, idx + 1, len(files), 
                                    f'[{idx + 1}/{len(files)}] {filename}: {message}')
                
                # 创建转换器
                converter = PDF2LaTeXEnhanced()
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
        
        # 发送完成进度
        progress_callback(batch_id, 'completed', len(files), len(files), 
                         f'批量转换完成！成功 {total_stats["successful_files"]}/{total_stats["total_files"]} 个文件')
        
        return jsonify({
            'success': True,
            'batch_id': batch_id,
            'results': results,
            'total_stats': total_stats
        })
    
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
        
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'{batch_id}_results.zip'
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/status', methods=['GET'])
def status():
    """检查API状态"""
    return jsonify({
        'status': 'running',
        'message': 'PDF2LaTeX Enhanced API is running'
    })


if __name__ == '__main__':
    print("=" * 60)
    print("PDF2LaTeX 增强版启动中...")
    print("=" * 60)
    print(f"上传目录: {UPLOAD_FOLDER.absolute()}")
    print(f"输出目录: {OUTPUT_FOLDER.absolute()}")
    print("=" * 60)
    print("访问地址: http://localhost:5000")
    print("新功能:")
    print("  ✓ 实时进度显示")
    print("  ✓ Token用量统计")
    print("  ✓ 美化代码展示")
    print("按 Ctrl+C 停止服务器")
    print("=" * 60)
    
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
