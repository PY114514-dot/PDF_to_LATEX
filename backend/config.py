"""
配置文件 - 所有API密钥和设置
"""
import os
import json
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

    # DeepSeek V4 Pro 的实际部署名称。不同 API 网关可在 .env 中覆盖此值。
    DEEPSEEK_V4_PRO_MODEL: str = os.getenv("DEEPSEEK_V4_PRO_MODEL", "deepseek-v4-pro")
    
    # 超时设置
    DEFAULT_TIMEOUT: float = float(os.getenv("DEFAULT_TIMEOUT", "600.0"))

    # Global LLM request guardrails for shared API keys during batch work.
    LLM_REQUESTS_PER_MINUTE: int = int(os.getenv("LLM_REQUESTS_PER_MINUTE", "30"))
    LLM_MAX_CONCURRENT_REQUESTS: int = int(os.getenv("LLM_MAX_CONCURRENT_REQUESTS", "4"))
    LLM_CONVERSION_CONCURRENCY: int = int(os.getenv("LLM_CONVERSION_CONCURRENCY", "6"))

    # Cost prices are deliberately supplied by deployment configuration rather
    # than hard-coded: gateways and model revisions can bill differently.
    # Example: {"deepseek_v4_flash":{"input_per_million":1.0,"output_per_million":2.0}}
    LLM_COST_CURRENCY: str = os.getenv("LLM_COST_CURRENCY", "CNY").upper()
    try:
        LLM_PRICING: dict = json.loads(os.getenv("LLM_PRICING_JSON", "{}"))
    except json.JSONDecodeError:
        LLM_PRICING = {}
    
    # 上传文件大小限制（MB）
    MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
    
    # 批量处理文件数量限制
    MAX_BATCH_FILES: int = int(os.getenv("MAX_BATCH_FILES", "10"))

    # Web server defaults are intentionally local-only.  LAN deployment must
    # opt in explicitly through .env after configuring an access boundary.
    APP_HOST: str = os.getenv("APP_HOST", "127.0.0.1")
    APP_DEBUG: bool = os.getenv("APP_DEBUG", "false").lower() == "true"
    CORS_ORIGINS: list = [
        origin.strip() for origin in os.getenv(
            "CORS_ORIGINS", "http://127.0.0.1:5000,http://localhost:5000"
        ).split(",") if origin.strip()
    ]

    # Persistent async task history is bounded independently from in-memory
    # progress state so task_store.json cannot grow forever.
    TASK_STORE_TTL_SECONDS: int = int(os.getenv("TASK_STORE_TTL_SECONDS", "604800"))
    MAX_PERSISTED_TASKS: int = int(os.getenv("MAX_PERSISTED_TASKS", "200"))

    # ==================== 缓存设置 ====================

    # 是否启用转换结果缓存
    ENABLE_CACHE: bool = os.getenv("ENABLE_CACHE", "true").lower() == "true"

    # 缓存目录
    CACHE_DIR: str = os.getenv("CACHE_DIR", "cache/convert")

    # 缓存过期时间（秒），默认 7 天
    CACHE_EXPIRY_SECONDS: int = int(os.getenv("CACHE_EXPIRY_SECONDS", "604800"))

    # ==================== v0.9 章节感知设置 ====================

    # 是否启用按章节切分（关闭则回退到固定4页块）
    ENABLE_CHAPTER_AWARE: bool = os.getenv("ENABLE_CHAPTER_AWARE", "true").lower() == "true"

    # 单个章节块最多包含的页数（防止token超限）
    MAX_PAGES_PER_CHAPTER: int = int(os.getenv("MAX_PAGES_PER_CHAPTER", "8"))

    # 是否对困难页（公式/表格/图像密集）做双次翻译+LLM评分；成本较高，默认关闭
    ENABLE_DIFFICULT_DOUBLE_TRANSLATE: bool = os.getenv("ENABLE_DIFFICULT_DOUBLE_TRANSLATE", "false").lower() == "true"

    # 标准模式是否使用本地规则转换 LaTeX，避免每页调用大模型
    ENABLE_LOCAL_LATEX_CONVERSION: bool = os.getenv("ENABLE_LOCAL_LATEX_CONVERSION", "true").lower() == "true"

    # 标准模式下，当页面公式行占比达到此阈值时，改用 LLM 转换该页。
    LOCAL_MATH_DENSITY_THRESHOLD: float = float(os.getenv("LOCAL_MATH_DENSITY_THRESHOLD", "0.20"))

    # ==================== OCR 和图片识别设置 ====================
    
    # OCR 引擎选择: 'mixed' | 'vision' | 'tesseract' | 'paddle'；默认本地优先，降低云端成本
    # Supported values: mixed | vision | tesseract | paddle | pix2text.
    # Pix2Text is opt-in: normal born-digital text PDFs keep the lightweight path.
    OCR_PROVIDER: str = os.getenv("OCR_PROVIDER", "tesseract")

    # Tesseract 低质量时是否自动回退到 Vision API；成本较高，默认关闭
    ENABLE_VISION_OCR_FALLBACK: bool = os.getenv("ENABLE_VISION_OCR_FALLBACK", "false").lower() == "true"

    # PaddleOCR is loaded lazily because its model runtime is comparatively
    # heavy.  It is used for scanned/low-quality pages, not ordinary text PDFs.
    PADDLEOCR_LANG: str = os.getenv("PADDLEOCR_LANG", "ch")
    PADDLEOCR_USE_GPU: bool = os.getenv("PADDLEOCR_USE_GPU", "false").lower() == "true"
    ENABLE_PADDLEOCR_FALLBACK: bool = os.getenv("ENABLE_PADDLEOCR_FALLBACK", "true").lower() == "true"

    # Optional formula/mixed-layout provider.  In mixed mode, route only pages
    # classified as formula or mixed; missing runtime falls back locally.
    ENABLE_PIX2TEXT_FORMULA_ROUTING: bool = os.getenv("ENABLE_PIX2TEXT_FORMULA_ROUTING", "false").lower() == "true"
    ENABLE_PIX2TEXT_PADDLE_FALLBACK: bool = os.getenv("ENABLE_PIX2TEXT_PADDLE_FALLBACK", "true").lower() == "true"
    
    # Tesseract 可执行文件路径（Windows需要配置）
    TESSERACT_CMD: str = os.getenv("TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe")

    # 图片预处理设置
    IMAGE_MAX_SIZE: int = int(os.getenv("IMAGE_MAX_SIZE", "4096"))  # 最大边长
    IMAGE_QUALITY_THRESHOLD: float = float(os.getenv("IMAGE_QUALITY_THRESHOLD", "0.6"))  # OCR质量阈值（Tesseract低于此值会切换到Vision API）

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
            available.append({
                'id': 'deepseek_v4_pro',
                'name': 'DeepSeek V4 Pro',
                'description': '更高质量，适合复杂公式、表格和困难页面'
            })

        return available

# 创建全局配置实例
settings = Settings()
