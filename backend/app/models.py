from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class Person(BaseModel):
    id: str
    name: str
    role: str


class Identity(BaseModel):
    id: str
    name: str
    role: str = ""
    description: str = ""


class Project(BaseModel):
    id: str
    name: str
    description: str = ""
    status: str = "进行中"
    owner_id: str | None = None


class Metric(BaseModel):
    id: str
    name: str
    current_value: float | None = None
    target_value: float | None = None
    unit: str = ""
    objective_id: str | None = None


class Risk(BaseModel):
    id: str
    title: str
    impact: str = ""
    owner_id: str | None = None
    status: str = "开放"
    project_id: str | None = None


class Policy(BaseModel):
    id: str
    title: str
    content: str
    scope: str = ""


class HistoricalStance(BaseModel):
    id: str
    person_id: str
    topic: str
    stance: str
    effective_scope: str = ""
    updated_at: str = ""


class Objective(BaseModel):
    id: str
    title: str
    progress: int
    metric: str
    risk: str


class Task(BaseModel):
    id: str
    title: str
    owner_id: str
    due_date: str
    status: str
    source_meeting_id: str | None = None
    source_decision_id: str | None = None


class AuthorizationRule(BaseModel):
    id: str
    person_id: str
    scope: str
    allowed_actions: list[str]
    escalation_triggers: list[str]


class AdsWorkspacePayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    people: list[Person] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    objectives: list[Objective] = Field(default_factory=list)
    metrics: list[Metric] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    tasks: list[Task] = Field(default_factory=list)
    policies: list[Policy] = Field(default_factory=list)
    historical_stances: list[HistoricalStance] = Field(default_factory=list)
    authorization_rules: list[AuthorizationRule] = Field(default_factory=list)


class AdsWorkspace(AdsWorkspacePayload):
    id: str
    created_at: str
    updated_at: str
    archived: bool = False


class AppSettings(BaseModel):
    onboarding_complete: bool = False
    active_identity_id: str | None = None
    active_workspace_id: str | None = None
    identities: list[Identity] = Field(default_factory=list)
    audio_retention_days: Literal[0, 30, 90] = 0


class AppSettingsUpdateRequest(BaseModel):
    audio_retention_days: Literal[0, 30, 90] | None = None
    identity: Identity | None = None
    active_identity_id: str | None = None


class OnboardingRequest(BaseModel):
    identity: Identity
    workspace_name: str = Field(min_length=1, max_length=120)
    workspace_description: str = Field(default="", max_length=500)


class MigrationChoiceRequest(BaseModel):
    action: Literal["use_existing", "create_blank"]


class MeetingAnalysisRequest(BaseModel):
    title: str
    transcript: str
    scenario: str = "项目周例会"
    model_provider_id: str = "deepseek"
    ads_context: AdsWorkspacePayload | None = None


class AgendaItem(BaseModel):
    topic: str
    context: str
    suggested_question: str
    duration_minutes: int | None = Field(default=None, ge=1, le=480)


class AgendaDraftRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2_000)
    duration_minutes: int = Field(ge=5, le=480)
    workspace_id: str | None = Field(default=None, max_length=80)
    model_provider_id: str = Field(default="mock", max_length=80)

    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str) -> str:
        return value.strip()


class AgendaDraftResponse(BaseModel):
    agenda_text: str
    agenda: list[AgendaItem]
    mode: Literal["live", "local_rules"]


class RecurrenceRule(BaseModel):
    frequency: Literal["none", "weekly", "biweekly", "monthly"] = "none"
    end_date: str | None = None

    @model_validator(mode="after")
    def validate_end_date(self):
        if self.frequency == "none":
            self.end_date = None
            return self
        if not self.end_date:
            raise ValueError("循环会议必须设置截止日期")
        try:
            date.fromisoformat(self.end_date)
        except ValueError as exc:
            raise ValueError("循环会议截止日期格式无效") from exc
        return self


