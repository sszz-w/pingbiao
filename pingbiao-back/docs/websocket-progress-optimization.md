# WebSocket 进度消息优化方案

## 优化目标
增强前端对评标流程的进度可见性和可预测性，通过添加细粒度的进度事件，让用户清楚了解当前处理阶段和剩余工作量。

## 新增事件类型

### progress_update
用于报告各阶段的进度信息。

**字段说明：**
- `type`: "progress_update"
- `stage`: 阶段标识
  - `pdf_parse`: PDF 文件解析阶段
  - `debate`: 条款评审辩论阶段
  - `report`: 报告生成阶段
- `current`: 当前进度（从 0 开始）
- `total`: 总任务数
- `message`: 人类可读的进度描述

**示例：**
```json
{
  "type": "progress_update",
  "stage": "pdf_parse",
  "current": 1,
  "total": 4,
  "message": "正在解析投标文件 company_a.pdf..."
}
```

## 优化后的事件流程

### 1. PDF 解析阶段
```
progress_update (stage: pdf_parse, 0/4) → 解析招标文件
parse_tender_done
progress_update (stage: pdf_parse, 1/4) → 解析投标文件 1
progress_update (stage: pdf_parse, 2/4) → 解析投标文件 2
progress_update (stage: pdf_parse, 3/4) → 解析投标文件 3
parse_bid_done × 3
```

### 2. 条款评审阶段
```
progress_update (stage: debate, 1/12) → 评审条款 1 × 投标 A
clause_start
debate (support)
debate (challenge)
score
clause_end
progress_update (stage: debate, 2/12) → 评审条款 1 × 投标 B
...
```

### 3. 报告生成阶段
```
progress_update (stage: report, 0/1) → 生成评标报告
report
```

## 前端集成建议

### 进度条计算
```typescript
// 根据 stage 和 current/total 计算整体进度
function calculateOverallProgress(event: ProgressEvent): number {
  const stageWeights = {
    pdf_parse: 0.2,    // 20%
    debate: 0.7,       // 70%
    report: 0.1        // 10%
  };

  const stageProgress = event.current / event.total;
  const stageWeight = stageWeights[event.stage];

  // 计算该阶段在整体进度中的贡献
  return stageProgress * stageWeight;
}
```

### UI 展示
- **主进度条**: 显示整体进度百分比
- **阶段指示器**: 高亮当前阶段（PDF 解析 → 条款评审 → 报告生成）
- **详细信息**: 显示 `message` 字段的内容
- **预估时间**: 根据历史数据估算剩余时间

## 实现细节

### 修改文件
- `models/schemas.py`: 添加 `ProgressEvent` 数据模型
- `routers/run.py`: 在事件流中插入进度事件

### 关键代码位置
- PDF 解析进度: `routers/run.py:44-70`
- 条款评审进度: `routers/run.py:82-96`
- 报告生成进度: `routers/run.py:148-155`

## 向后兼容性
- 新增的 `progress_update` 事件不影响现有事件
- 前端可选择性处理进度事件
- 旧版前端忽略未知事件类型即可

## 测试建议
1. 使用不同数量的投标文件测试进度计算准确性
2. 验证 `current` 和 `total` 的一致性
3. 确认 `message` 内容对用户友好
4. 测试网络延迟情况下的进度更新体验
