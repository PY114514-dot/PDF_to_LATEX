# PDF2LaTeX - 智能PDF转LaTeX工具

将PDF文档智能转换为LaTeX格式，支持多种AI模型、实时进度显示和在线预览。

## ✨ 主要功能

- 🤖 **多模型支持** - DeepSeek、GPT-4o、GLM、Gemini等10+模型
- 📊 **实时进度** - WebSocket实时推送转换进度和Token统计
- 🌏 **中英翻译** - 支持将英文文档翻译成中文
- 📦 **批量处理** - 一次上传多个PDF文件批量转换
- 👁️ **在线预览** - 实时渲染LaTeX数学公式和文档结构
- 💰 **成本统计** - 自动计算和显示API调用成本

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置API密钥

复制 `.env_example` 为 `.env` 并填入你的API密钥：

```bash
cp .env_example .env
```

编辑 `.env` 文件：

```env
# 至少配置一个模型的API密钥
DEEPSEEK_API_KEY=your_deepseek_key_here
OPENAI_API_KEY=your_openai_key_here
ZHIPU_API_KEY=your_zhipu_key_here
GEMINI_API_KEY=your_gemini_key_here
DOUBAO_API_KEY=your_doubao_key_here
CANOPY_WAVE_API_KEY=your_canopy_wave_key_here
```

### 3. 启动服务

```bash
python app_enhanced.py
```

### 4. 访问Web界面

打开浏览器访问：http://localhost:5000

## 📖 使用说明

### 单文件转换

1. 点击"浏览文件"或拖拽PDF文件到上传区域
2. 选择AI模型（推荐：DeepSeek Chat性价比最高）
3. 配置选项：
   - ✅ 翻译成中文（英文PDF自动翻译）
   - ✅ 添加文档结构（自动添加LaTeX文档头）
   - 📄 指定页码（可选，如：1,2,3）
4. 点击"开始转换"
5. 等待转换完成，可实时查看进度和Token使用情况
6. 下载.tex文件或在线预览

### 批量转换

1. 点击"批量选择"选择多个PDF文件（最多10个）
2. 选择相同的配置选项
3. 点击"开始转换"
4. 查看每个文件的转换进度和结果
5. 打包下载所有转换结果

## 🤖 支持的AI模型

| 模型 | 描述 | 输入价格 | 输出价格 | 推荐场景 |
|------|------|---------|---------|---------|
| DeepSeek Chat | 通用对话模型 | $1/M | $2/M | 日常转换（性价比最高）|
| DeepSeek Reasoner | 推理模型 | $1/M | $2/M | 复杂文档 |
| GPT-4o | OpenAI高性能 | $2.5/M | $10/M | 高质量要求 |
| GPT-4o Mini | OpenAI轻量级 | $0.15/M | $0.6/M | 快速处理 |
| GPT-5.2 | OpenAI推理 | $5/M | $15/M | 最强推理能力 |
| GLM-4.6 | 智谱AI | $1/M | $1/M | 中文文档优化 |
| GLM-4.7 | 智谱Thinking | $1/M | $1/M | 思维链推理 |
| Gemini 3 Pro | Google多模态 | $1.25/M | $5/M | 多模态理解 |
| 豆包 | 字节跳动 | $0.8/M | $2/M | 最低成本 |
| DeepSeek Math | 数学专用 | $1/M | $2/M | 数学论文 |

## 📁 项目结构

```
PDF2LATEX/
├── app_enhanced.py          # Flask Web服务器
├── pdf2latex_enhanced.py    # PDF转LaTeX核心逻辑
├── clients.py               # 统一的AI模型客户端
├── config.py                # 配置管理
├── requirements.txt         # Python依赖
├── .env                     # API密钥配置（需自行创建）
├── templates/               # HTML模板
│   ├── index_enhanced.html  # 主页面
│   └── latex_render.html    # LaTeX在线渲染页面
├── static/                  # 静态资源
│   ├── script_enhanced.js   # 前端JavaScript
│   └── style_enhanced.css   # 样式表
├── uploads/                 # 上传文件临时目录
└── outputs/                 # 输出文件目录
```

## ⚙️ 高级配置

### 自定义端口

编辑 `app_enhanced.py` 最后一行：

```python
socketio.run(app, debug=True, host='0.0.0.0', port=5000)  # 修改port参数
```

### 调整超时时间

编辑 `clients.py` 中对应模型的 `timeout` 参数：

```python
deepseek_chat = LLMClient(
    api_key=settings.DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1/chat/completions",
    model="deepseek-chat",
    timeout=600.0  # 修改此值（秒）
)
```

### 修改文件大小限制

编辑 `app_enhanced.py`：

```python
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB，可修改
```

## 🔧 依赖说明

主要依赖：

- `flask` - Web框架
- `flask-socketio` - WebSocket实时通信
- `flask-cors` - 跨域支持
- `PyPDF2` - PDF文本提取
- `httpx` - 异步HTTP客户端
- `python-dotenv` - 环境变量管理

## 🐛 常见问题

### Q1: 模型下拉框显示"加载中..."
**A**: 确认至少配置了一个API密钥，并重启服务器。

### Q2: 转换失败提示"不支持的模型"
**A**: 检查所选模型对应的API密钥是否已配置。

### Q3: WebSocket连接失败
**A**: 检查浏览器是否支持WebSocket，尝试刷新页面。

### Q4: 数学公式显示不正确
**A**: 确保LaTeX语法正确，复杂公式使用`$$...$$`包裹。

### Q5: 中文显示乱码
**A**: 确保PDF文件编码正确，选择"翻译成中文"选项。

## 📊 性能优化

- 使用 DeepSeek Chat 获得最佳性价比
- 批量处理时建议每次不超过5个文件
- 大文件（>10MB）建议指定页码范围
- 使用GPT-4o Mini可获得更快速度

## 🔐 安全说明

- API密钥存储在本地 `.env` 文件中，不会上传
- 上传的PDF文件在处理后自动删除
- 建议不要在公网环境直接运行

## 📄 许可证

MIT License

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📮 联系方式

如有问题或建议，请通过以下方式联系：
- 提交 GitHub Issue
- 发送邮件至项目维护者

---

**注意**: 本项目需要有效的AI模型API密钥才能使用。请确保已配置至少一个模型的API密钥。

**成本提示**: 使用AI模型转换会产生API调用费用，请根据实际需求选择合适的模型。