class MeetingCreateRequest(BaseModel):
    title: str = Field(max_length=120)
    scenario: str = Field(default="项目周例会", max_length=50)
    meeting_type: str = Field(default="项目周例会", max_length=50)
    scheduled_at: str = Field(default="2026-08-20 14:00", max_length=80)
    end_at: str | None = Field(default=None, max_length=80)
    duration_minutes: int = Field(default=45, ge=5, le=480)
    participants: list[str] = Field(default_factory=lambda: ["张伟", "李娜", "王强", "陈敏"])
    objective: str = Field(default="确认交付范围、风险和本周行动项", max_length=500)
    agenda_text: str = Field(default="进度同步\n风险确认\n行动项闭环", max_length=2_000)
    agenda: list[AgendaItem] = Field(default_factory=list)
    participation_mode: Literal["self", "delegate"] = "self"
    model_provider_id: str = Field(default="deepseek", max_length=80)
    workspace_id: str | None = Field(default=None, max_length=80)
    agent_identity_id: str | None = Field(default=None, max_length=80)
    authorization_rule_ids: list[str] = Field(default_factory=list)
    auto_reply_enabled: bool = False
    recurrence: RecurrenceRule = Field(default_factory=RecurrenceRule)

    @field_validator("title", "scenario")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value

    @model_validator(mode="after")
    def normalize_time_range(self):
        start = self.scheduled_at.replace("T", " ")
        try:
            start_dt = datetime.fromisoformat(start)
        except ValueError as exc:
            raise ValueError("开始时间格式无效") from exc
        self.scheduled_at = start
        if self.end_at:
            end = self.end_at.replace("T", " ")
            try:
                end_dt = datetime.fromisoformat(end)
            except ValueError as exc:
                raise ValueError("结束时间格式无效") from exc
            minutes = int((end_dt - start_dt).total_seconds() / 60)
            if minutes < 5 or minutes > 480:
                raise ValueError("会议时长必须在 5 分钟至 8 小时之间")
            self.end_at = end
            self.duration_minutes = minutes
        if self.recurrence.frequency != "none":
            recurrence_end = date.fromisoformat(self.recurrence.end_date or "")
            if recurrence_end < start_dt.date():
                raise ValueError("循环会议截止日期不能早于首次会议")
            try:
                maximum_end = start_dt.date().replace(year=start_dt.year + 1)
            except ValueError:
                maximum_end = start_dt.date().replace(year=start_dt.year + 1, day=28)
            if recurrence_end > maximum_end:
                raise ValueError("循环会议跨度不能超过一年")
        if self.agenda and any(item.duration_minutes is not None for item in self.agenda):
            if any(item.duration_minutes is None for item in self.agenda):
                raise ValueError("结构化议程必须为每一项分配分钟数")
            if sum(item.duration_minutes or 0 for item in self.agenda) != self.duration_minutes:
                raise ValueError("议程分钟合计必须等于会议时长")
        return self


class MeetingUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    scenario: str | None = Field(default=None, max_length=50)
    meeting_type: str | None = Field(default=None, max_length=50)
    scheduled_at: str | None = Field(default=None, max_length=80)
    end_at: str | None = Field(default=None, max_length=80)
    duration_minutes: int | None = Field(default=None, ge=5, le=480)
    participants: list[str] | None = None
    objective: str | None = Field(default=None, max_length=500)
    agenda_text: str | None = Field(default=None, max_length=2_000)
    participation_mode: Literal["self", "delegate"] | None = None
    model_provider_id: str | None = Field(default=None, max_length=80)
    workspace_id: str | None = Field(default=None, max_length=80)
    agent_identity_id: str | None = Field(default=None, max_length=80)
    authorization_rule_ids: list[str] | None = None
    auto_reply_enabled: bool | None = None

    @field_validator("title", "scenario", "meeting_type")
    @classmethod
    def strip_optional_required_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value


class MeetingAgendaUpdateRequest(BaseModel):
    agenda: list[AgendaItem] = Field(min_length=1)


class MeetingTranscriptRequest(BaseModel):
    transcript: str = Field(min_length=10, max_length=50_000)

    @field_validator("transcript")
    @classmethod
    def strip_transcript(cls, value: str) -> str:
        return value.strip()


