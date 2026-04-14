# Pingbiao-Power 后端 Bug 报告

审查日期: 2026-03-19
对照文档: `docs/interface.md`

---

## Critical

### Bug 1: 招标文件解析失败时静默返回空列表

**文件**: `services/tender_parser.py` 第 57-60 行

**现象**: 当 LLM 返回格式异常的 JSON（如 markdown 代码块包裹、返回对象而非数组），`except` 块吞掉异常并返回 `[]`。后续 `event_stream()` 发出 `parse_tender_done` 事件但 `clauses` 为空数组，评审循环直接跳过，用户看到空白报告，无任何错误提示。

**期望行为**: 应抛出异常，由 `event_stream()` 的外层 `try/except` 捕获并 yield `error` 事件。

**修复建议**:
```python
except Exception as e:
    raise ValueError(f"招标文件解析失败: {e}") from e
```

---

### Bug 2: `clause_end` 在 `score` 缺失时仍然发出

**文件**: `routers/run.py` 第 100-120 行

**现象**: `score` 事件仅在 `final_score is not None` 时 yield，但 `clause_end` 无条件 yield。当打分失败时，前端收到 `clause_end` 但没有对应的 `score`，该条款结果丢失，最终报告缺项。

**期望行为**: 每个 `clause_start` → `clause_end` 周期必须产生一个 `score`。

**修复建议**: 打分失败时 yield 一个 `error` 事件，或使用兜底分数（如 0 分 + 说明理由）确保 `score` 始终发出。

---

### Bug 3: JSON 提取正则无法匹配嵌套大括号

**文件**: `services/debate.py` 第 27-33 行

**现象**: `_extract_json` 的兜底正则 `r"\{[^{}]*\}"` 排除了 `{}`，无法匹配 LLM 返回的包含嵌套大括号的 JSON（如 reason 字段含代码片段或模板引用）。匹配失败后抛出 `ValueError`，被上层 `except` 捕获，静默使用 `clause.score * 0.7` 作为默认分数，评分质量下降且用户无感知。

**修复建议**:
```python
# 替换为贪婪匹配
match = re.search(r"\{.*\}", text, re.DOTALL)
```
或使用更健壮的 JSON 提取方案。

---

## Important

### Bug 4: `parse_bids` 同步阻塞异步事件循环

**文件**: `routers/run.py` 第 57 行; `services/bid_parser.py` 第 7 行

**现象**: `parse_bids` 使用 PyMuPDF 做 CPU 密集型 PDF 文本提取，在 `async generator` 中同步调用，阻塞事件循环。多个并发请求时会导致所有请求卡住。

**修复建议**:
```python
bid_chunks = await asyncio.to_thread(parse_bids, bid_files_data)
```

---

### Bug 5: `tender_parser.py` 同样存在同步阻塞

**文件**: `services/tender_parser.py` 第 26-29 行

**现象**: `fitz.open()` 和 `page.get_text()` 是同步 CPU 密集操作，在 `async def` 函数中直接调用，阻塞事件循环。

**修复建议**: 将 PyMuPDF 提取逻辑包装到 `asyncio.to_thread()` 中。

---

### Bug 6: LLM 返回的分数未做范围校验

**文件**: `services/debate.py` 第 72, 98, 124 行

**现象**: LLM 被要求返回 0 ~ 满分的分数，但代码未校验或 clamp。LLM 幻觉可能返回超出范围的值（如 10 分满分返回 11.0），直接流入报告。

**修复建议**:
```python
final_score = max(0.0, min(float(arb_data.get("score", ...)), clause.score))
```
对 `support_score` 和 `challenge_score` 同样处理。

---

### Bug 7: `bid_files` 变量名遮蔽 + 文件句柄风险

**文件**: `routers/run.py` 第 53-55 行

**现象**: 外层参数 `bid_files` 与内部变量命名容易混淆。更关键的是，`tender_file.read()` 在 generator 内部调用，如果 generator 被延迟迭代且请求上下文已释放，文件句柄可能已关闭。

**修复建议**: 在 generator 外部预读取文件内容，传入 bytes 而非 UploadFile 对象。

---

### Bug 8: LLM 返回 JSON 对象而非数组时静默失败

**文件**: `services/tender_parser.py` 第 45 行

**现象**: `json.loads(result_text)` 假设结果是 JSON 数组。部分 LLM 会返回 `{"clauses": [...]}` 格式的对象，此时 `for i, item in enumerate(clauses_data)` 会抛出 `TypeError`（遍历 dict），被 `except Exception` 捕获后静默返回 `[]`，触发 Bug 1。

**修复建议**:
```python
clauses_data = json.loads(result_text)
if isinstance(clauses_data, dict):
    # 尝试从常见 key 中提取数组
    for key in ("clauses", "data", "items", "result"):
        if key in clauses_data and isinstance(clauses_data[key], list):
            clauses_data = clauses_data[key]
            break
    else:
        raise ValueError("LLM 返回了非数组格式的 JSON")
```
