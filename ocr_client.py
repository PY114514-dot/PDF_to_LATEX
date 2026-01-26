"""
OCR 客户端 - 支持多种OCR引擎
混合方案：Tesseract (本地) + DeepSeek Vision (云端)
"""

import os
import base64
import re
from io import BytesIO
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from PIL import Image, ImageEnhance, ImageFilter
import pytesseract
import httpx

from config import settings

# OpenCV 是可选的，用于高级图像处理
try:
    import cv2
    import numpy as np
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False
    print("⚠️  OpenCV 未安装，将使用 Pillow 进行图像预处理")


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
    
    def preprocess_image(self, image: Image.Image, enhance: bool = True) -> Image.Image:
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
                print(f"OpenCV 处理失败，使用 Pillow 替代: {e}")
        
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
            print(f"内容类型检测失败: {str(e)}")
            return 'mixed'
    
    def tesseract_ocr(
        self,
        image: Image.Image,
        lang: str = 'eng+chi_sim',
        enhance: bool = True
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
            processed_image = self.preprocess_image(image, enhance=enhance)
            
            # OCR识别
            text = pytesseract.image_to_string(processed_image, lang=lang)
            
            # 获取置信度
            data = pytesseract.image_to_data(processed_image, lang=lang, output_type=pytesseract.Output.DICT)
            confidences = [int(conf) for conf in data['conf'] if conf != '-1']
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0
            
            quality_score = avg_confidence / 100.0
            
            return text.strip(), quality_score
            
        except Exception as e:
            print(f"Tesseract OCR 失败: {str(e)}")
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
    
    async def vision_api_ocr(
        self,
        image: Image.Image,
        prompt: Optional[str] = None
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
            processed_image = self.preprocess_image(image, enhance=False)
            
            # 转换为Base64
            image_base64 = self.image_to_base64(processed_image)
            
            # 默认提示词
            if prompt is None:
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
                
                return text, quality_score
                
        except Exception as e:
            print(f"Vision API OCR 失败 ({self.vision_model}): {str(e)}")
            return "", 0.0
    
    # 保留旧方法名作为别名
    async def deepseek_vision_ocr(self, image: Image.Image, prompt: Optional[str] = None) -> Tuple[str, float]:
        """DeepSeek Vision OCR（已弃用，改用通用 Vision API）"""
        return await self.vision_api_ocr(image, prompt)
    
    async def recognize(
        self,
        image: Image.Image,
        force_provider: Optional[str] = None
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
        # 检测内容类型
        content_type = self.detect_content_type(image)
        
        # 强制指定引擎
        if force_provider:
            provider = force_provider
        elif self.provider == 'tesseract':
            provider = 'tesseract'
        elif self.provider == 'vision':
            provider = 'vision'
        else:  # 'mixed' 混合方案
            # 根据内容类型智能选择
            if content_type == 'formula':
                # 数学公式优先用 Vision API
                provider = 'vision' if self.has_vision_api else 'tesseract'
            else:
                # 纯文字先试 Tesseract
                provider = 'tesseract'
        
        # 执行识别
        if provider == 'tesseract':
            text, quality = self.tesseract_ocr(image)
            
            # 如果 Tesseract 质量低，降级到 Vision API
            if quality < settings.IMAGE_QUALITY_THRESHOLD and self.has_vision_api:
                print(f"Tesseract 质量较低 ({quality:.2f})，切换到 Vision API ({self.vision_model})")
                text, quality = await self.vision_api_ocr(image)
                provider = 'vision'
        else:
            # 直接使用 Vision API
            if not self.has_vision_api:
                raise ValueError("Vision API 未配置，无法识别图片。请配置 OpenAI 或 Gemini API Key，或安装 Tesseract OCR")
            text, quality = await self.vision_api_ocr(image)
            provider = 'vision'
        
        return {
            'text': text,
            'quality': quality,
            'provider': provider,
            'content_type': content_type,
            'confidence': quality
        }


# 创建全局OCR客户端实例
ocr_client = OCRClient()