class MeetingModelUpdateRequest(BaseModel):
    model_provider_id: str = Field(min_length=1, max_length=80)


class AgentControlRequest(BaseModel):
    action: Literal["start", "pause", "resume"]


class MeetingLifecycleRequest(BaseModel):
    action: Literal["start", "end", "reopen"]


class MicrophoneControlRequest(BaseModel):
    action: Literal["acquire", "release"]


class AgentQuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2_000)


class AgentQuestionResponse(BaseModel):
    answer: str
    evidence_object_ids: list[str] = Field(default_factory=list)
    model_provider_id: str
    mode: Literal["live", "local_rules"]


class MeetingConfirmationRequest(BaseModel):
    action: Literal["approve", "edit", "reject"]
    reply: str = Field(default="", max_length=2_000)


class EscalationResolveRequest(BaseModel):
    action: Literal["approve", "edit", "reject", "defer"]
    reply: str = Field(default="", max_length=2_000)


class ActionItemUpdateRequest(BaseModel):
    owner_id: str = Field(min_length=1, max_length=80)
    due_date: date


class Decision(BaseModel):
    id: str
    topic: str
    content: str
    owner_id: str | None = None
    due_date: str | None = None
    evidence: str


class ActionItem(BaseModel):
    id: str
    title: str
    owner_id: str | None = None
    due_date: str | None = None
    linked_decision_id: str
    status: Literal["draft", "incomplete", "pending_confirmation", "written_back", "writeback_failed"] = "incomplete"
    writeback_attempts: int = 0
    writeback_task_id: str | None = None
    writeback_error: str | None = None


class SentAgentReply(BaseModel):
    id: str
    content: str
    decision: Literal["suggested", "sent", "escalated"]
    evidence_object_ids: list[str] = Field(default_factory=list)
    authorization_rule_ids: list[str] = Field(default_factory=list)
    created_at: str


class AgentReply(BaseModel):
    question: str
    decision: str = Field(description="answer, confirm, or escalate")
    reply: str
    reason: str
    evidence_object_ids: list[str]


class TranscriptTurn(BaseModel):
    speaker: str
    content: str
    agent_action: str
    linked_object_ids: list[str]


class AdsRelation(BaseModel):
    source_id: str
    source_label: str
    relation: str
    target_id: str
    target_label: str


class AuditEvent(BaseModel):
    time: str
    actor: str
    action: str
    detail: str


class DemoMetrics(BaseModel):
    """Legacy response fields kept for old SQLite snapshots.

    New UI code must use ``WorkloadMetrics`` below. These strings are no
    longer populated with estimated productivity claims.
    """

    manual_minutes_effort: str | None = None
    agent_minutes_effort: str | None = None
    attention_saved: str | None = None
    tasks_created: int = 0
    escalations: int = 0

    @model_validator(mode="after")
    def clear_legacy_estimates(self):
        self.manual_minutes_effort = None
        self.agent_minutes_effort = None
        self.attention_saved = None
        return self


class WorkloadMetrics(BaseModel):
    """Measurements that can be traced to this meeting's stored workflow."""

    measurement_status: Literal["pending", "partial", "measured"] = "pending"
    data_source: str = "本场会议的系统记录"
    sample_count: int = 0
    user_attendance_minutes: float | None = None
    agent_processing_minutes: float | None = None
    decision_confirmation_minutes: float | None = None
    transcript_characters: int = 0
    minutes_generated_characters: int = 0
    minutes_edited_characters: int = 0
    action_items_created: int = 0
    action_items_written_back: int = 0
    escalations: int = 0
    baseline_status: Literal["pending", "available"] = "pending"
    baseline_minutes: float | None = None
    post_process_minutes: float | None = None
    savings_percent: float | None = None


class EscalationRequest(BaseModel):
    id: str
    meeting_id: str
    question: str
    reason: str
    evidence_object_ids: list[str]
    ai_recommendation: str
    status: Literal["pending", "deferred", "approved", "edited", "rejected", "expired"] = "pending"
    user_reply: str | None = None
    created_at: str
    updated_at: str
    reply_deadline: str | None = None


