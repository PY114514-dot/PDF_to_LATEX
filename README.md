# PDF2LaTeX Enhanced

一个 Flask + 原生前端的 PDF 到 LaTeX 转换工作台，支持单文件转换、批量 PDF 转换、中文翻译、页码选择、实时进度、历史记录和在线预览。

## 当前可用能力

- PDF 转 LaTeX：上传 PDF 后生成 `.tex` 文件。
- 批量 PDF：最多同时选择 5 个 PDF 文件。
- 中文翻译：可选择将英文 PDF 翻译为中文 LaTeX。
- 页码选择：支持 `1-3,5,7-9` 这样的页码范围。
- 异步任务：长任务可进入任务中心并尝试恢复。
- 实时进度：通过 Socket.IO 推送阶段进度和处理日志。
- LaTeX 预览：结果页内置源码编辑与 KaTeX 预览。
- 历史记录：可查看、下载或清空转换历史。

> 说明：当前主应用没有接通 Word 转换和图片转 LaTeX 路由，前端已隐藏这些入口，避免用户进入不可用流程。

## 目录结构

```text
PDF2LATEX/
├── backend/
│   ├── app_enhanced.py        # Flask 主应用入口与 API 路由
│   ├── pdf2latex_enhanced.py  # PDF 到 LaTeX 核心流程
│   ├── document_parser.py     # PDF 文本提取与 OCR 降级
│   ├── ocr_client.py          # OCR 引擎封装
│   ├── clients.py             # LLM 客户端封装
│   ├── config.py              # 环境变量与运行配置
│   ├── latex_utils.py         # LaTeX 清洗、包装与合并
│   ├── latex_syntax.py        # LaTeX 语法检查、修复与质量评分
│   ├── history_manager.py     # 历史记录管理
│   ├── task_manager.py        # 异步任务状态管理
│   ├── error_handler.py       # 错误分类与报告
│   └── requirements.txt
├── frontend/
│   ├── static/
│   │   ├── script_enhanced.js
│   │   └── style_enhanced.css
│   └── templates/
│       ├── index_enhanced.html
│       └── latex_render.html
├── .codex/                   # Harness Engineering：项目护栏与工程记忆
│   ├── rules.md               # 不变量、敏感信息与修改边界
│   ├── architecture.md        # 转换链路与跨层约束
│   ├── workflow.md            # Agent 标准工作流
│   ├── testing.md             # 验证规范
│   └── mistakes.md            # 已知问题与处理经验
├── scripts/
│   └── verify_harness.ps1     # 一键基线验证
├── tests/                     # 集成/流程测试
├── backend/tests/             # 后端单元测试
├── uploads/                   # 上传文件临时目录，已 gitignore
├── outputs/                   # 生成结果目录，已 gitignore
├── cache/                     # 转换缓存，已 gitignore
└── logs/                      # 运行日志，已 gitignore
```

## 快速开始

```bash
cd backend
pip install -r requirements.txt
python app_enhanced.py
```

然后访问 `http://localhost:5000`。

## 环境变量

在项目根目录创建 `.env`：

```env
DEEPSEEK_API_KEY=your_deepseek_api_key
OPENAI_API_KEY=your_openai_api_key
ZHIPU_API_KEY=your_zhipu_api_key
GEMINI_API_KEY=your_gemini_api_key
DOUBAO_API_KEY=your_doubao_api_key
DEFAULT_MODEL=deepseek_v4_flash
# 可选：DeepSeek V4 Pro 的实际模型/部署名称
DEEPSEEK_V4_PRO_MODEL=deepseek-v4-pro
ENABLE_LOCAL_LATEX_CONVERSION=true
# 公式行占比达到 20% 的页面自动调用 LLM，其余页面保留本地转换
LOCAL_MATH_DENSITY_THRESHOLD=0.20
ENABLE_DIFFICULT_DOUBLE_TRANSLATE=false
OCR_PROVIDER=tesseract
ENABLE_VISION_OCR_FALLBACK=false
# 扫描页或低质量文本页使用本地 PaddleOCR（需要安装匹配平台的 PaddlePaddle）
OCR_PROVIDER=paddle
PADDLEOCR_LANG=ch
PADDLEOCR_USE_GPU=false
ENABLE_PADDLEOCR_FALLBACK=true
# 可选：费用以当前 API 网关的实际报价为准；未配置时前端会显示“未配置”
LLM_COST_CURRENCY=CNY
LLM_PRICING_JSON={"deepseek_v4_flash":{"input_per_million":1.0,"output_per_million":2.0},"deepseek_v4_pro":{"input_per_million":2.0,"output_per_million":4.0}}
```

至少配置一个可用模型密钥。当前 `config.py` 默认优先暴露 DeepSeek V4 Flash。
`LLM_PRICING_JSON` 中的单价单位为“每百万 Token”，示例数值仅展示格式；请替换为当前 API 网关的实际价格。
PaddleOCR 的 Codex MCP 仅供 Codex 开发环境调用；项目运行时使用的是 Python `paddleocr` provider，仍需在运行服务器安装匹配 CPU/GPU 的 PaddlePaddle。

## 常用命令

```bash
# 运行后端测试
pytest backend/tests

# 运行项目级测试
pytest tests

# 启动服务
python backend/app_enhanced.py

# Harness Engineering 一键验证（推荐，固定使用项目 .venv）
.\scripts\verify_harness.ps1
```

## Harness Engineering

项目通过 `.codex/` 固化开发规则、架构边界、验证要求和已知问题，避免 AI 或人工
修改跨层堆叠、绕过页级校验或泄露敏感信息。进行功能开发时应先阅读
`AGENTS.md`、`docs/DEVELOPMENT_GUIDE.md` 与 `.codex/` 中相应文档。

提交前运行 `.\scripts\verify_harness.ps1`。该命令会使用项目虚拟环境运行
`backend/tests`，并在本机存在 Node.js 时检查前端脚本语法。

## 可删除的本地生成内容

以下目录或文件属于运行时产物，可按需清理，不影响源码：

- `.pytest_cache/`
- `backend/.pytest_cache/`
- `__pycache__/`
- `cache/convert/`
- `logs/*.log`
- `uploads/*`
- `outputs/*`

如果需要保留历史转换结果，不要清理 `outputs/`；如果需要保留可恢复任务，不要清理 `uploads/` 和 `task_store.json`。
