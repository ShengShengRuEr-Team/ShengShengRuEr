"""模块二接口请求与响应模型。

学生接口只暴露可见字段；答案、解析、听力正文与批次/状态字段仅出现在
管理员接口，服务端组装时即剔除，不先返回再交给前端隐藏。
"""

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# 学生端
# --------------------------------------------------------------------------- #
class PaperListItem(BaseModel):
    exam_paper_id: int
    exam_paper_code: str
    exam_level: str
    exam_year: int
    exam_month: int
    paper_set: int
    content_scope: str
    audio_url: str
    duration_ms: int | None = None


class PaperListData(BaseModel):
    items: list[PaperListItem]


class OptionItem(BaseModel):
    label: str
    text: str


class QuestionStudent(BaseModel):
    question_no: int
    question_id: int
    question_text: str
    options: list[OptionItem]


class PassageStudent(BaseModel):
    passage_id: int
    passage_index: int
    passage_type: str
    topic: str
    questions: list[QuestionStudent]


class PaperDetailStudent(BaseModel):
    exam_paper_id: int
    exam_paper_code: str
    exam_level: str
    exam_year: int
    exam_month: int
    paper_set: int
    content_scope: str
    audio_url: str
    duration_ms: int | None = None
    passages: list[PassageStudent]


# --------------------------------------------------------------------------- #
# 管理员端（在学生结构基础上追加配套内容与状态）
# --------------------------------------------------------------------------- #
class SegmentAdmin(BaseModel):
    segment_id: int
    segment_index: int
    segment_type: str
    text: str
    speaker_code: str
    start_ms: int
    end_ms: int


class QuestionAdmin(QuestionStudent):
    correct_option: str
    explanation_text: str
    explanation_source: str
    question_index: int | None = None
    content_state: str = "待补齐"
    review_status: str = "待审核"


class PassageAdmin(BaseModel):
    passage_id: int
    passage_index: int
    passage_type: str
    topic: str
    scene: str = ""
    accent: str = "未判定"
    review_status: str = "待审核"
    start_ms: int
    body_end_ms: int | None = None
    end_ms: int | None = None
    segments: list[SegmentAdmin]
    questions: list[QuestionAdmin]


class PaperCompanionAdmin(BaseModel):
    exam_paper_id: int
    exam_paper_code: str
    exam_level: str
    exam_year: int
    exam_month: int
    paper_set: int
    content_scope: str
    audio_url: str
    duration_ms: int | None = None
    # 状态字段：彼此独立，不合并为一个“完成”状态。
    batch_code: str | None = None
    is_current: bool = False
    check_passed: bool = False
    is_visible: bool = False
    is_pending_confirmation: bool = False
    mapping_source: str = ""
    review_status: str = "待审核"
    passages: list[PassageAdmin]


class CheckIssue(BaseModel):
    kind: str
    message: str


class CheckResultData(BaseModel):
    exam_paper_id: int
    batch_code: str | None = None
    is_passed: bool
    issues: list[CheckIssue]
    checked_at: str | None = None


# --------------------------------------------------------------------------- #
# 请求
# --------------------------------------------------------------------------- #
class VisibilityActionRequest(BaseModel):
    action: str = Field(pattern="^(confirm|cancel)$")
    reason: str = Field(default="", max_length=255)


class VisibilityStateData(BaseModel):
    exam_paper_id: int
    batch_code: str | None = None
    is_visible: bool
    check_passed: bool
    action: str