class MeetingAnalysis(BaseModel):
    meeting_id: str
    prompt_version: str = "meeting-agent.v1"
    pre_meeting_brief: str
    agenda: list[AgendaItem]
    transcript_turns: list[TranscriptTurn]
    structured_minutes: str
    decisions: list[Decision]
    action_items: list[ActionItem]
    agent_replies: list[AgentReply]
    writeback_tasks: list[Task]
    ads_relations: list[AdsRelation]
    audit_events: list[AuditEvent]
    demo_metrics: DemoMetrics
    metrics: WorkloadMetrics = Field(default_factory=WorkloadMetrics)
    export_markdown: str


class ModelConfig(BaseModel):
    provider_id: str
    provider_name: str
    adapter_type: Literal["deepseek", "openai_compatible", "mock"]
    base_url: str
    model: str
    enabled: bool = True
    is_default: bool = False
    configured: bool = False
    connection_status: Literal["not_configured", "untested", "ok", "failed", "mock"] = "not_configured"
    last_tested_at: str | None = None
    message: str = ""
    api_key_masked: str = ""
    vendor_id: str = "generic"
    capabilities: list[str] = Field(default_factory=lambda: ["chat", "structured_output"])


class AiRuntimeStatus(BaseModel):
    mode: Literal["mock", "live"]
    label: str
    message: str


class ModelConfigUpdateRequest(BaseModel):
    provider_id: str = Field(min_length=1, max_length=80)
    provider_name: str = Field(min_length=1, max_length=120)
    adapter_type: Literal["deepseek", "openai_compatible", "mock"]
    base_url: str = Field(min_length=1, max_length=300)
    model: str = Field(min_length=1, max_length=120)
    api_key: str = Field(default="", max_length=300)
    enabled: bool = True
    is_default: bool = False


class SpeechHealth(BaseModel):
    status: Literal["ready", "degraded", "not_configured"]
    provider: str
    ffmpeg_available: bool
    model_available: bool
    model_name: str
    device: str
    compute_type: str
    message: str
    diarization_available: bool = False
    diarization_model_name: str | None = None


class SpeechSetupStatus(BaseModel):
    state: Literal[
        "idle",
        "unsupported",
        "installing_dependencies",
        "downloading_assets",
        "verifying",
        "restart_required",
        "failed",
    ]
    supported: bool
    python_version: str
    python_bits: int
    progress: int = Field(ge=0, le=100)
    message: str
    restart_required: bool = False
    error: str = ""
    updated_at: str


class TranscriptSegment(BaseModel):
    id: str
    sequence: int
    start_seconds: float
    end_seconds: float
    original_text: str
    revised_text: str
    speaker_label: str
    speaker_ambiguous: bool = False


class TranscriptRevision(BaseModel):
    id: str
    segment_id: str | None = None
    previous_text: str
    revised_text: str
    revised_at: str


class SpeechJob(BaseModel):
    id: str
    meeting_id: str
    source_type: Literal["microphone", "upload", "text_stub"]
    original_name: str
    status: Literal[
        "uploaded",
        "preprocessing",
        "transcribing",
        "diarizing",
        "awaiting_review",
        "confirmed",
        "failed",
        "cancelled",
    ]
    progress: int
    language: str
    model_name: str
    device: str
    compute_type: str
    full_text: str
    segments: list[TranscriptSegment] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    created_at: str
    updated_at: str
    mime_type: str = ""
    size_bytes: int = 0
    duration_seconds: float | None = None
    processing_seconds: float | None = None
    attempt: int = 1
    revisions: list[TranscriptRevision] = Field(default_factory=list)
    diarization_enabled: bool = False
    requested_speaker_count: int | None = Field(default=None, ge=2, le=10)
    detected_speaker_count: int | None = None
    diarization_model: str | None = None
    diarization_warning: str | None = None


