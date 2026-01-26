# 🔑 API Key 配置指南

## 📋 配置步骤

### 方法1：使用 .env 文件（推荐）

1. **创建 .env 文件**
   
   在项目根目录 `d:\PDF2LATEX\` 创建一个名为 `.env` 的文件

2. **填写配置**
   
   复制以下内容到 `.env` 文件中，并填写你的 API Keys：

```env
# ==================== 必填配置 ====================

# DeepSeek API Key（用于 PDF 转换）
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx

# OpenAI API Key（用于图片识别）⭐ 推荐
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx

# ==================== 可选配置 ====================

# Google Gemini API Key（Vision 备选）
GEMINI_API_KEY=

# 豆包 API Key
DOUBAO_API_KEY=

# 智谱 GLM API Key
ZHIPU_API_KEY=

# DeepSeek-Math API Key
CANOPY_WAVE_API_KEY=
```

3. **保存文件**并重启服务器

---

### 方法2：直接修改 config.py

如果不想创建 `.env` 文件，可以直接修改 `config.py`：

打开 `d:\PDF2LATEX\config.py`，找到以下行并填写：

```python
# 第16行
DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "sk-你的DeepSeek密钥")

# 第22行
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "sk-你的OpenAI密钥")
```

**注意**：方法2 会将密钥直接写入代码，不够安全，不推荐。

---

## 🎯 API Key 获取地址

### 1. DeepSeek（必需 - 用于 PDF 转换）

**获取地址**：https://platform.deepseek.com/api_keys

**步骤**：
1. 注册/登录 DeepSeek 账号
2. 进入 API Keys 页面
3. 点击"创建新密钥"
4. 复制密钥（格式：`sk-xxxxxxxx`）
5. 填写到配置中

**用途**：PDF 转 LaTeX、文本翻译、LaTeX 转换

---

### 2. OpenAI（推荐 - 用于图片识别）⭐

**获取地址**：https://platform.openai.com/api-keys

**步骤**：
1. 注册/登录 OpenAI 账号
2. 充值至少 $5（用于 API 调用）
3. 创建 API Key
4. 复制密钥（格式：`sk-xxxxxxxx`）
5. 填写到配置中

**用途**：图片 OCR 识别（GPT-4o Vision）

**成本**：约 $0.01-0.05/张图片

---

### 3. Google Gemini（可选 - Vision 备选）

**获取地址**：https://aistudio.google.com/app/apikey

**步骤**：
1. 使用 Google 账号登录
2. 点击"Get API Key"
3. 创建新项目（如果需要）
4. 复制 API Key（格式：`AIzaSyxxxxxx`）
5. 填写到配置中

**用途**：图片 OCR 识别（Gemini Vision，比 GPT-4o 便宜）

**成本**：约 $0.001-0.005/张图片

---

## ✅ 配置示例

### 最小配置（仅 PDF 转换）

```env
DEEPSEEK_API_KEY=sk-abc123def456...
```

### 推荐配置（PDF + 图片识别）

```env
DEEPSEEK_API_KEY=sk-abc123def456...
OPENAI_API_KEY=sk-xyz789ghi012...
```

### 完整配置（所有功能 + 混合方案）

```env
DEEPSEEK_API_KEY=sk-abc123def456...
OPENAI_API_KEY=sk-xyz789ghi012...
GEMINI_API_KEY=AIzaSyxxxxxxxxx...
DOUBAO_API_KEY=your_doubao_key...
ZHIPU_API_KEY=your_zhipu_key...
```

---

## 🧪 验证配置

配置完成后，重启服务器：

```bash
cd d:\PDF2LATEX
python app_enhanced.py
```

**查看启动日志**，确认 API 已正确配置：

```
============================================================
PDF2LaTeX + Image2LaTeX 增强版启动中...
============================================================
上传目录: D:\PDF2LATEX\uploads
输出目录: D:\PDF2LATEX\outputs
============================================================
访问地址: http://localhost:5000
新功能:
  ✓ 实时进度显示
  ✓ Token用量统计
  ✓ 美化代码展示
  ✓ 图片OCR识别 (Vision API + Tesseract)  <-- 看到这行说明配置成功
  ✓ 截图粘贴支持
按 Ctrl+C 停止服务器
============================================================
```

**访问网页**：http://localhost:5000

在"选择模型"下拉框中应该能看到你配置的所有模型。

---

## ❌ 常见问题

### 问题1：启动后没有可用模型

**原因**：所有 API Key 都未配置或配置错误

**解决**：
1. 检查 `.env` 文件是否在项目根目录
2. 检查 API Key 格式是否正确
3. 确保 API Key 前后没有空格或引号

### 问题2：图片识别失败

**提示**：`Vision API 未配置`

**解决**：配置 `OPENAI_API_KEY` 或 `GEMINI_API_KEY`

### 问题3：API Key 无效

**提示**：`401 Unauthorized` 或 `400 Bad Request`

**原因**：
- API Key 错误或已过期
- 账户余额不足（OpenAI）
- API Key 权限不足

**解决**：
1. 重新复制 API Key
2. 检查账户余额
3. 确认 API Key 有正确权限

---

## 💡 安全建议

1. ✅ **不要**将 `.env` 文件提交到 Git
2. ✅ **不要**在公开场合分享你的 API Key
3. ✅ 定期轮换 API Key
4. ✅ 设置 API 使用额度限制
5. ✅ 如果 Key 泄露，立即撤销并重新生成

---

## 📞 需要帮助？

如果配置过程中遇到问题，请：

1. 检查服务器终端输出的错误信息
2. 检查浏览器控制台（F12）的错误
3. 确认 API Key 格式正确
4. 确认账户余额充足

配置完成后即可开始使用！🎉
