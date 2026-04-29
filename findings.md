# PDF2LATEX 项目研究发现

## 项目架构分析

### 核心模块
```
frontend/              # HTML/CSS/JS
  ├── static/         # 静态资源
  └── templates/      # Jinja2模板

backend/              # Flask后端
  ├── app_enhanced.py      # 主应用，路由，WebSocket
  ├── pdf2latex_enhanced.py # PDF处理核心
  ├── image2latex_enhanced.py # 图片OCR+转换
  ├── ocr_client.py        # OCR引擎封装
  ├── clients.py           # LLM客户端统一接口
  ├── config.py            # 配置管理
  ├── history_manager.py   # 历史记录
  ├── task_manager.py      # 任务状态管理
  ├── error_handler.py     # 错误处理
  ├── latex_syntax.py      # LaTeX语法检查
  ├── knowledge_graph.py   # 论文知识图谱
  └── bilingual_reader.py  # 双语对照
```

### 数据流
```
用户上传PDF
    ↓
[前端] 读取 → 获取页数 → 显示选项
    ↓
[后端] 保存文件 → 提取文本 → LLM转换
    ↓
[WebSocket] 实时进度 → 前端展示
    ↓
[后端] 组装LaTeX → 保存 → 返回结果
```

---

## 代码审查发现

### 已修复问题
1. **SECRET_KEY硬编码** → `os.getenv('SECRET_KEY', 'default')`
2. **页码解析无限制** → 添加 `max_pages=1000` 参数
3. **timeout=None** → 改为合理超时值(300s/600s)
4. **gpt4o重复定义** → 重命名为 `gpt4o_general`
5. **regex负向后查找** → `(?<!\\)(?:\\\\)*&` 正确处理`\\`

### 仍需关注
1. `asyncio.run()` 在同步路由中使用 - 当前Flask使用`threading`模式，安全
2. 缺少单元测试覆盖
3. `gemini3_pro` 的 `timeout=None` 已修复为600s

---

## 用户需求分析

### 最终目标
1. **全自动PDF转LaTeX** - 用户只需输入PDF
2. **思维导图生成** - 从文章结构提取
3. **学术推荐智能体** - 相关论文推荐
4. **ArXiv搜索集成** - 搜索+一键转换

### 当前自动化程度
```
输入PDF → [用户选择页码] → [用户选择模型] → [用户选择模板] → 输出
              ↑              ↑               ↑
           自动化          自动化           自动化
```

---

## 技术选型决策

### 思维导图格式
- **选择**: Mermaid
- **理由**: 语法简单，支持导出LaTeX，生态好

### 推荐算法
- **选择**: 主题模型 (Topic Modeling)
- **理由**: 可解释性强，计算资源需求低，无需训练数据

### ArXiv缓存
- **选择**: 文件系统缓存
- **理由**: 简单够用，避免引入Redis等依赖

---

## 竞品分析

| 产品 | 优点 | 缺点 |
|------|------|------|
| Mathpix Snip | 公式识别准确率高 | 付费，专注公式非全文 |
| InftyReader | 免费，中文支持好 | 界面陈旧，活跃度低 |
| Docling | 开源，结构化输出 | 新生项目，成熟度低 |
| **本项目** | 全流程自动化，LLM驱动，思维导图 | 依赖LLM API，稳定性待验证 |

---

## 风险评估

### 高风险
1. **LLM API调用失败** → 需要多模型降级策略
2. **大批量页面OOM** → 需要分批处理+流式读取

### 中风险
1. **扫描版PDF无法处理** → 提示用户使用OCR
2. **ArXiv API限流** → 添加缓存+请求间隔

### 低风险
1. **前端状态管理混乱** → 考虑引入React/Vue重构

---

*最后更新: 2026-04-29*
