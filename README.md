# 📄 PDF2LaTeX Enhanced

<div align="center">

**一个强大的 PDF 到 LaTeX 转换工具，支持多模型、批量处理和中文翻译**

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/Flask-3.0+-green.svg)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

---

## ✨ 主要特性

### 🤖 多模型支持
- **DeepSeek** - 高性价比，推荐使用
- **OpenAI GPT-4o** - 高质量转换
- **GLM (智谱清言)** - 国产大模型
- **Gemini** - Google 大模型
- **Doubao (豆包)** - 字节跳动大模型

### 🚀 核心功能
- ✅ **智能PDF提取** - 多种提取方法自动降级，保证文本质量
- ✅ **批量转换** - 支持同时处理多个PDF文件（最多10个）
- ✅ **中文翻译** - 一键将英文PDF翻译为中文LaTeX
- ✅ **页码选择** - 灵活的页码范围选择（如：`1-3,5,7-9`）
- ✅ **实时进度** - WebSocket实时显示转换进度和页码
- ✅ **历史记录** - 自动保存转换历史，支持重新下载
- ✅ **成本显示** - 实时显示人民币成本（1 USD = 7.2 CNY）

### 💡 智能特性
- 📊 **自动检测页数** - 上传后自动显示PDF总页数
- 🎯 **智能质量检测** - 自动评估提取文本质量
- 🔄 **自动降级机制** - pdfplumber → pdfminer.six → PyPDF2
- 📈 **实时统计** - Token使用量、处理时间、成本估算
- 🌐 **现代化UI** - 响应式设计，支持移动端

---

## 🎯 快速开始

### 1️⃣ 安装依赖

```bash
# 克隆项目
git clone <your-repo-url>
cd PDF2LATEX

# 安装Python依赖
pip install -r requirements.txt
```

### 2️⃣ 配置环境变量

创建 `.env` 文件并配置API密钥：

```bash
# DeepSeek (推荐)
DEEPSEEK_API_KEY=your_deepseek_api_key

# OpenAI
OPENAI_API_KEY=your_openai_api_key

# GLM (智谱清言)
GLM_API_KEY=your_glm_api_key

# Gemini
GEMINI_API_KEY=your_gemini_api_key

# Doubao (豆包)
DOUBAO_API_KEY=your_doubao_api_key

# 汇率设置（可选，默认7.2）
USD_TO_CNY_RATE=7.2
```

### 3️⃣ 启动服务

```bash
python app_enhanced.py
```

访问 **http://localhost:5000** 即可使用！

---

## 📖 使用指南

### 单文件转换

1. **上传PDF** - 拖拽或点击选择PDF文件
2. **自动检测** - 系统自动显示PDF总页数
3. **选择页码** - 可选择全部或指定页码（如：`1-3,5,7-9`）
4. **选择模型** - 从下拉列表选择LLM模型
5. **选择选项**
   - ✅ 翻译为中文
   - ✅ 添加文档结构
6. **开始转换** - 实时查看进度和页码
7. **下载结果** - 转换完成后下载LaTeX文件

### 批量转换

1. **点击批量转换** - 切换到批量模式
2. **选择多个文件** - 最多10个PDF文件
3. **配置选项** - 统一应用于所有文件
4. **开始转换** - 实时查看每个文件的进度
5. **下载压缩包** - 所有文件打包为ZIP下载

### 页码选择示例

```bash
# 单页
1

# 连续页
1-5

# 不连续页
1,3,5

# 混合格式
1-3,5,7-9

# 自动检测
系统会显示 "例如: 1-3,5,7-9 (共10页)"
```

---

## 📊 功能展示

### 实时进度显示

```
⚙️ 正在翻译第 3/8 页...
━━━━━━━━━━━━━━━━━━ 38%

┌──────────────┐
│  第 3/8 页   │  ← 实时更新，大字体高亮
└──────────────┘
```

### 转换统计

```
📊 转换统计
┌────────────────┬──────────────┐
│ 📄 处理页数    │ 8 / 10       │
│ 🔤 总 Tokens   │ 15,234       │
│ 💰 估算成本    │ ¥0.54        │  ← 人民币显示
│ ⏱️ 处理时间    │ 45s          │
└────────────────┴──────────────┘
```

### 历史记录

```
📄 example.pdf
🤖 deepseek-chat | 🌏 翻译: 是 | 📄 1-5 页
💰 ¥0.54 | 🔢 1,234 tokens | ⏰ 2026-01-22 15:30
```

---

## 🛠️ 技术架构

### 后端
- **Flask** - Web框架
- **Flask-SocketIO** - WebSocket实时通信
- **pdfplumber** - 主要PDF提取引擎
- **pdfminer.six** - 备用PDF提取引擎
- **PyPDF2** - 降级PDF提取引擎

### 前端
- **原生JavaScript** - 无框架依赖
- **WebSocket** - 实时进度更新
- **现代CSS** - 渐变、动画、响应式

### LLM集成
- **统一客户端接口** - 支持多种LLM API
- **智能重试机制** - 自动处理临时失败
- **成本跟踪** - 实时计算Token和成本

---

## 📁 项目结构

