# PDF2LaTeX 架构记忆

```text
PDF / 图片
  → Extraction (document_parser)
  → Translation (pdf2latex_enhanced)
  → LaTeX conversion (pdf2latex_enhanced)
  → Validation / Assembly (latex_utils)
  → Task / HTTP delivery (app_enhanced)
  → Workbench UI (frontend)
```

## 关键不变量

- 页码使用内部 0-based、用户展示 1-based；跨层转换必须显式处理。
- 翻译批处理必须具有完整 `[PAGE X]` 映射；缺页改为逐页补译，不能传入英文原文。
- 每页都有独立诊断、重试和终态，不能由整份文档的成功掩盖错误。
- 表格、算法、跨页公式是结构信息；不能降级为普通段落而不报告风险。
- 异步任务可持久化，但敏感 API Key 仅可驻留当前进程内存。
