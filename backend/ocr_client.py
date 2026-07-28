"""
OCR 客户端 - 支持多种OCR引擎
混合方案：Tesseract (本地) + DeepSeek Vision (云端)
"""

import os
import base64
import re
import logging
import threading
from io import BytesIO
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from PIL import Image, ImageEnhance, ImageFilter
import pytesseract
import httpx

from config import settings

logger = logging.getLogger(__name__)

_paddle_engine = None
_paddle_engine_lock = threading.Lock()

# OpenCV 是可选的，用于高级图像处理
try:
    import cv2
    import numpy as np
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False
    logger.info("OpenCV is unavailable; OCR image preprocessing will use Pillow")


class OCRClient:
    """OCR 识别客户端，支持混合方案"""
    
    def __init__(self):
        """初始化OCR客户端"""
        self.provider = settings.OCR_PROVIDER
        
        # 配置 Tesseract 路径（Windows需要）
        if os.path.exists(settings.TESSERACT_CMD):
            pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD
        
        # Vision API 配置（支持图片识别的模型）
        # 注意：DeepSeek 当前不支持 Vision，使用 GPT-4o 或 Gemini
        self.vision_api_key = settings.OPENAI_API_KEY or settings.GEMINI_API_KEY
        self.vision_base_url = "https://api.openai.com/v1" if settings.OPENAI_API_KEY else "https://generativelanguage.googleapis.com/v1beta"
        self.vision_model = "gpt-4o" if settings.OPENAI_API_KEY else "gemini-2.0-flash-exp"
        self.timeout = settings.DEFAULT_TIMEOUT
        
        # 检查是否有可用的 Vision API
        self.has_vision_api = bool(settings.OPENAI_API_KEY or settings.GEMINI_API_KEY)
    
    def preprocess_image(
        self,
        image: Image.Image,
        enhance: bool = True,
        layout_hint: Optional[str] = None,
        skip_resize: bool = False,
    ) -> Image.Image:
        """
        图片预处理，提高OCR识别率
        
        Args:
            image: PIL图片对象
            enhance: 是否增强处理
            
        Returns:
            处理后的图片
        """
        # 转换为RGB模式
        if image.mode != 'RGB':
            image = image.convert('RGB')

        # Vision models receive the original raster dimensions unless the
        # caller explicitly asks for local-OCR preprocessing.
        if skip_resize:
            return image
        
        # 确保图片足够清晰 - 提高最小尺寸以改善识别率
        min_size = 800  # 最小边长
        if min(image.size) < min_size:
            ratio = min_size / min(image.size)
            new_size = tuple(int(dim * ratio) for dim in image.size)
            image = image.resize(new_size, Image.Resampling.LANCZOS)
        
        # 限制图片最大尺寸
        max_size = settings.IMAGE_MAX_SIZE
        if max(image.size) > max_size:
            ratio = max_size / max(image.size)
            new_size = tuple(int(dim * ratio) for dim in image.size)
            image = image.resize(new_size, Image.Resampling.LANCZOS)
        
        if not enhance:
            return image

        if layout_hint in {'table', 'code'}:
            gray_image = image.convert('L')
            enhancer = ImageEnhance.Contrast(gray_image)
            enhanced = enhancer.enhance(1.6 if layout_hint == 'table' else 1.4)
            enhancer = ImageEnhance.Sharpness(enhanced)
            return enhancer.enhance(1.15 if layout_hint == 'table' else 1.05)
        
        # 使用OpenCV进行高级增强（如果可用）
        if HAS_OPENCV:
            try:
                # 转为OpenCV格式进行增强
                img_array = np.array(image)
                
                # 转灰度
                gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
                
                # 自适应阈值二值化
                binary = cv2.adaptiveThreshold(
                    gray, 255,
                    cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                    cv2.THRESH_BINARY,
                    11, 2
                )
                
                # 去噪
                denoised = cv2.fastNlMeansDenoising(binary, None, 10, 7, 21)
                
                # 转回PIL格式
                enhanced_image = Image.fromarray(denoised)
                
                return enhanced_image
            except Exception as e:
                logger.warning("OpenCV preprocessing failed; falling back to Pillow: %s", e)
        
        # 使用Pillow进行基础增强（备选方案）
        # 转灰度
        gray_image = image.convert('L')
        
        # 增强对比度
        enhancer = ImageEnhance.Contrast(gray_image)
        enhanced = enhancer.enhance(2.0)
        
        # 增强锐度
        enhancer = ImageEnhance.Sharpness(enhanced)
        enhanced = enhancer.enhance(1.5)
        
        # 二值化（简单阈值）
        threshold = 128
        enhanced = enhanced.point(lambda p: 255 if p > threshold else 0)
        
        return enhanced

    def _build_tesseract_config(self, layout_hint: Optional[str] = None) -> str:
        """为 Tesseract 生成适合不同版式的配置。"""
        if layout_hint in {'table', 'code'}:
            return '--psm 6 -c preserve_interword_spaces=1'
        if layout_hint == 'sparse':
            return '--psm 11'
        return '--psm 6'

    def _normalize_ocr_text(self, text: str, layout_hint: Optional[str] = None) -> str:
        """统一 OCR 输出的换行与空白处理。"""
        normalized = (text or '').replace('\r\n', '\n').replace('\r', '\n')
        if layout_hint in {'table', 'code'}:
            return '\n'.join(line.rstrip() for line in normalized.split('\n')).strip('\n')
        return '\n'.join(line.strip() for line in normalized.split('\n')).strip()
    
    def detect_content_type(self, image: Image.Image) -> str:
        """
        检测图片内容类型
        
        Args:
            image: PIL图片对象
            
        Returns:
            'formula' | 'text' | 'mixed'
        """
        # 快速OCR检测
        try:
            text = pytesseract.image_to_string(image, lang='eng+chi_sim')
            
            # 检测数学符号和公式特征
            math_patterns = [
                r'[\+\-\*/=<>∫∑∏√∂∇]',  # 数学运算符
                r'\\[a-zA-Z]+',  # LaTeX命令
                r'\^|\{|\}|_',  # 上下标和大括号
                r'[α-ωΑ-Ω]',  # 希腊字母
                r'\d+[a-zA-Z]+\d*'  # 数学变量
            ]
            
            math_count = sum(len(re.findall(pattern, text)) for pattern in math_patterns)
            text_length = len(text.strip())
            
            if text_length == 0:
                return 'unknown'
            
            # 判断比例
            math_ratio = math_count / max(text_length, 1)
            
            if math_ratio > 0.3:
                return 'formula'
            elif math_ratio > 0.05:
                return 'mixed'
            else:
                return 'text'
        except Exception as e:
            logger.warning("OCR content-type detection failed: %s", e)
            return 'mixed'
    
    def tesseract_ocr(
        self,
        image: Image.Image,
        lang: str = 'eng+chi_sim',
        enhance: bool = True,
        layout_hint: Optional[str] = None
    ) -> Tuple[str, float]:
        """
        使用 Tesseract 进行 OCR 识别
        
        Args:
            image: PIL图片对象
            lang: 识别语言
            enhance: 是否预处理增强
            
        Returns:
            (识别文本, 质量分数)
        """
        try:
            # 预处理
            processed_image = self.preprocess_image(image, enhance=enhance, layout_hint=layout_hint)
            config = self._build_tesseract_config(layout_hint)
            
            # OCR识别
            text = pytesseract.image_to_string(processed_image, lang=lang, config=config)
            
            # 获取置信度
            data = pytesseract.image_to_data(processed_image, lang=lang, config=config, output_type=pytesseract.Output.DICT)
            confidences = [int(conf) for conf in data['conf'] if conf != '-1']
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0
            
            quality_score = avg_confidence / 100.0
            
            return self._normalize_ocr_text(text, layout_hint=layout_hint), quality_score
            
        except Exception as e:
            logger.warning("Tesseract OCR failed: %s", e)
            return "", 0.0

    def _get_paddle_engine(self):
        """Load PaddleOCR only if a scanned page actually needs it."""
        global _paddle_engine
        if _paddle_engine is not None:
            return _paddle_engine
        with _paddle_engine_lock:
            if _paddle_engine is not None:
                return _paddle_engine
            try:
                from paddleocr import PaddleOCR
                _paddle_engine = PaddleOCR(
                    use_angle_cls=True,
                    lang=settings.PADDLEOCR_LANG,
                    use_gpu=settings.PADDLEOCR_USE_GPU,
                    show_log=False,
                )
            except Exception as exc:
                logger.warning("PaddleOCR is unavailable: %s", exc)
                raise RuntimeError("PaddleOCR 不可用，请检查 PaddleOCR/PaddlePaddle 运行环境。") from exc
        return _paddle_engine

    def paddle_ocr(
        self,
        image: Image.Image,
        layout_hint: Optional[str] = None,
    ) -> Tuple[str, float]:
        """Recognize a page with local PaddleOCR and return text plus confidence."""
        try:
            import numpy as np
            processed = self.preprocess_image(image, layout_hint=layout_hint)
            result = self._get_paddle_engine().ocr(np.array(processed), cls=True)
            lines = []
            confidences = []
            for block in result or []:
                for item in block or []:
                    if not isinstance(item, (list, tuple)) or len(item) < 2:
                        continue
                    recognition = item[1]
                    if not isinstance(recognition, (list, tuple)) or not recognition:
                        continue
                    text = str(recognition[0] or '').strip()
                    if text:
                        lines.append(text)
                    if len(recognition) > 1:
                        try:
                            confidences.append(float(recognition[1]))
                        except (TypeError, ValueError):
                            pass
            quality = sum(confidences) / len(confidences) if confidences else 0.0
            return self._normalize_ocr_text('\n'.join(lines), layout_hint=layout_hint), quality
        except Exception as exc:
            logger.warning("PaddleOCR failed: %s", exc)
            return "", 0.0
    
    def image_to_base64(self, image: Image.Image, format: str = 'PNG') -> str:
        """
        将PIL图片转换为Base64编码
        
        Args:
            image: PIL图片对象
            format: 图片格式
            
        Returns:
            Base64编码字符串
        """
        buffered = BytesIO()
        image.save(buffered, format=format)
        img_bytes = buffered.getvalue()
        img_base64 = base64.b64encode(img_bytes).decode('utf-8')
        return f"data:image/{format.lower()};base64,{img_base64}"
    
    @staticmethod
    def _estimate_vision_quality(text: str) -> float:
        """Conservative readability score; API token usage is not OCR confidence."""
        if not text or not text.strip():
            return 0.0

        compact = re.sub(r'\s+', '', text)
        length_score = min(len(compact) / 120, 1.0) * 0.25
        readable = sum(char.isalnum() or '\u4e00' <= char <= '\u9fff' for char in compact)
        score = 0.35 + length_score + min(readable / max(len(compact), 1), 0.9) * 0.35
        if re.search(r'\ufffd|\(cid:\s*\d+\)|cid:\s*\d+', text, re.IGNORECASE):
            score -= 0.30
        if re.search(r'(.)\1{5,}', compact):
            score -= 0.20
        symbol_ratio = sum(not (char.isalnum() or char.isspace()) for char in compact) / max(len(compact), 1)
        if symbol_ratio > 0.45 and not re.search(r'\\[a-zA-Z]+|\$|\\begin\{', text):
            score -= 0.20
        if re.search(r'\\[a-zA-Z]+|\$[^$]+\$', text):
            score += 0.04
        return max(0.0, min(round(score, 3), 0.92))

    async def vision_api_ocr(
        self,
        image: Image.Image,
        prompt: Optional[str] = None,
        layout_hint: Optional[str] = None
    ) -> Tuple[str, float]:
        """
        使用 Vision API 进行图片识别（GPT-4o 或 Gemini）
        
        Args:
            image: PIL图片对象
            prompt: 自定义提示词
            
        Returns:
            (识别文本, 质量分数)
        """
        if not self.has_vision_api:
            raise ValueError("Vision API 未配置（需要 OpenAI 或 Gemini API Key）")
        
        try:
            # 预处理图片（不增强，保持原样）
            processed_image = self.preprocess_image(
                image,
                enhance=False,
                layout_hint=layout_hint,
                skip_resize=True,
            )
            
            # 转换为Base64
            image_base64 = self.image_to_base64(processed_image)
            
            # 默认提示词
            if prompt is None:
                if layout_hint == 'table':
                    prompt = """你是一个表格OCR识别专家。请按单元格顺序识别图片中的内容，并尽量保持每一行对应原表格的一行。

**识别规则**：

1. 保持单元格读取顺序，从左到右、从上到下。
2. 用换行分隔每一行；同一行的单元格之间用制表符或多个空格分隔。
3. 不要解释，不要补充额外文字。
4. 如果表格中有数学表达式，仍需保留标准 LaTeX 形式。
"""
                elif layout_hint == 'code':
                    prompt = """你是一个代码块OCR识别专家。请尽量保留代码中的缩进、空格、换行和符号，不要改写代码。

**识别规则**：

1. 保留每一行的换行。
2. 保留缩进与空格，不要自动格式化。
3. 不要解释，不要补充额外文字。
4. 如果有代码注释或字符串，请原样保留。
"""
                else:
                    prompt = """你是一个专业的数学文档OCR识别专家。请精确识别图片中的所有内容。

**识别规则**：

1. **数学公式** - 必须使用标准 LaTeX 语法：
   - 行内公式：$...$
   - 独立公式：$$...$$
   - 希腊字母：\\alpha, \\beta, \\gamma, \\Delta, \\Sigma 等
   - 常用符号：\\det, \\sum, \\prod, \\int, \\lim, \\frac, \\sqrt
   - 上下标：x^{2}, a_{ij}
   - 矩阵：\\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}
   - 集合：\\in, \\subset, \\cup, \\cap
   - 关系：\\leq, \\geq, \\neq, \\approx, \\equiv

2. **文本内容**：
   - 保持原有的段落结构
   - 保留换行和空格
   - 正确识别标点符号

3. **输出要求**：
   - 只输出识别结果，不要添加任何解释
   - 确保 LaTeX 语法正确，可以直接编译
   - 数学符号必须准确（例如：det 必须写成 \\det）

**示例**：
图片：det(G) = 3
输出：$$\\det(G) = 3$$"""
            
            # OCR must transcribe evidence, not infer mathematical structure
            # from ordinary prose, page furniture, or isolated punctuation.
            prompt += "\n\nOnly mark a span as LaTeX math when the image clearly contains a mathematical expression. Do not invent display delimiters (\\[...\\], $$...$$), formulas, or page-layout commands for ordinary text."

            # 构建请求
            headers = {
                "Authorization": f"Bearer {self.vision_api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": self.vision_model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": image_base64,
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                "temperature": 0.1,
                "max_tokens": 4000
            }
            
            # 发送请求
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.vision_base_url}/chat/completions",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                
                result = response.json()
                text = result['choices'][0]['message']['content'].strip()
                
                # 改进的质量评估逻辑
                if not text:
                    quality_score = 0.0
                else:
                    # 基础分数：基于文本长度
                    if len(text) < 10:
                        quality_score = 0.6
                    elif len(text) < 50:
                        quality_score = 0.75
                    elif len(text) < 200:
                        quality_score = 0.85
                    else:
                        quality_score = 0.90
                    
                    # 加分项：包含LaTeX数学标记
                    latex_markers = ['$', '\\', '\\frac', '\\det', '\\sum', '\\int', '\\alpha', '\\beta']
                    if any(marker in text for marker in latex_markers):
                        quality_score = min(quality_score + 0.1, 1.0)
                    
                    # 减分项：包含明显的识别错误
                    # 常见OCR错误：连续的无意义字符、过多的空格等
                    if re.search(r'[^\w\s$\\{}()=+\-*/.,;:\'"<>|&%#@!?[\]]{3,}', text):
                        quality_score *= 0.8  # 检测到乱码，降低质量
                    
                    # Vision API通常质量较高，给予基础加成
                    quality_score = min(quality_score * 1.05, 1.0)
                
                normalized_text = self._normalize_ocr_text(text, layout_hint=layout_hint)
                return normalized_text, self._estimate_vision_quality(normalized_text)
                
        except Exception as e:
            logger.warning("Vision API OCR failed for model %s: %s", self.vision_model, e)
            return "", 0.0
    
    # 保留旧方法名作为别名
    async def deepseek_vision_ocr(self, image: Image.Image, prompt: Optional[str] = None) -> Tuple[str, float]:
        """DeepSeek Vision OCR（已弃用，改用通用 Vision API）"""
        return await self.vision_api_ocr(image, prompt)
    
    async def recognize(
        self,
        image: Image.Image,
        force_provider: Optional[str] = None,
        layout_hint: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        智能识别图片（混合方案）
        
        Args:
            image: PIL图片对象
            force_provider: 强制使用指定引擎 ('tesseract' | 'deepseek')
            
        Returns:
            {
                'text': str,           # 识别文本
                'quality': float,      # 质量分数 0-1
                'provider': str,       # 使用的引擎
                'content_type': str,   # 内容类型
                'confidence': float    # 置信度
            }
        """
        # Only mixed mode needs a preliminary Tesseract pass for routing.
        # A forced Paddle request should not first do duplicate OCR work.
        content_type = self.detect_content_type(image) if not force_provider and self.provider == 'mixed' else 'mixed'
        
        # 强制指定引擎
        if force_provider:
            provider = force_provider
        elif self.provider == 'tesseract':
            provider = 'tesseract'
        elif self.provider == 'vision':
            provider = 'vision'
        elif self.provider == 'paddle':
            provider = 'paddle'
        else:  # 'mixed' 混合方案
            # 根据内容类型智能选择
            if content_type == 'formula' and settings.ENABLE_VISION_OCR_FALLBACK:
                # 数学公式优先用 Vision API
                provider = 'vision' if self.has_vision_api else 'tesseract'
            else:
                # 纯文字先试 Tesseract
                provider = 'tesseract'
        
        # 执行识别
        if provider == 'tesseract':
            text, quality = self.tesseract_ocr(image, layout_hint=layout_hint)
            
            # 如果 Tesseract 质量低，降级到 Vision API
            if (
                settings.ENABLE_VISION_OCR_FALLBACK
                and quality < settings.IMAGE_QUALITY_THRESHOLD
                and self.has_vision_api
            ):
                logger.info("Tesseract quality %.2f is low; switching to Vision API model %s", quality, self.vision_model)
                text, quality = await self.vision_api_ocr(image, layout_hint=layout_hint)
                provider = 'vision'
        elif provider == 'paddle':
            text, quality = self.paddle_ocr(image, layout_hint=layout_hint)
            if not text and settings.ENABLE_PADDLEOCR_FALLBACK:
                logger.info("PaddleOCR returned no text; falling back to Tesseract")
                text, quality = self.tesseract_ocr(image, layout_hint=layout_hint)
                provider = 'tesseract'
        else:
            # 直接使用 Vision API
            if not self.has_vision_api:
                raise ValueError("Vision API 未配置，无法识别图片。请配置 OpenAI 或 Gemini API Key，或安装 Tesseract OCR")
            text, quality = await self.vision_api_ocr(image, layout_hint=layout_hint)
            provider = 'vision'
        
        return {
            'text': text,
            'quality': quality,
            'provider': provider,
            'content_type': content_type,
            'confidence': quality
        }


_ocr_client: Optional[OCRClient] = None
_ocr_client_lock = threading.Lock()



def get_ocr_client() -> OCRClient:
    """Create the OCR client only when OCR is actually requested."""
    global _ocr_client
    if _ocr_client is None:
        with _ocr_client_lock:
            if _ocr_client is None:
                _ocr_client = OCRClient()
    return _ocr_client


class _LazyOCRClient:
    def __getattr__(self, name: str):
        return getattr(get_ocr_client(), name)


# Backwards-compatible lazy proxy for existing imports.
ocr_client = _LazyOCRClient()
