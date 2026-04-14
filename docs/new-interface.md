# 新接口设计（草案）

本文档描述前后端新契约，**当前章节仅约定 WebSocket** 的收发包方式；REST / 流式 HTTP 后续再补。

---

## 1. 总则

| 项 | 约定 |
|----|------|
| 传输 | 仅使用 **WebSocket 文本帧**（`send` / `receive` 的 text），不再使用 binary |
| 编码 | UTF-8，**每帧一个 JSON 对象**（单行或可pretty，解析时按单帧整体 `JSON.parse`） |
| 版本 | 根字段 `v`（整数），当前 **只定义 `v: 1`**；不认识的 `v` 客户端应关闭并提示升级 |
| 关联 | 可选字段 `rid`（string）：客户端生成，客户端发往服务端时带上，服务端响应同款 `rid` 便于 Promise / 超时对齐 |
| 时间 | 可选字段 `ts`（number，毫秒时间戳）：**建议服务端发出时统一带上**，便于前端排序与排障 |

**与现状的关系**：实现迁移阶段可双轨（见 §6）；目标态为「所有业务消息均为 JSON 信封」，避免混用裸字符串。

---

## 2. 消息信封（v1）

每一帧 JSON 必须包含 `type`，其余字段按 `type` 解释。

```json
{
  "v": 1,
  "type": "<命名空间>.<事件名>",
  "rid": "可选-客户端请求 id",
  "ts": 1730000000000,
  "payload": {}
}
```

约定：

- `type` 使用 **点分层命名**：`client.*` 表示仅客户端发送，`server.*` / `task.*` 表示服务端推送（命名即文档，不据此校验方向，以连接语义为准）。
- 业务数据一律放在 `payload` 内；`payload` 缺省等价于 `{}`。
- **禁止**在 `v1` 中再使用「整帧纯文本」承载业务（心跳可例外见 §6 过渡期）。

---

## 3. 连接与端点

| 端点 | 用途 | 路径参数 |
|------|------|----------|
| 会话信道 | 模型校验成功后保持长连接，供后续接口向该会话推送 | `GET ws(s)://{host}/api/ws/session/{sessionId}` |
| 任务日志信道 | 与单次 PDF 处理任务绑定，推送处理日志与结束态 | `GET ws(s)://{host}/api/ws/pdf-process/{taskId}` |

说明：

- `sessionId`：与 `POST /api/verify-model` 成功响应中的 `taskId` 一致（沿用现有字段名可到前端再统一别名）。
- `taskId`：与 `POST /api/upload-pdf` 表单中的 `task_id` 一致。

---

## 4. 客户端 → 服务端（接收）

服务端在以下端点 **接收** 的帧应解析为 §2 信封（`v1`）。

### 4.1 通用

| `type` | `payload` | 说明 |
|--------|-----------|------|
| `client.ping` | `{ "nonce": "<可选随机串>" }` | 心跳；服务端应回复 `server.pong`（见 §5） |
| `client.echo` | 任意小对象 | 调试用；可选实现，原样随 `server.echo` 返回 |

### 4.2 会话信道（`/api/ws/session/{sessionId}`）

当前以保活为主，**不强制**业务指令；后续若需「取消」「订阅主题」等，在 `client.*` 下扩展，并在此表追加。

### 4.3 任务日志信道（`/api/ws/pdf-process/{taskId}`）

默认 **客户端可不发送任何消息**，仅收日志。若需「客户端主动取消」等，新增 `client.cancel` 等类型并在实现时与后台任务取消逻辑绑定。

---

## 5. 服务端 → 客户端（发送）

### 5.1 连接生命周期

| `type` | `payload` | 何时发送 |
|--------|-----------|----------|
| `server.ready` | `{ "channel": "session" \| "pdf_task", "ref_id": "<sessionId 或 taskId>" }` | `accept` 后首帧（建议），便于前端确认上下文 |
| `server.error` | `{ "code": "<机器可读码>", "message": "<人类可读>", "detail": {} }` | 鉴权失败、参数非法、内部错误等；之后服务端应 `close` |
| `server.pong` | `{ "nonce": "<与 ping 对齐>" }` | 响应 `client.ping` |
| `server.echo` | 与客户端 `client.echo` 的 payload 一致 | 调试用 |

`server.error` 建议 `code` 枚举示例：

- `session.invalid` — session 未注册或已失效  
- `task.not_found` — 无对应任务或已过期  
- `task.duplicate_socket` — 同一 task 重复连接（若将来禁止）  
- `internal` — 未分类错误  

