# PDF2LaTeX 项目宪法

## 不可违反的产品约束

1. 正确性高于表面完整；不可靠的公式不得猜测补全。
2. 输出保持单栏；不得自动加入 `multicols`、`vspace` 或 `newpage`。
3. 所有改动必须保留或新增最小回归测试。
4. API Key、令牌和用户文件不得写入日志、历史记录、测试样例或持久任务文件。
5. 不得为通过测试而删除诊断、降低校验标准或吞掉异常。

## 修改边界

- `backend/document_parser.py`：只负责提取与结构识别。
- `backend/pdf2latex_enhanced.py`：翻译、转换、页级路由；不得承担 HTTP/前端状态。
- `backend/latex_utils.py`：清理、校验、组装；不得发起模型请求。
- `backend/app_enhanced.py`：HTTP、任务生命周期、可读错误；不得复制转换规则。
- `frontend/`：呈现和交互；服务端错误必须转为用户可行动的提示。

## 交付报告

每次完成修改必须说明：修改文件、行为变化、风险、验证命令及结果。
