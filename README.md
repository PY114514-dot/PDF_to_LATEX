# PDF2LaTeX Enhanced

<div align="center">

**一个强大的 PDF 到 LaTeX 转换工具，支持多模型、批量处理和中文翻译**

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/Flask-3.0+-green.svg)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

---

## 目录结构

```
PDF2LATEX/
├── backend/                    # Flask 后端
│   ├── app_enhanced.py        # Flask 主应用入口
│   ├── pdf2latex_enhanced.py  # 核心 PDF→LaTeX 转换逻辑
│   ├── image2latex_enhanced.py # 图片→LaTeX 流程
│   ├── document_parser.py     # PDF 文本提取（pdfplumber + PyPDF2）
│   ├── ocr_client.py          # OCR 引擎封装（Tesseract / Vision）
│   ├── clients.py             # LLM 客户端（DeepSeek / GPT / GLM / Gemini / Doubao）
│   ├── config.py              # 配置文件
│   ├── latex_utils.py        # LaTeX 清洗 / 包装 / 参考文献拆分
│   ├── latex_syntax.py       # LaTeX 语法检查、自动纠错、质量评分
│   ├── history_manager.py    # 历史记录管理
│   ├── task_manager.py       # 异步任务管理
│   ├── error_handler.py      # 错误分类、重试机制、详细错误报告
│   ├── knowledge_graph.py    # 论文结构分析、定理依赖关系
│   ├── bilingual_reader.py   # 原文/译文对照、hover显示原文
│   └── requirements.txt      # Python 依赖
│
├── frontend/                  # 前端资源
│   ├── static/
│   │   ├── script_enhanced.js  # 前端交互逻辑
│   │   └── style_enhanced.css  # 样式文件
│   └── templates/
│       ├── index_enhanced.html  # 主页面
│       ├── latex_render.html    # LaTeX 实时预览页
│       └── paper_agent_view.html # AI 学术阅读页面
│
├── uploads/                   # 上传文件临时目录（不提交到 git）
├── outputs/                  # 输出文件目录（不提交到 git）
├── .env                      # 环境变量（API 密钥等，勿提交）
├── .env_example              # 环境变量示例
├── task_plan.md              # 项目任务规划
├── progress.md               # 进度日志
├── findings.md                # 研究发现
├── PROJECT_FLOW.md           # 项目详细流程文档
└── README.md
```

---

## 快速开始

### 1. 安装依赖

```bash
cd backend
pip install -r requirements.txt
```

### 2. 配置环境变量

在项目根目录创建 `.env` 文件：

```bash
# DeepSeek（推荐，高性价比）
DEEPSEEK_API_KEY=your_deepseek_api_key

# OpenAI GPT
OPENAI_API_KEY=your_openai_api_key

# GLM（智谱清言）
ZHIPU_API_KEY=your_zhipu_api_key

# Gemini
GEMINI_API_KEY=your_gemini_api_key

# Doubao（豆包）
DOUBAO_API_KEY=your_doubao_api_key

# 默认模型（可选，默认 deepseek-chat）
DEFAULT_MODEL=deepseek-chat
```

### 3. 启动服务

```bash
# 从 backend/ 目录启动
cd backend
python app_enhanced.py
```

访问 **http://localhost:5000** 即可使用。

---

## 主要特性

### 多模型支持
| 模型 | 说明 | 特点 |
|------|------|------|
| **DeepSeek** | deepseek-chat / deepseek-reasoner | 高性价比，推荐 |
| **DeepSeek Math** | deepseek-math | 数学公式专用 |
| **GLM（智谱）** | glm-4.6 / glm-4.7 | 国产大模型，支持 Thinking 模式 |
| **Gemini** | gemini-3-pro | Google 大模型 |
| **Doubao（豆包）** | doubao-seed-2.0-lite | 字节跳动大模型 |

### 核心功能
- **智能 PDF 提取** - 文本层优先，OCR 兜底，保证文本质量
- **批量转换** - 最多同时处理 5 个 PDF 文件
- **中文翻译** - 一键将英文 PDF 翻译为中文 LaTeX
- **页码选择** - 支持 `1-3,5,7-9` 格式精确选择
- **实时进度** - WebSocket 实时推送转换进度
- **历史记录** - 保存转换历史，支持重新下载
- **表格优先还原** - 结构化表格上下文注入，优先生成完整 `tabular`
- **参考文献保护** - 自动识别文献区，翻译时保持作者名/题名/刊名原文
- **双栏版式检测** - 自动检测双栏排版页面，翻译后保留 `multicols` 结构
- **运行标题过滤** - 自动过滤页眉页脚的章节标题
- **KaTeX 兼容** - 自动转换 `\eqref` 为 `(\ref)` 确保前端渲染

