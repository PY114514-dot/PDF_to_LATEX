"""
配置文件 - 所有API密钥和设置
"""
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

class Settings:
    """应用配置"""
    
    # ==================== API密钥 ====================
    
    # DeepSeek
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    
    # 豆包（字节跳动）
    DOUBAO_API_KEY: str = os.getenv("DOUBAO_API_KEY", "")
    
    # OpenAI (GPT-4, GPT-5.2)
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    
    # 智谱 GLM（兼容旧变量名 GLM_API_KEY）
    ZHIPU_API_KEY: str = os.getenv("ZHIPU_API_KEY", os.getenv("GLM_API_KEY", ""))
    
    # Google Gemini
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    
    # Canopy Wave (DeepSeek-Math)
    CANOPY_WAVE_API_KEY: str = os.getenv("CANOPY_WAVE_API_KEY", "")
    
    # ==================== 应用设置 ====================
    
    # 默认模型（应为前后端统一的模型ID）
    DEFAULT_MODEL: str = os.getenv("DEFAULT_MODEL", "deepseek_v4_flash")
    
    # 超时设置
    DEFAULT_TIMEOUT: float = float(os.getenv("DEFAULT_TIMEOUT", "600.0"))
    
    # 上传文件大小限制（MB）
    MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
    
    # 批量处理文件数量限制
    MAX_BATCH_FILES: int = int(os.getenv("MAX_BATCH_FILES", "10"))

    # ==================== 缓存设置 ====================

    # 是否启用转换结果缓存
    ENABLE_CACHE: bool = os.getenv("ENABLE_CACHE", "true").lower() == "true"

    # 缓存目录
    CACHE_DIR: str = os.getenv("CACHE_DIR", "cache/convert")

    # 缓存过期时间（秒），默认 7 天
    CACHE_EXPIRY_SECONDS: int = int(os.getenv("CACHE_EXPIRY_SECONDS", "604800"))

    # ==================== OCR 和图片识别设置 ====================
    
    # OCR 引擎选择: 'mixed' | 'deepseek' | 'tesseract'
    OCR_PROVIDER: str = os.getenv("OCR_PROVIDER", "mixed")
    
    # Tesseract 可执行文件路径（Windows需要配置）
    TESSERACT_CMD: str = os.getenv("TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    
    # 允许的图片格式
    ALLOWED_IMAGE_EXTENSIONS: set = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff', '.gif'}
    
    # 图片预处理设置
    IMAGE_MAX_SIZE: int = int(os.getenv("IMAGE_MAX_SIZE", "4096"))  # 最大边长
    IMAGE_QUALITY_THRESHOLD: float = float(os.getenv("IMAGE_QUALITY_THRESHOLD", "0.6"))  # OCR质量阈值（Tesseract低于此值会切换到Vision API）
    
    # DeepSeek Vision 模型配置
    DEEPSEEK_VISION_MODEL: str = "deepseek-chat"  # DeepSeek 支持视觉的模型
    DEEPSEEK_VISION_DETAIL: str = "high"  # 图片分析详细度: 'low' | 'high' | 'auto'
    
    @classmethod
    def validate(cls) -> bool:
        """验证至少有一个API密钥被配置"""
        keys = [
            cls.DEEPSEEK_API_KEY,
            cls.DOUBAO_API_KEY,
            cls.OPENAI_API_KEY,
            cls.ZHIPU_API_KEY,
            cls.GEMINI_API_KEY,
            cls.CANOPY_WAVE_API_KEY
        ]
        return any(key.strip() for key in keys)
    
    @classmethod
    def get_available_models(cls) -> list:
        """获取已配置的可用模型列表"""
        available = []

        if cls.DEEPSEEK_API_KEY:
            available.append({
                'id': 'deepseek_v4_flash',
                'name': 'DeepSeek V4 Flash',
                'description': 'DeepSeek V4 Flash 最新模型'
            })

        return available

# 创建全局配置实例
settings = Settings()
