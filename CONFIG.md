# ⚙️ 配置指南

## 环境变量配置

### 创建 `.env` 文件

在项目根目录创建 `.env` 文件，内容如下：

```bash
# DeepSeek (推荐使用，性价比高)
DEEPSEEK_API_KEY=sk-your-deepseek-api-key-here

# OpenAI GPT-4o (高质量)
OPENAI_API_KEY=sk-your-openai-api-key-here

# GLM (智谱清言)
ZHIPU_API_KEY=your-zhipu-api-key-here

# Gemini (Google)
GEMINI_API_KEY=your-gemini-api-key-here

# Doubao (字节豆包)
DOUBAO_API_KEY=your-doubao-api-key-here

# 默认模型 (可选)
DEFAULT_MODEL=deepseek-chat

# 美元兑人民币汇率 (默认: 7.2)
USD_TO_CNY_RATE=7.2
```

## API密钥获取

### DeepSeek (推荐)
1. 访问: https://platform.deepseek.com/
2. 注册账号并登录
3. 前往 API Keys 页面
4. 创建新的API密钥
5. **优势**: 价格低廉，效果优秀

### OpenAI
1. 访问: https://platform.openai.com/
2. 注册账号并登录
3. 前往 API Keys 页面
4. 创建新的API密钥
5. **优势**: 质量最高，支持最好

### GLM (智谱清言)
1. 访问: https://open.bigmodel.cn/
2. 注册账号并登录
3. 前往 API Keys 管理
4. 创建新的API密钥
5. **优势**: 国产模型，无需翻墙

### Gemini
1. 访问: https://makersuite.google.com/app/apikey
2. 使用Google账号登录
3. 创建API密钥
4. **优势**: Google出品，性价比高

### Doubao (豆包)
1. 访问: https://www.volcengine.com/
2. 注册火山引擎账号
3. 开通豆包服务
4. 创建API密钥
5. **优势**: 字节跳动出品

## 配置文件说明

### `config.py`

所有配置项都在 `config.py` 中定义：

```python
# API密钥
DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
ZHIPU_API_KEY: str = os.getenv("ZHIPU_API_KEY", os.getenv("GLM_API_KEY", ""))
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
DOUBAO_API_KEY: str = os.getenv("DOUBAO_API_KEY", "")

# 汇率设置
USD_TO_CNY_RATE: float = float(os.getenv("USD_TO_CNY_RATE", "7.2"))

# 文件上传限制
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
ALLOWED_EXTENSIONS = {'pdf'}

# 批量处理限制
MAX_BATCH_FILES = 10
```

## 自定义配置

### 修改汇率

**方法1**: 在 `.env` 文件中修改
```bash
USD_TO_CNY_RATE=7.3
```

**方法2**: 在 `config.py` 中修改默认值
```python
USD_TO_CNY_RATE: float = 7.3
```

前端会通过 `/api/public-config` 自动读取后端汇率配置，无需手动改前端常量。

### 修改上传限制

在 `config.py` 中修改：

```python
# 修改最大文件大小为100MB
MAX_CONTENT_LENGTH = 100 * 1024 * 1024

# 修改批量文件数量为20
MAX_BATCH_FILES = 20
```

### 修改服务器端口

在启动时指定：

```bash
python app_enhanced.py --port 8080
```

或在 `app_enhanced.py` 最后一行修改：

```python
socketio.run(app, debug=True, host='0.0.0.0', port=8080)
```

## 安全建议

### ⚠️ 重要提示

1. **永远不要**将 `.env` 文件提交到Git仓库
2. **不要**在代码中硬编码API密钥
3. **定期轮换**API密钥
4. **监控**API使用量，避免超额费用

### 文件权限

确保 `.env` 文件权限正确：

```bash
# Linux/Mac
chmod 600 .env

# Windows
icacls .env /inheritance:r /grant:r "%USERNAME%:F"
```

## 故障排查

### API密钥无效

**错误**: `401 Unauthorized` 或 `403 Forbidden`

**解决**:
1. 检查API密钥是否正确复制
2. 确认API密钥有足够余额
3. 检查API密钥权限设置

### 环境变量未加载

**错误**: 模型列表为空

**解决**:
1. 确认 `.env` 文件在项目根目录
2. 重启服务器
3. 检查 `.env` 文件格式（无空格、无引号）

### 汇率显示不正确

**解决**:
1. 更新 `USD_TO_CNY_RATE` 值
2. 清除浏览器缓存
3. 强制刷新页面 (Ctrl + F5)

## 生产环境配置

### 使用 Gunicorn 部署

```bash
# 安装gunicorn
pip install gunicorn

# 启动服务
gunicorn -k geventwebsocket.gunicorn.workers.GeventWebSocketWorker \
  -w 1 \
  -b 0.0.0.0:5000 \
  app_enhanced:app
```

### 使用 Nginx 反向代理

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Docker 部署

创建 `Dockerfile`:

```dockerfile
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["python", "app_enhanced.py"]
```

构建并运行：

```bash
docker build -t pdf2latex .
docker run -p 5000:5000 --env-file .env pdf2latex
```

---

更多问题请参考 [README.md](README.md) 或提交 Issue。
