"""
图片转 LaTeX 增强版
支持图片OCR识别和LaTeX转换
"""

import os
import time
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Tuple
from PIL import Image
import asyncio

from ocr_client import ocr_client
from clients import LLMClient
from config import settings
from latex_utils import sanitize_latex_body, split_references_section, wrap_with_template


class Image2LaTeXEnhanced:
    """图片转LaTeX增强类"""
    
    def __init__(
        self,
        model_name: str = "deepseek-chat",
        translate: bool = False,
        translation_prompt: str = "",
        progress_callback: Optional[Callable] = None
    ):
        """
        初始化图片转LaTeX转换器
        
        Args:
            model_name: 使用的LLM模型
            translate: 是否翻译中文为英文
            progress_callback: 进度回调函数
        """
        self.model_name = model_name
        self.translate = translate
        self.translation_prompt = translation_prompt.strip()
        self.progress_callback = progress_callback
        
        # 初始化LLM客户端
        self.llm_client = self._init_llm_client()
        
        # 统计信息
        self.stats = {
            'total_images': 0,
            'successful_images': 0,
            'failed_images': 0,
            'total_tokens': 0,
            'total_cost': 0.0
        }

    def _compose_translation_guidance(self) -> str:
        """拼接用户自定义翻译要求。"""
        if not self.translation_prompt:
            return ""
        return f"\n\n用户自定义翻译要求：\n{self.translation_prompt}\n\n优先级说明：在不违反数学公式、符号、变量名和参考文献原文保护规则的前提下，优先满足上述要求。"
    
    def _init_llm_client(self) -> LLMClient:
        """初始化LLM客户端"""
        model_configs = {
            'deepseek-chat': {
                'api_key': settings.DEEPSEEK_API_KEY,
                'base_url': 'https://api.deepseek.com/v1/chat/completions',
                'model': 'deepseek-chat'
            },
            'deepseek-reasoner': {
                'api_key': settings.DEEPSEEK_API_KEY,
                'base_url': 'https://api.deepseek.com/v1/chat/completions',
                'model': 'deepseek-reasoner'
            },
            'gpt4o': {
                'api_key': settings.OPENAI_API_KEY,
                'base_url': 'https://api.openai.com/v1/chat/completions',
                'model': 'gpt-4o'
            },
            'gpt4o-mini': {
                'api_key': settings.OPENAI_API_KEY,
                'base_url': 'https://api.openai.com/v1/chat/completions',
                'model': 'gpt-4o-mini'
            },
            'gpt52': {
                'api_key': settings.OPENAI_API_KEY,
                'base_url': 'https://api.openai.com/v1/chat/completions',
                'model': 'gpt-5.2'
            },
            'glm46': {
                'api_key': settings.ZHIPU_API_KEY,
                'base_url': 'https://open.bigmodel.cn/api/paas/v4/chat/completions',
                'model': 'glm-4.6'
            },
            'glm47': {
                'api_key': settings.ZHIPU_API_KEY,
                'base_url': 'https://open.bigmodel.cn/api/paas/v4/chat/completions',
                'model': 'glm-4.7'
            },
            'gemini3-pro': {
                'api_key': settings.GEMINI_API_KEY,
                'base_url': 'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions',
                'model': 'gemini-2.0-flash-exp'
            },
            'doubao': {
                'api_key': settings.DOUBAO_API_KEY,
                'base_url': 'https://ark.cn-beijing.volces.com/api/v3/chat/completions',
                'model': 'doubao-seed-2-0-lite-260215'
            },
            'deepseek-math': {
                'api_key': settings.CANOPY_WAVE_API_KEY,
                'base_url': 'https://api.canopywave.io/v1/chat/completions',
                'model': 'deepseek-ai/DeepSeek-Math-V2'
            }
        }
        
        config = model_configs.get(self.model_name)
        if not config:
            raise ValueError(f"不支持的模型: {self.model_name}。支持的模型: {list(model_configs.keys())}")
        
        if not config['api_key']:
            raise ValueError(f"模型 {self.model_name} 的 API Key 未配置，请检查 config.py")
        
        return LLMClient(
            api_key=config['api_key'],
            base_url=config['base_url'],
            model=config['model'],
            timeout=settings.DEFAULT_TIMEOUT
        )
    
    def _emit_progress(
        self,
        status: str,
        current: int,
        total: int,
        message: str,
        log_type: str = 'info',
        log_message: Optional[str] = None,
        tokens: Optional[Dict[str, Any]] = None
    ):
        """发送进度更新"""
        if self.progress_callback:
            self.progress_callback(
                status=status,
                current=current,
                total=total,
                message=message,
                log_type=log_type,
                log_message=log_message or message,
                tokens=tokens
            )
    
    async def extract_text_from_image(
        self,
        image_path: str,
        ocr_provider: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        从图片中提取文本
        
        Args:
            image_path: 图片路径
            ocr_provider: 指定OCR引擎 ('tesseract' | 'deepseek' | None=自动)
            
        Returns:
            {
                'text': str,
                'quality': float,
                'provider': str,
                'content_type': str
            }
        """
        try:
            # 读取图片
            image = Image.open(image_path)
            
            # OCR识别
            result = await ocr_client.recognize(image, force_provider=ocr_provider)
            
            return result
            
        except Exception as e:
            print(f"图片文本提取失败: {str(e)}")
            return {
                'text': '',
                'quality': 0.0,
                'provider': 'none',
                'content_type': 'unknown'
            }
    
    async def convert_to_latex(
        self,
        text: str,
        content_type: str = 'mixed',
        quality_mode: str = 'standard'
    ) -> Tuple[str, Dict[str, Any]]:
        """
        将识别的文本转换为LaTeX
        
        Args:
            text: OCR识别的文本
            content_type: 内容类型 ('text' | 'formula' | 'mixed')
            
        Returns:
            (latex_content, usage_stats)
        """
        # 如果需要翻译，先翻译成中文
        total_usage = {
            'prompt_tokens': 0,
            'completion_tokens': 0,
            'total_tokens': 0
        }
        
        print(f"[convert_to_latex] self.translate = {self.translate} (type={type(self.translate)})")
        print(f"[convert_to_latex] 文本预览: {text[:100]}...")
        
        if self.translate:
            print(f"[convert_to_latex] 开始翻译流程...")
            main_text, refs_text = split_references_section(text)
            if not main_text.strip():
                # 全部是参考文献时直接保留原文。
                main_text = text
                refs_text = ""

            # 第一步：翻译英文为中文
            self._emit_progress(
                'translating', 0, 2,
                '🌏 正在翻译英文为中文...',
                'info',
                '📝 步骤 1/2: 翻译内容'
            )
            
            translate_prompt = """你是一个专业的英中翻译专家。

你的任务：将英文学术内容翻译为中文。

翻译规则：
1. 数学公式、符号、变量名必须保持不变（如 x, y, G, U, V, E 等）
2. 数学表达式不要翻译（如 "bipartite graph" 翻译为 "二分图"，但保留 G = (U, V, E)）
3. 使用准确的学术术语（如 "matrix" → "矩阵"，"determinant" → "行列式"）
4. 保持原文的段落结构和格式
5. **绝对禁止翻译参考文献条目**（包括 [10]、[11] 等编号格式的文献），保持英文原样：作者名、论文标题、期刊名、会议名全部保持原文
6. 如果已经是中文的参考文献，保留其中文内容不变
7. 如果已经是中文，直接输出原文
8. **公式编号位置**：如果文本中有形如 "(1.13)"、"Eq. (1.13)"、"式 (1.13)" 等公式引用标记，必须将它们放在对应的公式内部（即 LaTeX 公式内部），而不是单独成行或放在公式外部。例如：应该翻译为 "\\[ D_t f = \\partial_t f + u \\cdot \\nabla f \\qquad (1.13)\\]"，而不是 "\\qquad (1.13) \\[ D_t f = ... \\]"

示例：
输入：Given a bipartite graph G = (U, V, E), its biadjacency matrix is defined as B(G).
输出：给定一个二分图 G = (U, V, E)，其双邻接矩阵定义为 B(G)。"""
            translate_prompt += self._compose_translation_guidance()

            try:
                response = await self.llm_client.chat(
                    messages=[
                        {"role": "system", "content": translate_prompt},
                        {"role": "user", "content": f"请将以下英文内容翻译为中文（注意：参考文献条目保持英文原样，不要翻译）:\n\n{main_text}"}
                    ],
                    temperature=0.1,
                    max_tokens=4000
                )
                
                # 使用翻译后的文本
                translated_main = response['choices'][0]['message']['content'].strip()
                if refs_text.strip():
                    text = f"{translated_main}\n\n{refs_text.strip()}"
                else:
                    text = translated_main
                
                # 累加token统计
                total_usage['prompt_tokens'] += response.get('usage', {}).get('prompt_tokens', 0)
                total_usage['completion_tokens'] += response.get('usage', {}).get('completion_tokens', 0)
                total_usage['total_tokens'] += response.get('usage', {}).get('total_tokens', 0)
                
                self._emit_progress(
                    'translating', 1, 2,
                    '✅ 翻译完成！',
                    'success',
                    f'📊 已翻译，使用 {response.get("usage", {}).get("total_tokens", 0)} tokens',
                    tokens=total_usage
                )
                
            except Exception as e:
                print(f"翻译失败: {str(e)}，将直接转换原文本")
                self._emit_progress(
                    'translating', 1, 2,
                    '⚠️ 翻译失败，使用原文',
                    'warning',
                    f'错误: {str(e)}'
                )
        
        # 第二步：转换为LaTeX
        step_text = '步骤 2/2: LaTeX转换' if self.translate else '⚙️ 正在转换为LaTeX...'
        self._emit_progress(
            'converting', 0, 1 if not self.translate else 2,
            '⚙️ 正在转换为LaTeX...',
            'info',
            step_text
        )
        
        # 根据内容类型调整提示词
        if content_type == 'formula':
            system_prompt = """你是一个数学公式LaTeX专家。
任务：将用户提供的数学公式内容转换为标准的LaTeX格式。

要求：
1. 保持数学公式的准确性
2. 使用标准的LaTeX数学环境（如 equation, align, gather 等）
3. 行内公式用 $...$，独立公式用 $$...$$
4. 不要添加任何解释，只输出LaTeX代码
5. 如果有多个公式，保持它们的相对位置
6. 参考文献条目（References/Bibliography/参考文献）保持原文，不要修改"""

        elif content_type == 'text':
            system_prompt = """你是一个文档LaTeX转换专家。
任务：将用户提供的文本内容转换为标准的LaTeX格式。

要求：
1. 保持文本结构和排版
2. 使用适当的LaTeX环境（如 section, subsection, itemize 等）
3. 不要添加任何解释，只输出LaTeX代码
4. 保留段落和换行
5. 参考文献条目（References/Bibliography/参考文献）保持原文，不要修改"""

        else:  # mixed
            system_prompt = """你是一个LaTeX转换专家。
任务：将用户提供的内容（包含文字和数学公式）转换为标准的LaTeX格式。

要求：
1. 文字部分使用普通文本
2. 数学公式使用LaTeX数学环境
3. 行内公式用 $...$，独立公式用 $$...$$
4. 保持原有的结构和排版
5. 参考文献条目（References/Bibliography/参考文献）保持原文语言，不要翻译作者名、标题、刊名
6. 不要添加任何解释，只输出LaTeX代码"""
        
        # 构建消息
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请转换以下内容:\n\n{text}"}
        ]
        
        # 调用LLM进行LaTeX转换
        try:
            response = await self.llm_client.chat(
                messages=messages,
                temperature=0.1,
                max_tokens=4000
            )
            
            latex_content = response['choices'][0]['message']['content'].strip()
            latex_content = sanitize_latex_body(latex_content)

            if quality_mode == 'high':
                refine_prompt = """你是 LaTeX 修复助手。请仅修复语法和结构问题，不改变内容语义，只输出修复后的 LaTeX 正文。"""
                refine_resp = await self.llm_client.chat(
                    messages=[
                        {"role": "system", "content": refine_prompt},
                        {"role": "user", "content": latex_content}
                    ],
                    temperature=0.1,
                    max_tokens=4000
                )
                latex_content = refine_resp['choices'][0]['message']['content'].strip()
                latex_content = sanitize_latex_body(latex_content)

                total_usage['prompt_tokens'] += refine_resp.get('usage', {}).get('prompt_tokens', 0)
                total_usage['completion_tokens'] += refine_resp.get('usage', {}).get('completion_tokens', 0)
                total_usage['total_tokens'] += refine_resp.get('usage', {}).get('total_tokens', 0)
            
            # 累加token统计
            total_usage['prompt_tokens'] += response.get('usage', {}).get('prompt_tokens', 0)
            total_usage['completion_tokens'] += response.get('usage', {}).get('completion_tokens', 0)
            total_usage['total_tokens'] += response.get('usage', {}).get('total_tokens', 0)
            
            # 显示转换完成进度
            self._emit_progress(
                'converting', 1 if not self.translate else 2, 1 if not self.translate else 2,
                '✅ LaTeX转换完成！',
                'success',
                f'📊 总计使用 {total_usage["total_tokens"]} tokens',
                tokens=total_usage
            )
            
            return latex_content, total_usage
            
        except Exception as e:
            print(f"LaTeX转换失败: {str(e)}")
            return f"% 转换失败: {str(e)}\n{text}", total_usage
    
    async def convert_image(
        self,
        image_path: str,
        output_path: Optional[str] = None,
        ocr_provider: Optional[str] = None,
        add_document_wrapper: bool = True,
        template_name: str = 'article',
        quality_mode: str = 'standard'
    ) -> Dict[str, Any]:
        """
        转换单张图片为LaTeX
        
        Args:
            image_path: 图片路径
            output_path: 输出路径
            ocr_provider: OCR引擎选择
            add_document_wrapper: 是否添加LaTeX文档包装
            
        Returns:
            转换结果字典
        """
        start_time = time.time()
        image_path = Path(image_path)
        
        self._emit_progress('extracting', 0, 1, '🖼️ 正在识别图片内容...', 'info', '📸 开始OCR识别')
        
        # OCR识别
        ocr_result = await self.extract_text_from_image(str(image_path), ocr_provider)
        
        if not ocr_result['text']:
            return {
                'success': False,
                'error': 'OCR识别失败，未能提取到文本',
                'ocr_result': ocr_result
            }
        
        self._emit_progress(
            'extracting', 1, 1,
            f"✅ OCR识别完成 (引擎: {ocr_result['provider']}, 质量: {ocr_result['quality']:.2%})",
            'success',
            f"📊 识别质量: {ocr_result['quality']:.2%} | 内容类型: {ocr_result['content_type']}"
        )
        
        # 转换为LaTeX（内部会根据 self.translate 决定是否翻译）
        # 不在这里显示进度，让 convert_to_latex 内部处理
        latex_content, usage_stats = await self.convert_to_latex(
            ocr_result['text'],
            ocr_result['content_type'],
            quality_mode=quality_mode
        )
        
        # 添加文档包装
        if add_document_wrapper:
            latex_content = wrap_with_template(
                latex_content,
                template_name=template_name,
                use_chinese=self.translate
            )
        
        # 保存输出
        if output_path is None:
            output_path = image_path.with_suffix('.tex')
        else:
            output_path = Path(output_path)
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(latex_content, encoding='utf-8')
        
        # 更新统计
        self.stats['total_images'] += 1
        self.stats['successful_images'] += 1
        self.stats['total_tokens'] += usage_stats.get('total_tokens', 0)
        
        elapsed_time = time.time() - start_time
        
        self._emit_progress(
            'completed', 1, 1,
            f'✅ 转换完成！耗时 {elapsed_time:.1f}秒',
            'success',
            f'💾 已保存到: {output_path.name}'
        )
        
        return {
            'success': True,
            'output_file': str(output_path),
            'ocr_result': ocr_result,
            'usage_stats': usage_stats,
            'elapsed_time': elapsed_time,
            'source_text': ocr_result.get('text', '')
        }
    
    async def batch_convert_images(
        self,
        image_paths: List[str],
        output_dir: Optional[str] = None,
        ocr_provider: Optional[str] = None,
        add_document_wrapper: bool = True,
        template_name: str = 'article',
        quality_mode: str = 'standard'
    ) -> Dict[str, Any]:
        """
        批量转换图片
        
        Args:
            image_paths: 图片路径列表
            output_dir: 输出目录
            ocr_provider: OCR引擎选择
            add_document_wrapper: 是否添加LaTeX文档包装
            
        Returns:
            批量转换结果
        """
        total_images = len(image_paths)
        results = []
        
        for idx, image_path in enumerate(image_paths, 1):
            self._emit_progress(
                'converting', idx - 1, total_images,
                f'🖼️ 正在处理第 {idx}/{total_images} 张图片...',
                'info',
                f'📄 处理文件: {Path(image_path).name}'
            )
            
            # 设置输出路径
            if output_dir:
                output_path = Path(output_dir) / Path(image_path).with_suffix('.tex').name
            else:
                output_path = None
            
            # 转换单张图片
            result = await self.convert_image(
                image_path,
                output_path=output_path,
                ocr_provider=ocr_provider,
                add_document_wrapper=add_document_wrapper,
                template_name=template_name,
                quality_mode=quality_mode
            )
            
            results.append(result)
        
        # 统计总结
        successful = sum(1 for r in results if r['success'])
        failed = total_images - successful
        
        return {
            'success': True,
            'total_images': total_images,
            'successful_images': successful,
            'failed_images': failed,
            'results': results,
            'stats': self.stats
        }
    
    def _wrap_latex_document(self, content: str) -> str:
        """添加LaTeX文档包装"""
        return f"""\\documentclass{{article}}
\\usepackage{{amsmath}}
\\usepackage{{amssymb}}
\\usepackage{{graphicx}}
\\usepackage{{ctex}}  % 中文支持
\\usepackage{{geometry}}
\\geometry{{a4paper, margin=1in}}

\\begin{{document}}

{content}

\\end{{document}}
"""
