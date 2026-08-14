# 验证规范

## 必跑基线

```powershell
scripts\verify_harness.ps1
```

该脚本使用项目 `.venv`，避免全局 Python 的 asyncio/Winsock 环境干扰。

## 测试分层

- `backend/tests/`：单元与回归测试。
- 前端改动：至少运行 `node --check frontend/static/script_enhanced.js`。
- 影响转换链路：至少运行相关 pytest 测试；高风险改动再用真实 PDF 手工验证。

测试失败不得被缓存权限警告、缺失 API Key 或网络错误伪装成通过。
