# PDF2LATEX 项目任务规划

## 项目愿景
**最终目标**: 构建一个高效的PDF转LaTeX转换系统，专注于：
1. PDF内容提取效率
2. LaTeX转换质量和准确性
3. 自动化程度最大化

---

## 项目现状分析

### 当前阶段：功能原型期 (Functional Prototype)
**成熟度**: 70%

| 模块 | 状态 | 说明 |
|------|------|------|
| PDF转LaTeX核心 | ✅ 可用 | 批量翻译(4页/块)，上下文连贯 |
| PDF批量翻译 | ✅ 新增 | 每4页批量翻译，减少API调用，保留上下文 |
| 图片转LaTeX | ✅ 可用 | OCR混合策略(Tesseract+Vision) |
| 知识图谱分析 | ✅ 可用 | 定理依赖关系提取 |
| LaTeX质量评分 | ✅ 可用 | 多维度自动评分 |
| 错误处理重试 | ✅ 可用 | 分类错误+智能重试 |
| 历史记录管理 | ✅ 可用 | 转换历史持久化 |
| Web UI | ⚠️ 待优化 | 基础功能可用，UX待改进 |
| ~~双语对照阅读~~ | ❌ 已删除 | 功能冗余，已移除 |
| ~~学术智能体~~ | ❌ 已删除 | 功能冗余，已移除 |

### 差距分析
```
用户输入PDF → [需手动选择页码] → [需选择模型] → [需选择模板] → 输出LaTeX
                ↓                    ↓              ↓
              自动化               自动化          自动化
```

---

## 目标分解

### 目标1: 全自动PDF转LaTeX
**优先级**: P0 (核心)
**当前完成度**: 70%

- [ ] 智能页码选择（自动检测有效内容页）
- [ ] 自动模型选择（根据内容类型/语言）
- [ ] 自动模板选择（根据文档结构）
- [ ] 一键转换模式（vs 当前的分步选择）

### 目标2: 转换效率优化
**优先级**: P0 (核心)
**当前完成度**: 60%

- [x] 批处理性能优化 (每4页批量翻译)
- [ ] 页眉页脚自动去重
- [ ] 内存使用优化
- [ ] 并行处理支持
- [ ] 缓存机制

### 目标3: 输出质量提升
**优先级**: P1 (重要)
**当前完成度**: 50%

- [ ] 公式识别准确率提升
- [ ] 表格转换质量优化
- [ ] 参考文献格式规范化
- [ ] 图像处理优化

### 目标4: Word文档转LaTeX
**优先级**: P0 (核心)
**当前完成度**: 0%

- [ ] python-docx 内容提取
- [ ] 基础结构转换
- [ ] LLM 优化公式/表格
- [ ] API 端点集成

### 目标5: 图片转LaTeX增强
**优先级**: P1 (重要)
**当前完成度**: 40%

- [ ] SVG/EMF 矢量图支持
- [ ] 批量图片处理
- [ ] 公式识别增强
- [ ] 表格结构恢复优化

---

## 阶段规划

### Phase 1: 代码审查修复收尾 ✅
**状态**: 已完成
**内容**:
- [x] SECRET_KEY环境变量化
- [x] 页码解析DoS防护
- [x] timeout=None修复
- [x] gpt4o变量名冲突
- [x] regex负向后查找修复

### Phase 2: 核心功能稳定化
**状态**: in_progress
**目标**: 修复已知问题，提升稳定性

- [x] 完善单元测试覆盖 (完成: latex_utils, document_parser)
- [x] 修复 regex replacement 中的转义问题 (lambda 函数替代)
- [x] 修复 eqref KaTeX 兼容 (lambda 函数替代)
- [x] 日志系统规范化 (添加 logger.py)
- [x] 修复 bare except blocks (pdf2latex_enhanced.py)
- [x] 修复 SyntaxWarning (无效转义序列)
- [ ] 错误处理边界case优化
- [ ] 性能优化（大批量页面处理）
- [ ] 内存使用优化

**关键问题**:
1. 如何确保OCR质量稳定？
2. 如何处理加密/扫描PDF？
3. 如何处理中文PDF乱码？

### Phase 3: 自动化增强
**状态**: in_progress
**目标**: 减少用户干预，实现一键转换

- [x] 智能内容检测（自动判断公式/文本/表格比例）
- [x] 自动模型选择策略
- [x] 页面范围智能推荐
- [ ] 转换质量自适应（低质量时自动换方法）