### 5.2 任务与日志（任务信道为主，会话信道若转发任务也可复用）

| `type` | `payload` | 说明 Log / UI |
|--------|-----------|----------------|
| `task.log` | `{ "task_id": "<可选，默认可从路径推断>", "level": "info" \| "warn" \| "error", "message": "<单行或多行文本>" }` | 控制台、终端样式展示；`level` 缺省为 `info` |
| `task.progress` | `{ "phase": "<如 parse|llm|report>", "percent": 0-100 \| null, "message": "<可选>" }` | 进度条；`percent` 可为 `null` 表示阶段未知 |
| `task.result` | `{ "ok": true \| false, "summary": "<可选字符串>", "meta": {} }` | **业务完成**的正式结果；收到后客户端可认为任务结束 |
| `task.closed` | `{ "reason": "completed" \| "cancelled" \| "error", "message": "<可选>" }` | 通道即将关闭的通知；随后服务端 `close` |

规则建议：

1. 正常结束顺序：`task.log`（零或多条）→ `task.result` → `task.closed`（`reason: completed`）→ WebSocket `close`。  
2. 异常：`server.error` 或 `task.closed`（`reason: error`）→ `close`。  
3. **`task.result` 与现有「最后一行中文结果」对齐**：`summary` 可承载原先「处理成功/失败」的摘要，结构化字段可以放 `meta`。

### 5.3 会话信道上的推送（将来）

其他 HTTP 接口需要通过 `sessionId` 推送时，复用同一套 `task.*` / 或新增 `notify.*`，在专门章节扩展；原则仍是 §2 信封。

---

## 6. 从现行实现迁移（双轨）

现行代码要点回顾：

- `/api/ws/session/{id}`：客户端发纯文本 `"ping"`，服务端回 `"pong"`；错误时为裸 JSON 字符串。  
- `/api/ws/pdf-process/{id}`：服务端逐条 **纯文本** 日志，结束关闭连接。

**条款打分（与 `POST /api/analysis-clause` 配套，同一 `task_id` 信道）**：服务端推送 JSON 文本帧（非 §2 v1 信封），`type` 取值包括：

- `analysis_clause_log` — `message` 为进度说明  
- `analysis_clause_result` — `data` 为 `{ "本地条款摘录", "打分", "思考过程" }` 或 `null`  
- `analysis_clause_done` — `task_id`、`result`（0/1）  
- 另可能与 PDF/条款列表共用 `error`、`clause_list_*`、`pdf_log` 等

**迁移策略建议**：

1. **Phase A**：服务端同时接受 `client.ping`（JSON）与纯文本 `ping`；发送时优先发 §5 的 JSON，必要时对旧前端仍发纯文本日志（仅 pdf 信道）。  
2. **Phase B**：前端只解析 JSON 帧；pdf 信道不再发裸字符串。  
3. **Phase C**：移除纯文本兼容分支。

---

## 7. 示例

### 7.1 会话信道：心跳

客户端发送：

```json
{ "v": 1, "type": "client.ping", "rid": "r-1", "payload": { "nonce": "n-xyz" } }
```

服务端响应：

```json
{ "v": 1, "type": "server.pong", "rid": "r-1", "ts": 1730000000123, "payload": { "nonce": "n-xyz" } }
```

### 7.2 PDF 任务信道：日志与结束

```json
{ "v": 1, "type": "server.ready", "ts": 1730000000100, "payload": { "channel": "pdf_task", "ref_id": "upload-task-uuid" } }
```

```json
{ "v": 1, "type": "task.log", "ts": 1730000000200, "payload": { "level": "info", "message": "开始解析 PDF…" } }
```

```json
{ "v": 1, "type": "task.result", "ts": 1730000000800, "payload": { "ok": true, "summary": "处理成功", "meta": {} } }
```

```json
{ "v": 1, "type": "task.closed", "ts": 1730000000801, "payload": { "reason": "completed" } }
```

---

## 8. 后续工作（非本文范围）

- REST：`verify-model`、`upload-pdf` 等与 `sessionId` / `taskId` 的返回体对齐（字段命名 camelCase vs snake_case 统一）。  
- 与 `POST /api/run` 的 NDJSON 流式是否合并到 WebSocket 的统一方案。  
- OpenAPI / TypeScript 类型从 `type` + `payload` 生成 discriminated union。

---

*文档版本：与 WS `v: 1` 同步迭代。*
