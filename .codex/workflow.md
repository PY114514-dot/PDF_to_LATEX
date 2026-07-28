# Agent 工作流

1. 读取 `AGENTS.md`、`docs/DEVELOPMENT_GUIDE.md` 和本目录相关文档。
2. 明确需求、受影响层及不确定项；不可安全假设时先请求用户决定。
3. 做最小、可回滚的改动；不覆盖工作区中无关的用户修改。
4. 针对缺陷添加回归测试，运行 `scripts/verify_harness.ps1`。
5. 如改动了长期决策，同步更新 `docs/DEVELOPMENT_GUIDE.md`。
6. 交付时报告修改、验证、剩余风险；不声称未实际验证的结果。