class SpeechJobCreateRequest(BaseModel):
    meeting_id: str
    source_type: Literal["microphone", "upload", "text_stub"] = "text_stub"
    original_name: str = Field(default="会议音频片段", max_length=160)
    stub_text: str = Field(
        default="李娜：本段语音已转写为会议发言，请确认后进入智能分析。",
        min_length=2,
        max_length=20_000,
    )
    language: str = Field(default="zh", max_length=20)


class TranscriptSegmentUpdateRequest(BaseModel):
    revised_text: str = Field(min_length=1, max_length=10_000)
    speaker_label: str = Field(min_length=1, max_length=80)


class TranscriptFullTextUpdateRequest(BaseModel):
    full_text: str = Field(min_length=1, max_length=100_000)


class SpeechConfirmResponse(BaseModel):
    job: SpeechJob
    transcript: str


class SpeechJobActionRequest(BaseModel):
    action: Literal["cancel", "retry"]


class MeetingSession(BaseModel):
    id: str
    title: str
    scenario: str
    status: Literal[
        "draft",
        "prepared",
        "awaiting_confirmation",
        "confirmed",
        "rejected",
        "completed",
    ]
    meeting_status: Literal["draft", "scheduled", "in_progress", "ended", "closed", "cancelled"] = "draft"
    agent_session_state: Literal["not_started", "preparing", "delegating", "paused", "completed", "failed"] = "not_started"
    participation_mode: Literal["self", "delegate"] = "self"
    model_provider_id: str = "deepseek"
    workspace_id: str | None = None
    agent_identity_id: str | None = None
    authorization_rule_ids: list[str] = Field(default_factory=list)
    auto_reply_enabled: bool = False
    series_id: str | None = None
    occurrence_index: int = 0
    recurrence: RecurrenceRule = Field(default_factory=RecurrenceRule)
    sent_agent_replies: list[SentAgentReply] = Field(default_factory=list)
    meeting_type: str = "项目周例会"
    scheduled_at: str = "2026-08-20 14:00"
    end_at: str | None = None
    duration_minutes: int = 45
    participants: list[str] = Field(default_factory=list)
    objective: str = ""
    agenda_text: str = ""
    transcript: str = ""
    pre_meeting_brief: str = ""
    agenda: list[AgendaItem] = Field(default_factory=list)
    agenda_edited: bool = False
    analysis: MeetingAnalysis | None = None
    escalation_requests: list[EscalationRequest] = Field(default_factory=list)
    confirmation_action: str | None = None
    confirmation_reply: str | None = None
    audit_events: list[AuditEvent] = Field(default_factory=list)
    created_at: str
    updated_at: str


class MeetingSummary(BaseModel):
    id: str
    title: str
    scenario: str
    status: str
    scheduled_at: str = ""
    series_id: str | None = None
    occurrence_index: int = 0
    recurrence: RecurrenceRule = Field(default_factory=RecurrenceRule)
    created_at: str
    updated_at: str


class ModelCallAudit(BaseModel):
    id: str
    meeting_id: str | None = None
    provider_id: str
    model: str
    operation: str
    status: Literal["success", "failed", "fallback"]
    duration_ms: int
    prompt_version: str
    token_usage: int | None = None
    error: str = ""
    created_at: str


class ProviderDefinition(BaseModel):
    vendor_id: str
    name: str
    adapter_type: Literal["deepseek", "openai_compatible"]
    default_base_url: str
    default_model: str
    capabilities: list[str] = Field(default_factory=lambda: ["chat", "structured_output"])


class MetricBaseline(BaseModel):
    id: str
    meeting_id: str = ""
    meeting_type: str
    baseline_minutes: float = Field(gt=0)
    post_process_minutes: float = Field(ge=0)
    sample_date: str
    source: str
    notes: str = ""


class DataOverview(BaseModel):
    database_bytes: int
    audio_bytes: int
    meetings: int
    workspaces: int
    speech_jobs: int
    backups: list[str] = Field(default_factory=list)


class BackupResponse(BaseModel):
    filename: str
    created_at: str
    size_bytes: int


class RestoreRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=200)


class CleanupRequest(BaseModel):
    include_confirmed: bool = False


class OperationResult(BaseModel):
    ok: bool = True
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)
