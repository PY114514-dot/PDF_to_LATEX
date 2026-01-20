# PDF2LaTeX Web应用使用指南

## 🌐 简介

这是一个基于Web的PDF转LaTeX工具，提供了友好的图形界面，支持拖拽上传PDF文件，一键转换为LaTeX格式。

## ✨ 功能特点

- 🎯 **拖拽上传** - 直接拖拽PDF文件到浏览器即可
- 🌏 **中文翻译** - 支持先翻译成中文再转换
- 📄 **页面选择** - 可以指定转换特定页面
- 💾 **一键下载** - 直接下载生成的.tex文件
- 📋 **复制代码** - 一键复制LaTeX代码到剪贴板
- 📱 **响应式设计** - 支持手机、平板、电脑访问

## 🚀 快速开始

### 方法1: 使用启动脚本（推荐）

**Windows:**
```bash
# 双击运行或在命令行执行
start_server.bat
```

**Linux/Mac:**
```bash
# 添加执行权限
chmod +x start_server.sh

# 运行
./start_server.sh
```

### 方法2: 手动启动

1. **安装依赖**
```bash
pip install flask flask-cors
```

2. **启动服务器**
```bash
python app.py
```

3. **访问Web界面**
```
打开浏览器访问: http://localhost:5000
```

## 📖 使用步骤

### 1. 上传PDF文件

**方式A: 拖拽上传**
- 将PDF文件拖拽到上传区域

**方式B: 浏览选择**
- 点击"浏览文件"按钮
- 选择要转换的PDF文件

### 2. 配置选项

- ✅ **翻译成中文**: 勾选后会先翻译再转换（费用翻倍）
- ✅ **添加文档结构**: 包含`\documentclass`等LaTeX文档框架
- 📝 **指定页码**: 输入页码（如: 1,2,3），留空则转换全部

### 3. 开始转换

- 点击"开始转换"按钮
- 等待处理完成（会显示进度）

### 4. 获取结果

转换完成后可以:
- 📥 **下载.tex文件** - 保存到本地
- 📋 **复制代码** - 直接复制到剪贴板
- 👀 **预览代码** - 在浏览器中查看

## 🏗️ 项目结构

```
PDF2LATEX/
├── app.py                 # Flask后端服务
├── pdf2latex.py          # 核心转换模块
├── templates/
│   └── index.html        # 主页面
├── static/
│   ├── style.css         # 样式文件
│   └── script.js         # 前端脚本
├── uploads/              # 临时上传目录
├── outputs/              # 输出文件目录
├── start_server.bat      # Windows启动脚本
└── start_server.sh       # Linux/Mac启动脚本
```

## ⚙️ 配置说明

### 环境变量

确保已配置DeepSeek API密钥：
```bash
# .env文件
DEEPSEEK_API_KEY=your-api-key-here
```

### 服务器配置

在`app.py`中可以修改：
- `MAX_CONTENT_LENGTH`: 最大文件大小（默认50MB）
- `host`: 监听地址（默认0.0.0.0）
- `port`: 监听端口（默认5000）

## 🔧 API接口

### POST /api/convert

转换PDF为LaTeX

**请求参数:**
- `file`: PDF文件（multipart/form-data）
- `translate`: 是否翻译（true/false）
- `add_wrapper`: 是否添加文档结构（true/false）
- `pages`: 页码（可选，如: "1,2,3"）

**响应示例:**
```json
{
    "success": true,
    "filename": "output.tex",
    "content": "\\documentclass{article}...",
    "download_url": "/api/download/output.tex"
}
```

### GET /api/download/<filename>

下载生成的LaTeX文件

### GET /api/status

检查API状态

## 📝 使用示例

### 示例1: 转换整个PDF
1. 上传PDF文件
2. 不勾选任何选项
3. 点击"开始转换"

### 示例2: 翻译并转换
1. 上传PDF文件
2. ✅ 勾选"翻译成中文"
3. 点击"开始转换"

### 示例3: 只转换前3页
1. 上传PDF文件
2. 在"指定页码"输入: `1,2,3`
3. 点击"开始转换"

## ⚠️ 注意事项

1. **文件大小限制**: 最大支持50MB的PDF文件
2. **API费用**: 使用翻译功能会调用两次API，费用约为普通转换的2倍
3. **网络要求**: 需要能访问DeepSeek API
4. **浏览器兼容**: 推荐使用Chrome、Firefox、Edge等现代浏览器
5. **临时文件**: 上传的PDF会在处理后自动删除

## 🐛 常见问题

### Q: 服务器无法启动

**A:** 
- 检查5000端口是否被占用
- 确保已安装Flask: `pip install flask flask-cors`
- 检查Python版本（需要3.7+）

### Q: 上传文件失败

**A:**
- 确认文件是PDF格式
- 检查文件大小是否超过50MB
- 查看浏览器控制台错误信息

### Q: 转换一直卡住

**A:**
- 检查.env文件中的API密钥是否正确
- 确认网络可以访问DeepSeek API
- 查看服务器终端的错误信息

### Q: 如何在局域网访问

**A:**
修改`app.py`最后一行：
```python
app.run(debug=True, host='0.0.0.0', port=5000)
```
然后通过`http://你的IP:5000`访问

## 🔒 安全建议

如果部署到公网，建议：
1. 添加用户认证
2. 限制上传频率
3. 定期清理临时文件
4. 使用HTTPS
5. 添加文件类型验证

## 📊 性能优化

- 小文件（<5页）: 约10-30秒
- 中等文件（5-20页）: 约30秒-2分钟
- 大文件（20+页）: 2分钟以上

建议：
- 先测试单页转换效果
- 大文件分批转换
- 使用页码选项只转换需要的部分

## 🎨 界面截图

访问 http://localhost:5000 后可以看到：
- 🎨 现代化的渐变背景
- 📤 直观的拖拽上传区域
- ⚙️ 清晰的选项配置
- 📊 实时的转换进度
- 💻 代码预览和下载功能

## 🆕 更新日志

### v1.0.0 (2026-01-20)
- ✨ 首次发布Web版本
- 🎯 支持拖拽上传
- 🌏 集成翻译功能
- 💾 支持文件下载和代码复制
- 📱 响应式设计

## 📄 许可证

MIT License

## 🤝 贡献

欢迎提交Issue和Pull Request！