```
PDF2LATEX/
├── app_enhanced.py          # Flask主应用
├── pdf2latex_enhanced.py    # 核心转换逻辑
├── clients.py               # LLM客户端
├── config.py                # 配置文件
├── history_manager.py       # 历史记录管理
├── requirements.txt         # Python依赖
│
├── static/                  # 静态资源
│   ├── script_enhanced.js   # 前端逻辑
│   └── style_enhanced.css   # 样式文件
│
├── templates/               # HTML模板
│   ├── index_enhanced.html  # 主页面
│   └── latex_render.html    # LaTeX预览
│
├── uploads/                 # 上传临时目录
├── outputs/                 # 输出文件目录
└── README.md               # 项目文档
```

---

## ⚙️ 配置说明

### 环境变量 (`.env`)

| 变量名 | 说明 | 默认值 | 必需 |
|--------|------|--------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API密钥 | - | 否* |
| `OPENAI_API_KEY` | OpenAI API密钥 | - | 否* |
| `GLM_API_KEY` | GLM API密钥 | - | 否* |
| `GEMINI_API_KEY` | Gemini API密钥 | - | 否* |
| `DOUBAO_API_KEY` | Doubao API密钥 | - | 否* |
| `USD_TO_CNY_RATE` | 美元兑人民币汇率 | 7.2 | 否 |

> *注：至少需要配置一个模型的API密钥

### 修改汇率

在 `config.py` 中修改：

```python
USD_TO_CNY_RATE: float = 7.3  # 修改为当前汇率
```

或在前端 `script_enhanced.js` 中修改：

```javascript
const USD_TO_CNY_RATE = 7.3;  // 修改为当前汇率
```

---

## 🔧 PDF提取优化

### 三级降级机制

1. **pdfplumber** (优先)
   - 最准确的文本提取
   - 支持复杂布局
   - 表格和图表处理

2. **pdfminer.six** (备用)
   - 处理特殊编码
   - 扫描件OCR结果
   - 复杂格式文档

3. **PyPDF2** (降级)
   - 基础文本提取
   - 简单PDF文档
   - 最后的备选方案

### 质量检测指标

- 字符密度检测
- 特殊字符比例
- 重复字符检测
- 空白内容过滤

---

## 💰 成本估算

### 主流模型价格对比

| 模型 | Input | Output | 转换10页成本 |
|------|-------|--------|--------------|
| DeepSeek-Chat | ¥0.001/1K | ¥0.002/1K | ~¥0.03 |
| GPT-4o | ¥0.036/1K | ¥0.108/1K | ~¥1.44 |
| GLM-4 | ¥0.072/1K | ¥0.072/1K | ~¥1.44 |
| Gemini Pro | ¥0.001/1K | ¥0.002/1K | ~¥0.03 |

> 注：实际成本取决于PDF内容复杂度

---

## 🐛 常见问题

### Q1: 上传后没有显示页数？

**解决方法**:
1. 检查PDF文件是否损坏
2. 按 `F12` 查看浏览器Console错误
3. 检查服务器日志

### Q2: 转换后乱码或质量差？

**解决方法**:
1. 系统会自动尝试三种提取方法
2. 检查PDF是否为扫描件（需要OCR）
3. 尝试使用不同的模型

### Q3: WebSocket连接失败？

**解决方法**:
1. 检查防火墙设置
2. 确认5000端口未被占用
3. 尝试使用 `http://127.0.0.1:5000`

### Q4: 批量转换失败？

**解决方法**:
1. 单个文件不超过50MB
2. 批量最多10个文件
3. 确保所有文件都是PDF格式

### Q5: 成本显示不准确？

**解决方法**:
1. 更新 `USD_TO_CNY_RATE` 汇率
2. 检查模型定价配置
3. 成本为估算值，仅供参考

---

## 🚀 性能优化建议

### 服务器端
- 使用 `gunicorn` 部署生产环境
- 配置 Nginx 反向代理
- 启用 Redis 缓存历史记录

### 客户端
- 现代浏览器（Chrome 90+, Edge 90+）
- 稳定的网络连接
- 关闭浏览器跟踪保护

---

## 📝 开发计划

- [ ] OCR支持（扫描PDF）
- [ ] LaTeX在线预览优化
- [ ] 用户账户系统
- [ ] 云存储集成
- [ ] Docker容器化部署
- [ ] API接口开放

---

## 🤝 贡献指南

欢迎提交Issue和Pull Request！

1. Fork项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启Pull Request

---

## 📄 开源协议

本项目采用 **MIT License** 开源协议。

---

## 🙏 致谢

- [Flask](https://flask.palletsprojects.com/) - Web框架
- [pdfplumber](https://github.com/jsvine/pdfplumber) - PDF提取
- [OpenAI](https://openai.com/) - GPT模型
- [DeepSeek](https://www.deepseek.com/) - DeepSeek模型
- [智谱AI](https://www.zhipuai.cn/) - GLM模型

---

## 📧 联系方式

- 项目主页: [GitHub Repository](https://github.com/yourusername/PDF2LATEX)
- 问题反馈: [Issues](https://github.com/yourusername/PDF2LATEX/issues)

---

<div align="center">

**如果这个项目对你有帮助，请给一个 ⭐️ Star！**

Made with ❤️ by PDF2LaTeX Team

</div>
