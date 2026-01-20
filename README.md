# PDF to LaTeX 转换工具

这是一个使用 DeepSeek API 将 PDF 文档转换为 LaTeX 格式的工具。该工具能够智能识别文档结构、数学公式、表格等内容，并生成规范的 LaTeX 代码。

## 功能特点

- ✅ 自动提取 PDF 文本内容
- ✅ 智能识别数学公式和符号
- ✅ 保持文档结构（标题、段落、列表等）
- ✅ **🆕 支持中文翻译功能** - 先翻译成中文再转LaTeX
- ✅ 支持批量转换或指定页面转换
- ✅ 使用 DeepSeek API 进行高质量转换
- ✅ 生成可编译的 LaTeX 文档
- ✅ 带进度条显示转换进度

## 安装

### 1. 克隆或下载项目

```bash
cd PDF2LATEX
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置 API 密钥

创建 `.env` 文件并添加你的 DeepSeek API 密钥：

```bash
cp .env.example .env
```

然后编辑 `.env` 文件，填入你的 API 密钥：

```
DEEPSEEK_API_KEY=your-actual-api-key
```

> 获取 API 密钥：访问 [DeepSeek 平台](https://platform.deepseek.com/) 注册并获取

## 使用方法

### 方式一：直接转换（不翻译）

转换整个 PDF 文件：

```bash
python pdf2latex.py input.pdf
```

### 方式二：翻译转换 🆕

**先翻译成中文，再转换为LaTeX：**

```bash
# 翻译整个PDF
python pdf2latex.py input.pdf --translate

# 使用专用脚本（更简洁）
python pdf2latex_translate.py input.pdf

# 只翻译前3页
python pdf2latex_translate.py input.pdf -p 1 2 3

# 批量翻译当前目录所有PDF
python pdf2latex_translate.py --batch
```

### 其他选项

**指定输出文件：**

```bash
python pdf2latex.py input.pdf -o output.tex
```

**只转换特定页面：**

转换第 1、2、3 页（页码从 1 开始）：

```bash
python pdf2latex.py input.pdf -p 1 2 3
```

**不添加文档结构：**

如果只需要内容部分，不需要完整的 LaTeX 文档结构：

```bash
python pdf2latex.py input.pdf --no-wrapper
```

**命令行指定 API 密钥：**

```bash
python pdf2latex.py input.pdf --api-key your-api-key
```

### 完整参数说明

**pdf2latex.py 参数：**

```
positional arguments:
  pdf_file              输入的PDF文件路径

optional arguments:
  -h, --help            显示帮助信息
  -o, --output OUTPUT   输出的LaTeX文件路径（默认：与PDF同名的.tex文件）
  -p, --pages PAGES     要转换的页码（从1开始，可指定多个）
  --no-wrapper          不添加LaTeX文档结构（\documentclass, \begin{document}等）
  --translate           先翻译成中文再转换为LaTeX 🆕
  --api-key API_KEY     DeepSeek API密钥（也可通过DEEPSEEK_API_KEY环境变量设置）
  --model MODEL         使用的模型（默认：deepseek-chat）
```

**pdf2latex_translate.py 参数：**

```
positional arguments:
  pdf_file              输入的PDF文件路径

optional arguments:
  -h, --help            显示帮助信息
  -o, --output OUTPUT   输出的LaTeX文件路径（默认：与PDF同名加_cn后缀）
  -p, --pages PAGES     要翻译转换的页码（从1开始，可指定多个）
  --no-wrapper          不添加LaTeX文档结构
  --batch               批量翻译当前目录所有PDF文件
  --api-key API_KEY     DeepSeek API密钥
  --model MODEL         使用的模型（默认：deepseek-chat）
```

## 在代码中使用

你也可以在 Python 代码中导入使用：

```python
from pdf2latex import PDF2LaTeX

# 创建转换器
converter = PDF2LaTeX(api_key="your-api-key")

