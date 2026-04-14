from pydantic import BaseModel


class Clause(BaseModel):
    """招标评审条款"""
    id: str
    no: str
    desc: str
    score: float
    weight: float
    order: int


class Chunk(BaseModel):
    """投标文件切片"""
    bid_id: str
    index: int
    content: str


class DebateEvent(BaseModel):
    """辩论事件（NDJSON 流中的单条事件）"""
    type: str
    role: str | None = None
    content: str | None = None
    score: float | None = None
    reason: str | None = None
    clause_no: str | None = None
    bid_name: str | None = None


class ClauseScore(BaseModel):
    """单个投标在某条款上的评分结果"""
    bid_id: str
    bid_name: str
    score: float
    reason: str


class ClauseRequest(BaseModel):
    """POST /api/clause 请求体"""
    session_id: str
    clause: Clause
    api_base: str
    api_key: str
    model: str


class ClauseResponse(BaseModel):
    """POST /api/clause 响应体"""
    clause_id: str
    clause_no: str
    scores: list[ClauseScore]


class ClauseListItem(BaseModel):
    """WebSocket clause_list_result 中 data 数组元素的固定结构"""

    条款描述: str = ""
    评分标准: str = ""
    其他要求: str = ""


class ProgressEvent(BaseModel):
    """进度事件（用于细粒度进度追踪）"""
    type: str  # progress_update
    stage: str  # pdf_parse, clause_extract, debate, report
    current: int
    total: int
    message: str | None = None