### Phase 4: 效率与质量优化
**状态**: in_progress
**目标**: 提升转换效率和输出质量

- [x] 批处理并行化 (translate_batch_async, 每4页为一块)
- [x] 页眉页脚去重 (_mark_duplicate_headers)
- [x] **v0.9 智能章节识别** (detect_chapter_boundaries, 字号+正则)
- [x] **v0.9 困难页双次翻译+LLM评分** (classify_difficult_pages, _pick_better_translation)
- [x] **v0.9 章节感知 chunking** (_plan_chunks, MAX_PAGES_PER_CHAPTER=8)
- [ ] 内存优化
- [ ] 公式识别模型优化
- [ ] 表格结构恢复算法

### Phase 7: v0.9 发布 ✅
**状态**: 已完成
**内容**:
- [x] document_parser.py: detect_chapter_boundaries (字号+中英文正则)
- [x] document_parser.py: classify_difficult_pages (公式/表格/图像密度)
- [x] document_parser.py: ChapterBoundary, PageFeatures dataclass
- [x] pdf2latex_enhanced.py: _plan_chunks (章节感知 vs 4-页块)
- [x] pdf2latex_enhanced.py: _translate_chunk (分离 difficult 页)
- [x] pdf2latex_enhanced.py: _translate_difficult_pages (双次并发+评分)
- [x] pdf2latex_enhanced.py: _pick_better_translation (LLM评分容错)
- [x] config.py: ENABLE_CHAPTER_AWARE / MAX_PAGES_PER_CHAPTER / ENABLE_DIFFICULT_DOUBLE_TRANSLATE
- [x] tests/test_v09_chapter_aware.py: 15/15 测试通过

### Phase 5: Word文档支持
**状态**: pending
**目标**: 新增Word (.docx) 转 LaTeX功能

- [ ] 创建 docx2latex_converter.py
- [ ] 实现 python-docx 内容提取
- [ ] 实现基础结构转换
- [ ] 集成 LLM 优化
- [ ] 添加 /api/convert-docx 端点

### Phase 6: 图片处理增强
**状态**: pending
**目标**: 增强图片转LaTeX能力

- [ ] SVG/EMF 矢量图支持
- [ ] 批量图片处理
- [ ] 公式识别增强
- [ ] 表格结构恢复优化

---

## 技术债务

| 债务项 | 严重度 | 建议修复方式 |
|--------|--------|--------------|
| 缺少单元测试 | 高 | 添加pytest覆盖率 > 70% (已完成: latex_utils, document_parser) |
| 硬编码默认值 | 中 | 迁移到config.py统一管理 |
| 日志分散 | 中 | 统一使用logging模块 (已添加 logger.py) |
| 前端无状态管理 | 中 | 考虑引入Redux/Context |
| API无版本控制 | 低 | 添加/api/v1/前缀 |

---

## 风险与缓解

| 风险 | 影响 | 缓解策略 |
|------|------|----------|
| 大PDF内存溢出 | 高 | 分批处理+流式读取 |
| LLM调用失败 | 中 | 多模型降级+重试 |
| 扫描PDF无法处理 | 中 | 提示用户+推荐OCR |
| OCR质量不稳定 | 中 | 混合策略+质量检测 |

---

## 下一步行动

**立即执行 (本周)**:
1. [x] 添加基础单元测试框架
2. [x] 修复 `parse_pages_input` 的 `max_pages` 参数（已支持传入实际PDF总页数）
3. [x] 修复 `gpt4o` → `gpt4o_general` 后更新所有引用处
4. [x] 修复 SyntaxWarning (无效转义序列) - 已修复 \\n 为 \\\\n

**短期规划 (本月)**:
1. Phase 2: 核心功能稳定化收尾
2. Phase 3: 自动化增强完成
3. Phase 4: 效率与质量优化启动

---

## 项目里程碑

| 里程碑 | 目标日期 | 验收标准 |
|--------|----------|----------|
| M1: 稳定版发布 | 2周后 | 核心转换功能测试通过率 > 95% |
| M2: 一键转换 | 1个月 | 用户只需上传PDF即可获得结果 |
| M3: 高效版发布 | 2个月 | 批处理效率提升50%，内存降低30% |
| M4: 正式版发布 | 3个月 | 全部核心功能稳定，输出质量达标 |

---

*最后更新: 2026/05/01*