### AI 学术阅读（仅 PDF）
在 PDF 转换完成后，点击结果页中的 `AI学术阅读`，调用后端生成摘要、大纲、思维导图与算法解析。

---

## 项目架构

### 后端（Flask + Python）
| 文件 | 说明 |
|------|------|
| `app_enhanced.py` | Flask 主入口，路由定义，WebSocket 进度推送 |
| `pdf2latex_enhanced.py` | PDF→LaTeX 核心流程，翻译/转换并发控制 |
| `document_parser.py` | PDF 文本提取，三级降级（pdfplumber → PyPDF2 → OCR）|
| `latex_utils.py` | LaTeX 清洗、表格修复、模板包装 |
| `latex_syntax.py` | LaTeX 语法检查、自动纠错、质量评分（多维度）|
| `clients.py` | 统一 LLM 客户端，支持多模型 |
| `ocr_client.py` | OCR 引擎封装（Tesseract / DeepSeek Vision）|
| `error_handler.py` | 错误分类、重试策略、用户友好错误消息 |
| `knowledge_graph.py` | 论文结构分析、定理依赖关系图谱 |
| `bilingual_reader.py` | 原文/译文对照，段落级对齐，hover 显示原文 |
| `task_manager.py` | 异步任务状态管理 |
| `history_manager.py` | 转换历史持久化 |

### 前端（原生 JS + CSS）
| 文件 | 说明 |
|------|------|
| `script_enhanced.js` | 前端交互、WebSocket 进度、实时预览 |
| `style_enhanced.css` | ChatGPT 风格黑白极简 UI |
| `index_enhanced.html` | 主页面 |
| `latex_render.html` | LaTeX 实时渲染预览页（KaTeX）|
| `paper_agent_view.html` | AI 学术阅读页面 |

---

## 配置说明

### 环境变量

| 变量名 | 说明 | 默认值 | 必需 |
|--------|------|--------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 | - | 否* |
| `OPENAI_API_KEY` | OpenAI API 密钥 | - | 否* |
| `ZHIPU_API_KEY` | GLM API 密钥 | - | 否* |
| `GEMINI_API_KEY` | Gemini API 密钥 | - | 否* |
| `DOUBAO_API_KEY` | Doubao API 密钥 | - | 否* |
| `DEFAULT_MODEL` | 默认模型 ID | `deepseek-chat` | 否 |

> *至少需要配置一个模型的 API 密钥

---

## 常见问题

### Q: 表格经常缺列或格式错乱？
**A:** 系统已内置行列一致性修复，缺失单元格会自动补 `--`。复杂的多行合并/跨列表格建议在 LaTeX 编辑器中手动微调。

### Q: 为什么参考文献没有翻译？
**A:** 这是默认策略。文献区通过标题识别 + 尾部引用样式启发式检测，翻译阶段默认不翻译作者名、刊名和题名，保持原文准确性。

### Q: 转换速度较慢？
**A:** 当前页面并发为 8（`max_concurrency=8`），可酌情调高。若遇 API 429 限流错误，请降低并发数。

### Q: 支持扫描版 PDF 吗？
**A:** 支持。系统会自动检测文本质量，低质量时触发 OCR（需配置 Tesseract 或使用 Vision API）。

### Q: LaTeX 公式在网页上显示不正确？
**A:** 系统会自动处理常见兼容性问题：
- `\eqref` → `(\ref)` 自动转换（KaTeX 不支持 `\eqref`）
- 矩阵转置符号修复（`W.T` → `W^{\mathsf{T}}`）
- 参考文献区保护

---

## 项目文档

- `PROJECT_FLOW.md` - 项目详细流程和技术文档
- `task_plan.md` - 项目任务规划和里程碑
- `progress.md` - 开发进度日志
- `findings.md` - 研究发现和技术决策

---

## 开源协议

MIT License

---

<div align="center">

**如果这个项目对你有帮助，请给一个 ⭐️ Star！**

</div>