# 转换整个PDF
output_path = converter.convert_pdf("input.pdf")

# 翻译并转换 🆕
output_path = converter.convert_pdf(
    pdf_path="input.pdf",
    translate=True  # 启用翻译
)

# 只转换特定页面（页码从0开始）
output_path = converter.convert_pdf(
    pdf_path="input.pdf",
    output_path="output.tex",
    pages=[0, 1, 2],  # 转换前3页
    add_document_wrapper=True,
    translate=False  # 不翻译
)
```

## 示例

### 示例 1: 转换数学论文（保持英文）

```bash
python pdf2latex.py math_paper.pdf -o math_paper.tex
```

### 示例 2: 翻译数学论文成中文 🆕

```bash
python pdf2latex_translate.py math_paper.pdf
# 或
python pdf2latex.py math_paper.pdf --translate
```

### 示例 3: 只转换前 5 页

```bash
python pdf2latex.py large_document.pdf -p 1 2 3 4 5 -o preview.tex
```

### 示例 4: 批量转换（使用脚本）

```bash
# 批量转换（不翻译）
python batch_convert.py

# 批量翻译转换 🆕
python pdf2latex_translate.py --batch
```

## 注意事项

1. **API 费用**: DeepSeek API 按使用量收费，翻译功能会调用两次API（翻译+转换），请注意控制成本
2. **PDF 质量**: PDF 的文本提取质量会影响转换效果，扫描版 PDF 效果较差
3. **中文支持**: 使用翻译功能时，生成的LaTeX需要用XeLaTeX编译，并确保系统有中文字体
4. **复杂格式**: 对于复杂的表格、图像等内容，可能需要手动调整
5. **编译**: 生成的 LaTeX 文件可能需要安装相应的宏包才能编译
6. **检查输出**: 建议转换后检查并适当调整生成的 LaTeX 代码
7. **翻译质量**: 数学公式和专业术语的翻译质量取决于AI模型的理解能力

## 依赖项

- Python 3.7+
- PyPDF2: PDF 文本提取
- openai: DeepSeek API 客户端
- python-dotenv: 环境变量管理
- tqdm: 进度条显示

## 常见问题

### Q: 提示 "请设置 DEEPSEEK_API_KEY 环境变量"

**A**: 确保已创建 `.env` 文件并填入正确的 API 密钥，或使用 `--api-key` 参数。

### Q: 转换的 LaTeX 代码无法编译

**A**: 
- 检查是否安装了必要的 LaTeX 宏包（amsmath, amssymb, amsthm 等）
- **翻译版本需要用 XeLaTeX 编译**，不能用普通的 pdflatex
- 手动检查并修正生成的代码
- 可以尝试只转换部分页面进行测试

### Q: 如何编译带中文的LaTeX文件 🆕

**A**:
```bash
# 使用 XeLaTeX 编译（支持中文）
xelatex output_cn.tex

# 或使用提供的编译脚本
compile_latex.bat output_cn.tex
```

### Q: 扫描版 PDF 无法转换

**A**: 扫描版 PDF 需要先进行 OCR（光学字符识别），本工具暂不支持。建议使用 OCR 工具先转换为可搜索的 PDF。

### Q: 转换速度慢

**A**: 
- API 调用需要网络请求，大文件转换需要较长时间
- 可以先转换少量页面测试效果
- 考虑分批转换大文档

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！

## 更新日志

### v1.1.0 (2026-01-20) 🆕
- ✨ 新增翻译功能：支持先翻译成中文再转LaTeX
- ✨ 新增 `pdf2latex_translate.py` 专用翻译脚本
- ✨ 新增批量翻译功能
- 🔧 改进中文LaTeX支持（自动添加xeCJK宏包）
- 📝 更新文档和示例

### v1.0.0 (2026-01-20)
- 首次发布
- 支持 PDF 文本提取
- 支持使用 DeepSeek API 转换为 LaTeX
- 支持命令行和代码调用
- 支持指定页面转换
