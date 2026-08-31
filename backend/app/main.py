import logging
import uuid
import shutil
import time
from calendar import monthrange
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal

import os

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.ai import (
    answer_agent_question,
    build_agenda_draft,
    build_local_agenda_draft,
    build_model_analysis,
    default_model_configs,
    find_escalation_match,
    mock_ai_enabled,
    provider_ready,
    test_chat_completion,
)
from app.mock_data import AUTHORIZATION_RULES, OBJECTIVES, PEOPLE, TASKS
from app.prompt_templates import PROMPT_VERSION
from app.models import (
    ActionItemUpdateRequest,
    AgentReply,
    AgentQuestionRequest,
    AgentQuestionResponse,
    AiRuntimeStatus,
    AgentControlRequest,
    AdsWorkspace,
    AdsWorkspacePayload,
    AppSettings,
    AppSettingsUpdateRequest,
    AgendaItem,
    AgendaDraftRequest,
    AgendaDraftResponse,
    AuditEvent,
    BackupResponse,
    CleanupRequest,
    DataOverview,
    Decision,
    EscalationResolveRequest,
    EscalationRequest,
    MeetingAnalysis,
    MeetingAnalysisRequest,
    MeetingConfirmationRequest,
    MeetingCreateRequest,
    MeetingAgendaUpdateRequest,
    MeetingLifecycleRequest,
    MigrationChoiceRequest,
    MeetingModelUpdateRequest,
    MetricBaseline,
    MicrophoneControlRequest,
    ModelCallAudit,
    MeetingSession,
    MeetingSummary,
    MeetingUpdateRequest,
    ModelConfig,
    ModelConfigUpdateRequest,
    OnboardingRequest,
    OperationResult,
    Person,
    ProviderDefinition,
    RestoreRequest,
    RecurrenceRule,
    SentAgentReply,
    SpeechConfirmResponse,
    SpeechHealth,
    SpeechSetupStatus,
    SpeechJob,
    SpeechJobCreateRequest,
    TranscriptFullTextUpdateRequest,
    TranscriptSegment,
    TranscriptRevision,
    TranscriptSegmentUpdateRequest,
    MeetingTranscriptRequest,
    Task,
)
from app.speech_setup import get_status as get_speech_setup_status
from app.speech_setup import start_setup as start_speech_setup
from app.storage import (
    BACKUP_DIR,
    DB_PATH,
    complete_meeting_with_tasks,
    create_backup,
    create_ads_workspace,
    create_meeting,
    data_counts,
    delete_ads_workspace,
    delete_meeting,
    delete_speech_job,
    get_ads_workspace,
    get_app_settings,
    has_app_settings,
    get_microphone_owner,
    get_model_secret,
    get_meeting,
    get_speech_job,
    init_db,
    list_all_speech_jobs,
    list_backups,
    list_metric_baselines,
    list_model_call_audits,
    list_model_configs,
    list_ads_workspaces,
    list_meetings,
    list_meeting_sessions,
    list_persisted_tasks,
    list_speech_jobs,
    persist_tasks,
    save_meeting,
    save_app_settings,
    save_metric_baseline,
    save_model_call_audit,
    save_ads_workspace,
    save_speech_job,
    set_ads_workspace_archived,
    set_microphone_owner,
    reset_product_data,
    restore_backup,
    upsert_model_config,
)
from app.providers import PROVIDER_REGISTRY, provider_definition
from app.diarization import (
    MODEL_NAME as DIARIZATION_MODEL_NAME,
    assign_speakers,
    diarize,
    runtime as diarization_runtime,
)
from app.speech import (
    AUDIO_ROOT,
    COMPUTE_TYPE,
    DEVICE,
    MAX_AUDIO_SECONDS,
    MODEL_NAME,
    delete_audio_assets,
    normalized_audio_path,
    probe_duration,
    runtime as speech_runtime,
    save_upload,
    source_for_job,
    transcribe,
)

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(_: FastAPI):
    startup()
    yield


app = FastAPI(title="ADS 会议智能体", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def startup() -> None:
    init_db()
    recover_interrupted_speech_jobs()
    cleanup_expired_audio_assets()
    configs = list_model_configs()
    if not configs:
        for config in default_model_configs():
            upsert_model_config(config)
        return
    defaults = {config.provider_id: config for config in default_model_configs()}
    for config in configs:
        baseline = defaults.get(config.provider_id)
        if baseline is None:
            continue
        if config.adapter_type == "mock" or "演示" in config.provider_name or "演示" in config.message:
            config.provider_name = baseline.provider_name
            config.message = baseline.message
            upsert_model_config(config)


def recover_interrupted_speech_jobs() -> None:
    """Make jobs left in an in-flight state recoverable after a service restart."""
    interrupted_statuses = {"uploaded", "preprocessing", "transcribing", "diarizing"}
    for job in list_all_speech_jobs():
        if job.status not in interrupted_statuses:
            continue
        job.status = "failed"
        job.error_code = "service_restarted"
        job.error_message = "服务已重启，未完成的转写已暂停。原始音频仍保留，可重新转写。"
        save_speech_job(job)


def cleanup_expired_audio_assets() -> int:
    days = get_app_settings().audio_retention_days
    if not days:
        return 0
    cutoff = datetime.now().astimezone() - timedelta(days=days)
    cleaned = 0
    for job in list_all_speech_jobs():
        source = source_for_job(job.id)
        if job.status in {"failed", "cancelled", "confirmed"} and source and datetime.fromtimestamp(source.stat().st_mtime).astimezone() <= cutoff:
            delete_audio_assets(job.id); cleaned += 1
    return cleaned


def _event(action: str, detail: str, actor: str = "ADS 会议智能体") -> AuditEvent:
    return AuditEvent(
        time=datetime.now().astimezone().isoformat(timespec="seconds"),
        actor=actor,
        action=action,
        detail=detail,
    )


def _require_meeting(meeting_id: str) -> MeetingSession:
    meeting = get_meeting(meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="会议不存在")
    return meeting


def _require_status(meeting: MeetingSession, allowed: set[str]) -> None:
    if meeting.status not in allowed:
        expected = "、".join(sorted(allowed))
        raise HTTPException(
            status_code=409,
            detail=f"当前状态 {meeting.status} 不允许此操作，需要状态：{expected}",
        )


def _meeting_people(meeting: MeetingSession):
    workspace = get_ads_workspace(meeting.workspace_id) if meeting.workspace_id else None
    return workspace.people if workspace is not None else []


def _person_name(person_id: str | None, people=PEOPLE) -> str:
    if person_id is None:
        return "待确认"
    return next((person.name for person in people if person.id == person_id), person_id)


def _valid_due_date(value: str | None) -> bool:
    if not value:
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def expand_occurrence_starts(start_at: str, rule: RecurrenceRule, limit: int = 100) -> list[str]:
    start = datetime.fromisoformat(start_at.replace("T", " "))
    if rule.frequency == "none":
        return [start.strftime("%Y-%m-%d %H:%M")]
    end = date.fromisoformat(rule.end_date or "")
    starts: list[str] = []
    index = 0
    while True:
        if rule.frequency == "monthly":
            month_index = start.month - 1 + index
            year, month_zero_based = divmod(start.year * 12 + month_index, 12)
            month = month_zero_based + 1
            current = start.replace(
                year=year,
                month=month,
                day=min(start.day, monthrange(year, month)[1]),
            )
        else:
            interval_days = 7 if rule.frequency == "weekly" else 14
            current = start + timedelta(days=interval_days * index)
        if current.date() > end:
            break
        starts.append(current.strftime("%Y-%m-%d %H:%M"))
        if len(starts) > limit:
            raise HTTPException(status_code=422, detail=f"单个循环系列最多生成 {limit} 场会议")
        index += 1
    return starts


def _action_status(owner_id: str | None, due_date: str | None) -> str:
    return "pending_confirmation" if owner_id and _valid_due_date(due_date) else "incomplete"


def _split_stub_segments(text: str) -> list[TranscriptSegment]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        lines = [text.strip()]
    segments: list[TranscriptSegment] = []
    cursor = 0.0
    for index, line in enumerate(lines, start=1):
        speaker = "发言人 1"
        content = line
        if "：" in line:
            speaker, content = line.split("：", 1)
        elif ":" in line:
            speaker, content = line.split(":", 1)
        duration = max(4.0, min(18.0, len(content) / 6))
        segments.append(
            TranscriptSegment(
                id=f"seg_{index:04d}",
                sequence=index,
                start_seconds=round(cursor, 1),
                end_seconds=round(cursor + duration, 1),
                original_text=content.strip(),
                revised_text=content.strip(),
                speaker_label=speaker.strip() or "发言人 1",
            )
        )
        cursor += duration
    return segments


def _sync_segments_from_full_text(
    text: str, existing: list[TranscriptSegment]
) -> list[TranscriptSegment]:
    parsed = _split_stub_segments(text)
    synchronized: list[TranscriptSegment] = []
    for index, item in enumerate(parsed):
        if index < len(existing):
            current = existing[index]
            current.sequence = index + 1
            current.speaker_label = item.speaker_label
            current.revised_text = item.revised_text
            synchronized.append(current)
        else:
            item.id = f"seg_{uuid.uuid4().hex[:8]}"
            synchronized.append(item)
    return synchronized


def _build_final_markdown(meeting: MeetingSession, tasks: list[Task]) -> str:
    analysis = meeting.analysis
    if analysis is None:
        return ""
    people = _meeting_people(meeting)
    decision_lines = "\n".join(
        f"- {decision.content}（负责人：{_person_name(decision.owner_id, people)}；截止：{decision.due_date or '待确认'}；依据：{decision.evidence}）"
        for decision in analysis.decisions
    )
    task_lines = "\n".join(
        f"- [{task.status}] {task.title}（负责人：{_person_name(task.owner_id, people)}；截止：{task.due_date}；任务 ID：{task.id}）"
        for task in tasks
    )
    audit_lines = "\n".join(
        f"- {event.time} · {event.actor} · {event.action}：{event.detail}"
        for event in meeting.audit_events
    )
    confirmation = meeting.confirmation_reply or "本次会议未触发额外本人确认。"
    return (
        f"# {meeting.title}\n\n"
        f"- 会议 ID：{meeting.id}\n"
        f"- 最终状态：{meeting.status}\n\n"
        f"## 会前简报\n{meeting.pre_meeting_brief}\n\n"
        f"## 结构化纪要\n{analysis.structured_minutes}\n\n"
        f"## 决策与依据\n{decision_lines or '- 无'}\n\n"
        f"## 本人确认\n{confirmation}\n\n"
        f"## 已回写 ADS 任务\n{task_lines or '- 无'}\n\n"
        f"## 审计记录\n{audit_lines or '- 无'}\n"
    )


def _build_analysis_markdown(meeting: MeetingSession) -> str:
    analysis = meeting.analysis
    if analysis is None:
        return ""
    people = _meeting_people(meeting)
    decision_lines = "\n".join(
        f"- {item.content}（负责人：{_person_name(item.owner_id, people)}；截止：{item.due_date or '待确认'}；依据：{item.evidence}）"
        for item in analysis.decisions
    )
    action_lines = "\n".join(
        f"- [{item.status}] {item.title}（负责人：{_person_name(item.owner_id, people)}；截止：{item.due_date or '待确认'}）"
        for item in analysis.action_items
    )
    reply_lines = "\n".join(
        f"- {item.question}：{item.reply}（{item.reason}）"
        for item in analysis.agent_replies
    )
    return (
        f"# {meeting.title}\n\n"
        f"## 会前简报\n{meeting.pre_meeting_brief}\n\n"
        f"## 当前有效结构化纪要\n{analysis.structured_minutes}\n\n"
        f"## 决策与依据\n{decision_lines or '- 无'}\n\n"
        f"## 行动项\n{action_lines or '- 无'}\n\n"
        f"## 智能体判断\n{reply_lines or '- 无'}\n"
    )


def _rebuild_structured_minutes(meeting: MeetingSession) -> None:
    if meeting.analysis is None:
        return
    people = _meeting_people(meeting)

    def clean(value: str) -> str:
        return value.strip().rstrip("。；;,.， ")

    decisions = "；".join(clean(item.content) for item in meeting.analysis.decisions)
    actions = "；".join(
        f"{clean(item.title)}（负责人：{_person_name(item.owner_id, people)}；截止：{item.due_date or '待确认'}）"
        for item in meeting.analysis.action_items
    )
    meeting.analysis.structured_minutes = (
        f"当前有效决策：{decisions or '无'}。"
        f"当前有效行动项：{actions or '无'}。"
    )


def _merge_analysis(previous: MeetingAnalysis | None, current: MeetingAnalysis) -> MeetingAnalysis:
    if previous is None:
        return current
    current.transcript_turns = [*previous.transcript_turns, *current.transcript_turns]
    current.decisions = [*previous.decisions, *current.decisions]
    current.action_items = [*previous.action_items, *current.action_items]
    current.agent_replies = [*previous.agent_replies, *current.agent_replies]
    current.writeback_tasks = [*previous.writeback_tasks, *current.writeback_tasks]
    current.ads_relations = [*previous.ads_relations, *current.ads_relations]
    current.audit_events = [*previous.audit_events, *current.audit_events]
    current.demo_metrics.tasks_created += previous.demo_metrics.tasks_created
    current.demo_metrics.escalations += previous.demo_metrics.escalations
    return current


def _refresh_workload_metrics(meeting: MeetingSession) -> None:
    """Refresh only values that can be derived from the stored workflow."""
    if meeting.analysis is None:
        return
    metrics = meeting.analysis.metrics
    meeting.analysis.prompt_version = PROMPT_VERSION
    metrics.measurement_status = "partial"
    metrics.data_source = "本场会议的系统记录"
    metrics.sample_count = 1
    metrics.transcript_characters = len(meeting.transcript)
    metrics.minutes_generated_characters = len(meeting.analysis.structured_minutes)
    metrics.action_items_created = len(meeting.analysis.action_items)
    metrics.action_items_written_back = len(meeting.analysis.writeback_tasks)
    metrics.escalations = len(meeting.escalation_requests)
    metrics.baseline_status = "pending"
    metrics.baseline_minutes = None
    metrics.post_process_minutes = None
    metrics.savings_percent = None


def _remove_discarded_escalation_outputs(meeting: MeetingSession) -> set[str]:
    if meeting.analysis is None:
        return set()
    discarded_questions = {
        item.question.strip()
        for item in meeting.escalation_requests
        if item.status in {"edited", "rejected"} and item.question.strip()
    }
    if not discarded_questions:
        return set()

    def matches_discarded(*values: str | None) -> bool:
        text = "\n".join(value or "" for value in values)
        return any(question in text for question in discarded_questions)

    discarded_decision_ids = {
        decision.id
        for decision in meeting.analysis.decisions
        if matches_discarded(decision.content, decision.evidence)
    }
    discarded_action_ids = {
        item.id
        for item in meeting.analysis.action_items
        if item.linked_decision_id in discarded_decision_ids or matches_discarded(item.title)
    }
    meeting.analysis.decisions = [
        decision for decision in meeting.analysis.decisions if decision.id not in discarded_decision_ids
    ]
    meeting.analysis.action_items = [
        item
        for item in meeting.analysis.action_items
        if item.id not in discarded_action_ids
    ]
    meeting.analysis.agent_replies = [
        reply
        for reply in meeting.analysis.agent_replies
        if not matches_discarded(reply.question, reply.reply, reply.reason)
    ]
    discarded_ids = discarded_decision_ids | discarded_action_ids
    meeting.analysis.ads_relations = [
        relation
        for relation in meeting.analysis.ads_relations
        if relation.source_id not in discarded_ids
        and relation.target_id not in discarded_ids
        and not matches_discarded(relation.source_label, relation.target_label)
    ]
    return discarded_decision_ids


def _resolve_escalation(
    meeting: MeetingSession,
    escalation: EscalationRequest,
    action: str,
    reply: str,
) -> MeetingSession:
    if escalation.status not in {"pending", "deferred"}:
        raise HTTPException(status_code=409, detail="该确认事项已处理")
    escalation.status = (
        "deferred" if action == "defer" else
        "edited" if action == "edit" else
        "approved" if action == "approve" else "rejected"
    )
    escalation.user_reply = reply.strip()
    escalation.updated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    meeting.confirmation_action = action
    meeting.confirmation_reply = escalation.user_reply
    if action in {"edit", "reject"}:
        _remove_discarded_escalation_outputs(meeting)
        if action == "edit" and escalation.user_reply:
            meeting.analysis.decisions.append(
                Decision(
                    id=f"dec_{uuid.uuid4().hex[:8]}",
                    topic="本人修改确认",
                    content=escalation.user_reply,
                    evidence="本人修改确认，原提案与回复详见审计记录。",
                )
            )
        _rebuild_structured_minutes(meeting)
        _refresh_workload_metrics(meeting)
        if meeting.analysis is not None:
            meeting.analysis.export_markdown = _build_analysis_markdown(meeting)
    pending_count = sum(1 for item in meeting.escalation_requests if item.status in {"pending", "deferred"})
    meeting.status = "awaiting_confirmation" if pending_count else "confirmed"
    meeting.agent_session_state = "delegating" if meeting.meeting_status == "in_progress" else "completed"
    labels = {
        "approve": "确认代理提案",
        "edit": "修改后确认",
        "reject": "拒绝代理提案",
        "defer": "暂不处理",
    }
    meeting.audit_events.append(
        _event(
            labels[action],
            escalation.user_reply or ("本人拒绝该超权事项，其他会议成果继续处理。" if action == "reject" else "本人允许继续执行。"),
            "本人",
        )
    )
    if action != "defer":
        meeting.audit_events.append(
            _event(
                "回复会议",
                f"已将本人决定返回原会议：{escalation.user_reply or '继续按授权范围执行。'}",
                "ADS 会议智能体",
            )
        )
    return save_meeting(meeting)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "storage": "sqlite", "workflow": "state-machine"}


@app.get("/api/setup")
def setup_status() -> dict:
    settings = get_app_settings()
    workspaces = list_ads_workspaces()
    migration_required = bool(workspaces) and not has_app_settings()
    return {
        "requires_onboarding": (not settings.onboarding_complete or not workspaces) and not migration_required,
        "requires_migration_choice": migration_required,
        "settings": settings.model_dump(),
        "workspace_count": len([item for item in workspaces if not item.archived]),
        "speech": speech_health().model_dump(),
        "ai": ai_status().model_dump(),
    }


@app.post("/api/setup/migrate", response_model=AppSettings)
def migrate_existing_workspace(payload: MigrationChoiceRequest) -> AppSettings:
    settings = get_app_settings()
    workspaces = list_ads_workspaces()
    if payload.action == "create_blank":
        settings.onboarding_complete = False
        return save_app_settings(settings)
    if not workspaces:
        raise HTTPException(status_code=409, detail="没有可继续使用的旧工作区")
    workspace = workspaces[0]
    settings.onboarding_complete = True
    settings.active_workspace_id = workspace.id
    if workspace.people:
        person = workspace.people[0]
        settings.active_identity_id = person.id
        settings.identities = [person]
    return save_app_settings(settings)


@app.get("/api/settings", response_model=AppSettings)
def app_settings() -> AppSettings:
    return get_app_settings()


@app.put("/api/settings", response_model=AppSettings)
def update_app_settings(payload: AppSettingsUpdateRequest) -> AppSettings:
    settings = get_app_settings()
    if payload.audio_retention_days is not None:
        settings.audio_retention_days = payload.audio_retention_days
    if payload.identity is not None:
        settings.identities = [
            payload.identity if item.id == payload.identity.id else item
            for item in settings.identities
        ] if any(item.id == payload.identity.id for item in settings.identities) else [*settings.identities, payload.identity]
        settings.active_identity_id = payload.identity.id
        workspace = get_ads_workspace(settings.active_workspace_id) if settings.active_workspace_id else None
        if workspace is not None:
            person = Person.model_validate(payload.identity.model_dump())
            workspace.people = [
                person if item.id == person.id else item for item in workspace.people
            ] if any(item.id == person.id for item in workspace.people) else [*workspace.people, person]
            save_ads_workspace(workspace.id, AdsWorkspacePayload.model_validate(workspace.model_dump()))
    if payload.active_identity_id is not None:
        if not any(item.id == payload.active_identity_id for item in settings.identities):
            raise HTTPException(status_code=422, detail="所选本人身份不存在")
        settings.active_identity_id = payload.active_identity_id
    return save_app_settings(settings)


@app.post("/api/onboarding")
def complete_onboarding(payload: OnboardingRequest) -> dict:
    settings = get_app_settings()
    identity = payload.identity
    if not identity.description.strip():
        duty = identity.role.strip() or "团队成员"
        scope = payload.workspace_description.strip() or f"{payload.workspace_name}工作区"
        identity = identity.model_copy(
            update={
                "description": (
                    f"{identity.name}的 AI 分身，岗位或职责为{duty}。"
                    f"在{payload.workspace_name}中围绕{scope}协助准备会议、整理信息并遵守本人授权边界。"
                )
            }
        )
    if any(item.id == identity.id for item in settings.identities):
        settings.identities = [
            identity if item.id == identity.id else item for item in settings.identities
        ]
    else:
        settings.identities.append(identity)
    workspace = create_ads_workspace(
        f"ws_{uuid.uuid4().hex[:8]}",
        AdsWorkspacePayload(
            name=payload.workspace_name,
            description=payload.workspace_description,
            people=[
                {
                    "id": identity.id,
                    "name": identity.name,
                    "role": identity.role,
                }
            ],
        ),
    )
    settings.active_identity_id = identity.id
    settings.active_workspace_id = workspace.id
    settings.onboarding_complete = True
    save_app_settings(settings)
    return {"settings": settings.model_dump(), "workspace": workspace.model_dump()}


@app.get("/api/ads")
def get_ads_context() -> dict[str, list[dict]]:
    workspaces = list_ads_workspaces()
    workspace = workspaces[0] if workspaces else None
    persisted = list_persisted_tasks()
    if workspace is not None:
        persisted_ids = {task.id for task in persisted}
        tasks = [*persisted, *(task for task in workspace.tasks if task.id not in persisted_ids)]
        return {
            "people": [person.model_dump() for person in workspace.people],
            "projects": [item.model_dump() for item in workspace.projects],
            "objectives": [objective.model_dump() for objective in workspace.objectives],
            "metrics": [item.model_dump() for item in workspace.metrics],
            "risks": [item.model_dump() for item in workspace.risks],
            "tasks": [task.model_dump() for task in tasks],
            "policies": [item.model_dump() for item in workspace.policies],
            "historical_stances": [item.model_dump() for item in workspace.historical_stances],
            "authorization_rules": [rule.model_dump() for rule in workspace.authorization_rules],
        }
    return {
        "people": [], "projects": [], "objectives": [], "metrics": [], "risks": [],
        "tasks": [], "policies": [], "historical_stances": [], "authorization_rules": [],
    }


@app.get("/api/workspaces", response_model=list[AdsWorkspace])
def workspaces() -> list[AdsWorkspace]:
    return list_ads_workspaces()


@app.post("/api/workspaces", response_model=AdsWorkspace)
def add_workspace(payload: AdsWorkspacePayload) -> AdsWorkspace:
    return create_ads_workspace(f"ws_{uuid.uuid4().hex[:8]}", payload)


@app.get("/api/workspaces/{workspace_id}", response_model=AdsWorkspace)
def workspace_detail(workspace_id: str) -> AdsWorkspace:
    workspace = get_ads_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="ADS 工作区不存在")
    return workspace


@app.put("/api/workspaces/{workspace_id}", response_model=AdsWorkspace)
def update_workspace(workspace_id: str, payload: AdsWorkspacePayload) -> AdsWorkspace:
    workspace = save_ads_workspace(workspace_id, payload)
    if workspace is None:
        raise HTTPException(status_code=404, detail="ADS 工作区不存在")
    return workspace


@app.patch("/api/workspaces/{workspace_id}/archive", response_model=AdsWorkspace)
def archive_workspace(workspace_id: str, archived: bool = True) -> AdsWorkspace:
    workspace = set_ads_workspace_archived(workspace_id, archived)
    if workspace is None:
        raise HTTPException(status_code=404, detail="ADS 工作区不存在")
    return workspace


@app.delete("/api/workspaces/{workspace_id}", response_model=OperationResult)
def remove_workspace(workspace_id: str) -> OperationResult:
    if get_ads_workspace(workspace_id) is None:
        raise HTTPException(status_code=404, detail="ADS 工作区不存在")
    if not delete_ads_workspace(workspace_id):
        raise HTTPException(status_code=409, detail="工作区仍有关联会议，请先归档而不是删除")
    return OperationResult(message="工作区已删除")


@app.get("/api/providers", response_model=list[ProviderDefinition])
def providers() -> list[ProviderDefinition]:
    return PROVIDER_REGISTRY


@app.post("/api/providers/{vendor_id}/install", response_model=ModelConfig)
def install_provider(vendor_id: str) -> ModelConfig:
    definition = provider_definition(vendor_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="模型厂商不存在")
    configs = list_model_configs()
    provider_id = vendor_id
    suffix = 2
    existing_ids = {item.provider_id for item in configs}
    while provider_id in existing_ids:
        provider_id = f"{vendor_id}-{suffix}"
        suffix += 1
    config = ModelConfig(
        provider_id=provider_id,
        provider_name=definition.name,
        adapter_type=definition.adapter_type,
        base_url=definition.default_base_url,
        model=definition.default_model,
        enabled=True,
        configured=False,
        connection_status="not_configured",
        message="已添加配置，请填写 API Key 并测试连接。",
        vendor_id=definition.vendor_id,
        capabilities=definition.capabilities,
    )
    return upsert_model_config(config)


@app.get("/api/models", response_model=list[ModelConfig])
def models() -> list[ModelConfig]:
    configs = list_model_configs()
    return configs or default_model_configs()


@app.get("/api/model-audits", response_model=list[ModelCallAudit])
def model_audits() -> list[ModelCallAudit]:
    return list_model_call_audits()


@app.get("/api/ai/status", response_model=AiRuntimeStatus)
def ai_status() -> AiRuntimeStatus:
    if mock_ai_enabled():
        return AiRuntimeStatus(
            mode="mock",
            label="本地规则模式",
            message="当前会议分析使用本地规则，不调用在线大模型。",
        )
    return AiRuntimeStatus(
        mode="live",
        label="在线模型",
        message="当前会议分析将使用所选在线模型；未配置可用密钥时会回退到本地规则。",
    )


@app.put("/api/models/{provider_id}", response_model=ModelConfig)
def save_model(provider_id: str, payload: ModelConfigUpdateRequest) -> ModelConfig:
    if provider_id != payload.provider_id:
        raise HTTPException(status_code=422, detail="provider_id 不一致")
    existing = next(
        (item for item in list_model_configs() if item.provider_id == provider_id),
        None,
    )
    stored_key = get_model_secret(provider_id)
    configured = bool(payload.api_key or stored_key)
    connection_changed = bool(payload.api_key) or existing is None or any(
        (
            existing.adapter_type != payload.adapter_type,
            existing.base_url.rstrip("/") != payload.base_url.rstrip("/"),
            existing.model != payload.model,
        )
    )
    if payload.adapter_type == "mock":
        connection_status = "mock"
        last_tested_at = existing.last_tested_at if existing else None
        message = "本地规则模式可用，不调用在线大模型。"
    elif connection_changed:
        connection_status = "untested" if configured else "not_configured"
        last_tested_at = None
        message = "已保存配置，请测试连接。"
    else:
        connection_status = existing.connection_status
        last_tested_at = existing.last_tested_at
        message = existing.message
    config = ModelConfig(
        provider_id=payload.provider_id,
        provider_name=payload.provider_name,
        adapter_type=payload.adapter_type,
        base_url=payload.base_url.rstrip("/"),
        model=payload.model,
        enabled=payload.enabled,
        is_default=payload.is_default,
        configured=configured,
        connection_status=connection_status,
        last_tested_at=last_tested_at,
        message=message,
        api_key_masked="已配置" if configured else "",
        vendor_id=existing.vendor_id if existing else "generic",
        capabilities=existing.capabilities if existing else ["chat", "structured_output"],
    )
    return upsert_model_config(config, payload.api_key)


@app.post("/api/models/{provider_id}/test", response_model=ModelConfig)
async def test_model(provider_id: str) -> ModelConfig:
    configs = {config.provider_id: config for config in (list_model_configs() or default_model_configs())}
    config = configs.get(provider_id)
    if config is None:
        raise HTTPException(status_code=404, detail="模型配置不存在")
    if config.adapter_type == "mock":
        config.connection_status = "mock"
        config.configured = True
        config.message = "本地规则模式可用，不调用在线大模型。"
        return upsert_model_config(config)
    api_key = get_model_secret(provider_id)
    if not api_key:
        env_key = "DEEPSEEK_API_KEY" if provider_id == "deepseek" else "OPENAI_COMPATIBLE_API_KEY"
        api_key = os.getenv(env_key, "") or (os.getenv("OPENAI_API_KEY", "") if provider_id != "deepseek" else "")
    ok, message = await test_chat_completion(config.base_url, api_key, config.model)
    config.configured = bool(api_key)
    config.connection_status = "ok" if ok else "failed"
    config.last_tested_at = datetime.now().astimezone().isoformat(timespec="seconds")
    config.message = message
    config.api_key_masked = "已配置" if api_key else ""
    return upsert_model_config(config)


@app.get("/api/speech/health", response_model=SpeechHealth)
def speech_health() -> SpeechHealth:
    current = speech_runtime()
    diarization = diarization_runtime()
    ready = current.ready and diarization.ready
    if current.ready and not diarization.ready:
        message = f"离线语音转写可用；{diarization.message}，可关闭说话人分离后继续"
    elif ready:
        message = "离线语音转写与匿名说话人分离可用"
    else:
        message = current.message
    return SpeechHealth(
        status="ready" if ready else "degraded",
        provider="FasterWhisperProvider + SherpaOnnx",
        ffmpeg_available=current.ffmpeg_available,
        model_available=current.model_available,
        model_name=MODEL_NAME,
        device=DEVICE,
        compute_type=COMPUTE_TYPE,
        message=message,
        diarization_available=diarization.ready,
        diarization_model_name=DIARIZATION_MODEL_NAME,
    )


@app.get("/api/speech/setup/status", response_model=SpeechSetupStatus)
def speech_setup_status() -> SpeechSetupStatus:
    return SpeechSetupStatus(**get_speech_setup_status())


@app.post("/api/speech/setup/start", response_model=SpeechSetupStatus)
def speech_setup_start() -> SpeechSetupStatus:
    try:
        return SpeechSetupStatus(**start_speech_setup())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/microphone")
def microphone_status() -> dict[str, str | None]:
    return {"meeting_id": get_microphone_owner()}


@app.post("/api/meetings/{meeting_id}/microphone")
def control_microphone(meeting_id: str, payload: MicrophoneControlRequest) -> dict[str, str | None]:
    _require_meeting(meeting_id)
    owner = get_microphone_owner()
    if payload.action == "acquire":
        if owner and owner != meeting_id:
            current = get_meeting(owner)
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "microphone_in_use",
                    "meeting_id": owner,
                    "meeting_title": current.title if current else owner,
                },
            )
        set_microphone_owner(meeting_id)
        return {"meeting_id": meeting_id}
    if owner == meeting_id:
        set_microphone_owner(None)
    return {"meeting_id": get_microphone_owner()}


def _speech_error_message(code: str) -> str:
    return {
        "audio_too_large": "音频超过 500 MB，请压缩或拆分后重试。",
        "audio_too_long": "音频超过 4 小时，请拆分后重试。",
        "empty_audio": "音频文件为空，请重新选择或录制后再试。",
        "unsupported_format": "暂不支持该格式，请使用 MP3、WAV、M4A 或 WebM。",
        "ffmpeg_missing": "未找到 FFmpeg，请检查应用安装目录。",
        "ffmpeg_failed": "音频预处理失败，请更换文件后重试。",
        "model_missing": "未找到内置语音模型，请检查应用 models 目录。",
        "no_speech_detected": "未检测到清晰语音，请检查音量后重试。",
    }.get(code, "转写失败，请查看任务详情并重试。")


def _diarization_warning_message(code: str) -> str:
    return {
        "diarization_model_missing": "说话人分离模型缺失，已保留转写并回退为“发言人 1”。",
        "diarization_model_invalid": "说话人分离模型无法加载，已保留转写并回退为“发言人 1”。",
        "diarization_runtime_missing": "说话人分离运行组件缺失，已保留转写并回退为“发言人 1”。",
        "diarization_audio_invalid": "标准化音频无法用于说话人分离，已保留转写并回退为“发言人 1”。",
        "diarization_no_speakers": "没有得到有效的说话人区间，已保留转写并回退为“发言人 1”。",
    }.get(code, "说话人分离未完成，已保留转写并回退为“发言人 1”。")


def _process_speech_job(
    job_id: str, source_path: str, language: str, attempt: int
) -> None:
    job = get_speech_job(job_id)
    if job is None or job.status == "cancelled" or job.attempt != attempt:
        return
    started_at = time.perf_counter()
    try:
        job.status = "preprocessing"
        job.progress = 20
        save_speech_job(job)
        job = get_speech_job(job_id)
        if job is None or job.status == "cancelled" or job.attempt != attempt:
            return

        job.status = "transcribing"
        job.progress = 55
        save_speech_job(job)

        def report_progress(progress: int) -> None:
            current = get_speech_job(job_id)
            if (
                current is None
                or current.status != "transcribing"
                or current.attempt != attempt
            ):
                return
            current.progress = progress
            save_speech_job(current)

        raw_segments = transcribe(
            job_id,
            Path(source_path),
            language,
            progress_callback=report_progress,
            word_timestamps=job.diarization_enabled,
            progress_ceiling=82 if job.diarization_enabled else 95,
        )

        job = get_speech_job(job_id)
        if job is None or job.status == "cancelled" or job.attempt != attempt:
            return
        processed_segments = assign_speakers(raw_segments, [])
        if job.diarization_enabled:
            job.status = "diarizing"
            job.progress = 85
            save_speech_job(job)

            def report_diarization_progress(progress: int) -> None:
                current = get_speech_job(job_id)
                if current is None or current.status != "diarizing" or current.attempt != attempt:
                    return
                current.progress = min(99, 85 + round(progress * 0.14))
                save_speech_job(current)

            try:
                turns = diarize(
                    normalized_audio_path(job_id),
                    speaker_count=job.requested_speaker_count,
                    progress_callback=report_diarization_progress,
                )
                processed_segments = assign_speakers(raw_segments, turns)
                job.diarization_model = DIARIZATION_MODEL_NAME
                job.detected_speaker_count = len(
                    {item["speaker_label"] for item in processed_segments}
                )
                job.diarization_warning = None
            except Exception as exc:
                code = str(exc)
                logger.warning("speaker diarization fallback job_id=%s code=%s", job_id, code, exc_info=True)
                job.diarization_warning = _diarization_warning_message(code)
                job.diarization_model = DIARIZATION_MODEL_NAME
                job.detected_speaker_count = 1

            current = get_speech_job(job_id)
            if current is None or current.status == "cancelled" or current.attempt != attempt:
                return
        job.segments = [
            TranscriptSegment(
                id=f"seg_{index:04d}",
                sequence=index,
                start_seconds=round(item["start"], 2),
                end_seconds=round(item["end"], 2),
                original_text=item["text"],
                revised_text=item["text"],
                speaker_label=item["speaker_label"],
                speaker_ambiguous=item.get("speaker_ambiguous", False),
            )
            for index, item in enumerate(processed_segments, start=1)
        ]
        if not job.segments:
            raise RuntimeError("no_speech_detected")
        job.full_text = "\n".join(f"{item.speaker_label}：{item.revised_text}" for item in job.segments)
        job.status = "awaiting_review"
        job.progress = 100
        job.processing_seconds = round(time.perf_counter() - started_at, 2)
        save_speech_job(job)
    except (ValueError, RuntimeError) as exc:
        job = get_speech_job(job_id)
        if job is None or job.status == "cancelled" or job.attempt != attempt:
            return
        job.status = "failed"
        job.error_code = str(exc)
        job.error_message = _speech_error_message(str(exc))
        job.processing_seconds = round(time.perf_counter() - started_at, 2)
        save_speech_job(job)
    except Exception:
        job = get_speech_job(job_id)
        if job is None or job.status == "cancelled" or job.attempt != attempt:
            return
        job.status = "failed"
        job.error_code = "transcription_failed"
        job.error_message = _speech_error_message(job.error_code)
        job.processing_seconds = round(time.perf_counter() - started_at, 2)
        save_speech_job(job)


@app.post("/api/speech/transcriptions", response_model=SpeechJob)
async def upload_and_transcribe(
    background_tasks: BackgroundTasks,
    meeting_id: str = Form(...),
    source_type: str = Form("upload"),
    language: str = Form("zh"),
    diarization_enabled: bool = Form(True),
    speaker_count: int | None = Form(None, ge=2, le=10),
    file: UploadFile = File(...),
) -> SpeechJob:
    """Persist an audio source and queue local transcription without blocking the UI."""
    _require_meeting(meeting_id)
    if source_type not in {"microphone", "upload"}:
        raise HTTPException(status_code=422, detail="source_type 必须是 microphone 或 upload")
    job_id = f"stt_{uuid.uuid4().hex[:8]}"
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    job = SpeechJob(
        id=job_id,
        meeting_id=meeting_id,
        source_type=source_type,
        original_name=(file.filename or "recording.webm")[:160],
        status="uploaded",
        progress=5,
        language=language,
        model_name=MODEL_NAME,
        device=DEVICE,
        compute_type=COMPUTE_TYPE,
        full_text="",
        diarization_enabled=diarization_enabled,
        requested_speaker_count=speaker_count,
        created_at=now,
        updated_at=now,
    )
    save_speech_job(job)
    try:
        content = await file.read()
        job.mime_type = file.content_type or ""
        job.size_bytes = len(content)
        source = save_upload(job_id, job.original_name, content)
        job.duration_seconds = probe_duration(source)
        if job.duration_seconds and job.duration_seconds > MAX_AUDIO_SECONDS:
            raise ValueError("audio_too_long")
        save_speech_job(job)
    except (ValueError, RuntimeError) as exc:
        if str(exc) == "audio_too_long":
            delete_audio_assets(job.id)
        job.status = "failed"
        job.error_code = str(exc)
        job.error_message = _speech_error_message(str(exc))
        return save_speech_job(job)
    background_tasks.add_task(
        _process_speech_job, job.id, str(source), language, job.attempt
    )
    return job


@app.post("/api/speech/jobs", response_model=SpeechJob)
def create_speech_job(payload: SpeechJobCreateRequest) -> SpeechJob:
    _require_meeting(payload.meeting_id)
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    segments = _split_stub_segments(payload.stub_text)
    transcript = "\n".join(f"{segment.speaker_label}：{segment.revised_text}" for segment in segments)
    job = SpeechJob(
        id=f"stt_{uuid.uuid4().hex[:8]}",
        meeting_id=payload.meeting_id,
        source_type=payload.source_type,
        original_name=payload.original_name.strip(),
        status="awaiting_review",
        progress=100,
        language=payload.language,
        model_name="stub-provider",
        device="cpu",
        compute_type="n/a",
        full_text=transcript,
        segments=segments,
        created_at=now,
        updated_at=now,
    )
    return save_speech_job(job)


@app.get("/api/speech/jobs/{job_id}", response_model=SpeechJob)
def speech_job_detail(job_id: str) -> SpeechJob:
    job = get_speech_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="转写任务不存在")
    return job


@app.post("/api/speech/jobs/{job_id}/cancel", response_model=SpeechJob)
def cancel_speech_job(job_id: str) -> SpeechJob:
    job = get_speech_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="转写任务不存在")
    if job.status not in {"uploaded", "preprocessing", "transcribing", "diarizing"}:
        raise HTTPException(status_code=409, detail="当前任务不支持取消")
    job.status = "cancelled"
    job.error_code = "cancelled_by_user"
    job.error_message = "已取消转写，可保留音频后重新尝试。"
    return save_speech_job(job)


@app.post("/api/speech/jobs/{job_id}/retry", response_model=SpeechJob)
def retry_speech_job(job_id: str, background_tasks: BackgroundTasks) -> SpeechJob:
    job = get_speech_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="转写任务不存在")
    if job.status not in {"failed", "cancelled"}:
        raise HTTPException(status_code=409, detail="只有失败或已取消任务可以重试")
    source = source_for_job(job.id)
    if source is None:
        raise HTTPException(status_code=409, detail="原始音频已不存在，请重新上传文件")
    job.status = "uploaded"
    job.progress = 5
    job.full_text = ""
    job.segments = []
    job.error_code = None
    job.error_message = None
    job.processing_seconds = None
    job.detected_speaker_count = None
    job.diarization_warning = None
    job.attempt += 1
    save_speech_job(job)
    background_tasks.add_task(
        _process_speech_job, job.id, str(source), job.language, job.attempt
    )
    return job


@app.delete("/api/speech/jobs/{job_id}", response_model=SpeechJob)
def delete_speech_job_route(job_id: str) -> SpeechJob:
    job = get_speech_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="转写任务不存在")
    if job.status in {"uploaded", "preprocessing", "transcribing", "diarizing"}:
        raise HTTPException(status_code=409, detail="请先取消正在处理的转写任务")
    if job.status == "confirmed":
        raise HTTPException(status_code=409, detail="已确认转写已进入会议记录，暂不支持删除")
    meeting = _require_meeting(job.meeting_id)
    meeting.audit_events.append(_event("删除音频任务", f"删除未进入会议分析的音频任务 {job.id}：{job.original_name}。", "本人"))
    save_meeting(meeting)
    delete_speech_job(job.id)
    delete_audio_assets(job.id)
    return job


@app.get("/api/meetings/{meeting_id}/speech-jobs", response_model=list[SpeechJob])
def meeting_speech_jobs(meeting_id: str) -> list[SpeechJob]:
    _require_meeting(meeting_id)
    return list_speech_jobs(meeting_id)


@app.patch("/api/speech/jobs/{job_id}/segments/{segment_id}", response_model=SpeechJob)
def update_speech_segment(
    job_id: str, segment_id: str, payload: TranscriptSegmentUpdateRequest
) -> SpeechJob:
    job = get_speech_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="转写任务不存在")
    if job.status != "awaiting_review":
        raise HTTPException(status_code=409, detail="只有待审核转写可以修改")
    segment = next((item for item in job.segments if item.id == segment_id), None)
    if segment is None:
        raise HTTPException(status_code=404, detail="转写片段不存在")
    previous_text = segment.revised_text
    segment.revised_text = payload.revised_text.strip()
    segment.speaker_label = payload.speaker_label.strip()
    if previous_text != segment.revised_text:
        job.revisions.append(
            TranscriptRevision(
                id=f"rev_{uuid.uuid4().hex[:8]}",
                segment_id=segment.id,
                previous_text=previous_text,
                revised_text=segment.revised_text,
                revised_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            )
        )
    job.full_text = "\n".join(f"{item.speaker_label}：{item.revised_text}" for item in job.segments)
    return save_speech_job(job)


@app.patch("/api/speech/jobs/{job_id}/transcript", response_model=SpeechJob)
def update_speech_full_text(job_id: str, payload: TranscriptFullTextUpdateRequest) -> SpeechJob:
    job = get_speech_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="转写任务不存在")
    if job.status != "awaiting_review":
        raise HTTPException(status_code=409, detail="只有待审核转写可以修改")
    previous_text = job.full_text
    job.full_text = payload.full_text.strip()
    if previous_text != job.full_text:
        job.revisions.append(
            TranscriptRevision(
                id=f"rev_{uuid.uuid4().hex[:8]}",
                previous_text=previous_text,
                revised_text=job.full_text,
                revised_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            )
        )
    job.segments = _sync_segments_from_full_text(job.full_text, job.segments)
    return save_speech_job(job)


@app.post("/api/speech/jobs/{job_id}/confirm", response_model=SpeechConfirmResponse)
def confirm_speech_job(job_id: str) -> SpeechConfirmResponse:
    job = get_speech_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="转写任务不存在")
    if job.status == "confirmed":
        return SpeechConfirmResponse(job=job, transcript=job.full_text)
    if job.status != "awaiting_review":
        raise HTTPException(status_code=409, detail="只有待审核转写可以确认")
    job.status = "confirmed"
    job.progress = 100
    save_speech_job(job)
    meeting = _require_meeting(job.meeting_id)
    meeting.audit_events.append(_event("确认转写", f"确认语音任务 {job.id}，文本可进入会议分析。", "本人"))
    save_meeting(meeting)
    return SpeechConfirmResponse(job=job, transcript=job.full_text)


@app.post("/api/agenda/draft", response_model=AgendaDraftResponse)
async def draft_agenda(payload: AgendaDraftRequest) -> AgendaDraftResponse:
    workspace = get_ads_workspace(payload.workspace_id) if payload.workspace_id else None
    if payload.workspace_id and workspace is None:
        raise HTTPException(status_code=422, detail="所选 ADS 工作区不存在")
    started = time.perf_counter()
    result, model, fallback_error = await build_agenda_draft(
        payload,
        workspace or AdsWorkspacePayload(name="未关联工作区"),
    )
    save_model_call_audit(
        ModelCallAudit(
            id=f"call_{uuid.uuid4().hex[:10]}",
            provider_id=payload.model_provider_id,
            model=model,
            operation="agenda_draft",
            status="success" if result.mode == "live" else "fallback",
            duration_ms=int((time.perf_counter() - started) * 1000),
            prompt_version=PROMPT_VERSION,
            error=fallback_error,
            created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        )
    )
    return result


@app.get("/api/meetings", response_model=list[MeetingSummary])
def meetings() -> list[MeetingSummary]:
    return list_meetings()


@app.post("/api/meetings", response_model=MeetingSession)
def start_meeting(payload: MeetingCreateRequest) -> MeetingSession:
    workspace_id = payload.workspace_id
    if workspace_id is None:
        available_workspaces = [item for item in list_ads_workspaces() if not item.archived]
        settings = get_app_settings()
        default_workspace = next(
            (item for item in available_workspaces if item.id == settings.active_workspace_id),
            available_workspaces[0] if available_workspaces else None,
        )
        if default_workspace is None:
            raise HTTPException(
                status_code=409,
                detail={"code": "setup_required", "message": "请先完成本人身份和 ADS 工作区设置"},
            )
        workspace_id = default_workspace.id if default_workspace else None
    elif get_ads_workspace(workspace_id) is None:
        raise HTTPException(status_code=422, detail="所选 ADS 工作区不存在")
    workspace = get_ads_workspace(workspace_id) if workspace_id else None
    agent_identity_id = payload.agent_identity_id if payload.participation_mode == "delegate" else None
    if payload.participation_mode == "delegate":
        if not agent_identity_id:
            raise HTTPException(status_code=422, detail="委托智能体时必须选择代理身份")
        if workspace and not any(item.id == agent_identity_id for item in workspace.people):
            raise HTTPException(status_code=422, detail="代理身份不在当前 ADS 工作区人员列表中")
    known_rule_ids = {item.id for item in workspace.authorization_rules} if workspace else set()
    selected_rule_ids = payload.authorization_rule_ids if payload.participation_mode == "delegate" else []
    if payload.participation_mode == "delegate" and not selected_rule_ids:
        raise HTTPException(status_code=422, detail="委托智能体时必须选择至少一条本场授权")
    if not set(selected_rule_ids).issubset(known_rule_ids):
        raise HTTPException(status_code=422, detail="本场授权包含不存在的规则")
    if payload.auto_reply_enabled and payload.participation_mode != "delegate":
        raise HTTPException(status_code=422, detail="只有委托智能体参会时可以开启授权内自动回复")
    starts = expand_occurrence_starts(payload.scheduled_at, payload.recurrence)
    series_id = f"series_{uuid.uuid4().hex[:8]}" if payload.recurrence.frequency != "none" else None
    created_meetings: list[MeetingSession] = []
    for occurrence_index, scheduled_at in enumerate(starts):
        occurrence_end = None
        if payload.end_at:
            occurrence_end = (
                datetime.fromisoformat(scheduled_at) + timedelta(minutes=payload.duration_minutes)
            ).strftime("%Y-%m-%d %H:%M")
        meeting = create_meeting(
            meeting_id=f"mtg_{uuid.uuid4().hex[:8]}",
            title=payload.title.strip(),
            scenario=payload.scenario.strip(),
            meeting_type=payload.meeting_type.strip(),
            scheduled_at=scheduled_at,
            end_at=occurrence_end,
            duration_minutes=payload.duration_minutes,
            participants=[participant.strip() for participant in payload.participants if participant.strip()],
            objective=payload.objective.strip(),
            agenda_text=payload.agenda_text.strip(),
            participation_mode=payload.participation_mode,
            model_provider_id=payload.model_provider_id,
            workspace_id=workspace_id,
            agent_identity_id=agent_identity_id,
            authorization_rule_ids=selected_rule_ids,
            auto_reply_enabled=payload.auto_reply_enabled,
            series_id=series_id,
            occurrence_index=occurrence_index,
            recurrence=payload.recurrence,
            agenda=payload.agenda,
        )
        detail = "建立会议会话，等待生成会前准备。"
        if series_id:
            detail = f"建立循环会议第 {occurrence_index + 1} 场，等待生成会前准备。"
        meeting.audit_events.append(_event("创建会议", detail))
        created_meetings.append(save_meeting(meeting))
    return created_meetings[0]


@app.get("/api/meetings/{meeting_id}", response_model=MeetingSession)
def meeting_detail(meeting_id: str) -> MeetingSession:
    return _require_meeting(meeting_id)


@app.patch("/api/meetings/{meeting_id}", response_model=MeetingSession)
def update_meeting(
    meeting_id: str,
    payload: MeetingUpdateRequest,
    scope: Literal["single", "future"] = "single",
) -> MeetingSession:
    meeting = _require_meeting(meeting_id)
    fields = payload.model_fields_set
    if not fields:
        return meeting

    text_fields = {"title", "objective", "agenda_text"}
    structural_fields = fields - text_fields
    if structural_fields and meeting.meeting_status not in {"draft", "scheduled"}:
        raise HTTPException(status_code=409, detail="会议已开始或结束，只能修改名称和会议内容")

    targets = [meeting]
    if scope == "future" and meeting.series_id:
        targets = [
            item for item in list_meeting_sessions()
            if item.series_id == meeting.series_id
            and item.occurrence_index >= meeting.occurrence_index
        ]
    if structural_fields and any(item.meeting_status not in {"draft", "scheduled"} for item in targets):
        raise HTTPException(status_code=409, detail="本次及后续包含已开始或结束的会议，不能修改结构信息")

    changes = payload.model_dump(exclude_unset=True)
    old_start = datetime.fromisoformat(meeting.scheduled_at.replace("T", " "))
    try:
        new_start = datetime.fromisoformat(str(changes.get("scheduled_at", meeting.scheduled_at)).replace("T", " "))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="开始时间格式无效") from exc
    schedule_delta = new_start - old_start
    new_duration = int(changes.get("duration_minutes", meeting.duration_minutes))
    if "end_at" in fields and changes["end_at"]:
        try:
            requested_end = datetime.fromisoformat(str(changes["end_at"]).replace("T", " "))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="结束时间格式无效") from exc
        new_duration = int((requested_end - new_start).total_seconds() / 60)
    if not 5 <= new_duration <= 480:
        raise HTTPException(status_code=422, detail="会议时长必须在 5 分钟至 8 小时之间")

    prepared_targets: list[MeetingSession] = []
    for target in targets:
        target_start = datetime.fromisoformat(target.scheduled_at.replace("T", " "))
        shifted_start = target_start + schedule_delta
        if "scheduled_at" in fields:
            target.scheduled_at = shifted_start.strftime("%Y-%m-%d %H:%M")
        if fields & {"scheduled_at", "end_at", "duration_minutes"}:
            target.duration_minutes = new_duration
            if "end_at" in fields and changes["end_at"] is None:
                target.end_at = None
            elif target.end_at is not None or "end_at" in fields:
                target.end_at = (shifted_start + timedelta(minutes=new_duration)).strftime("%Y-%m-%d %H:%M")

        for field in fields - {"scheduled_at", "end_at", "duration_minutes"}:
            value = changes[field]
            if field in {"objective", "agenda_text"} and isinstance(value, str):
                value = value.strip()
            if field == "participants" and value is not None:
                value = [item.strip() for item in value if item.strip()]
            setattr(target, field, value)

        workspace = get_ads_workspace(target.workspace_id) if target.workspace_id else None
        if target.workspace_id and workspace is None:
            raise HTTPException(status_code=422, detail="所选 ADS 工作区不存在")
        if target.participation_mode == "delegate":
            if not target.agent_identity_id:
                raise HTTPException(status_code=422, detail="委托智能体时必须选择代理身份")
            if workspace and not any(item.id == target.agent_identity_id for item in workspace.people):
                raise HTTPException(status_code=422, detail="代理身份不在当前 ADS 工作区人员列表中")
            known_rule_ids = {item.id for item in workspace.authorization_rules} if workspace else set()
            if not target.authorization_rule_ids:
                raise HTTPException(status_code=422, detail="委托智能体时必须选择至少一条本场授权")
            if not set(target.authorization_rule_ids).issubset(known_rule_ids):
                raise HTTPException(status_code=422, detail="本场授权包含不存在的规则")
        else:
            target.agent_identity_id = None
            target.authorization_rule_ids = []
            target.auto_reply_enabled = False
        target.audit_events.append(_event("编辑会议信息", f"本人更新字段：{'、'.join(sorted(fields))}。", "本人"))
        prepared_targets.append(target)

    saved_current = meeting
    for target in prepared_targets:
        saved = save_meeting(target)
        if target.id == meeting.id:
            saved_current = saved
    return saved_current


@app.patch("/api/meetings/{meeting_id}/agenda", response_model=MeetingSession)
def update_meeting_agenda(meeting_id: str, payload: MeetingAgendaUpdateRequest) -> MeetingSession:
    meeting = _require_meeting(meeting_id)
    if any(item.duration_minutes is None for item in payload.agenda):
        raise HTTPException(status_code=422, detail="请为每个议程项填写分钟数")
    total = sum(item.duration_minutes or 0 for item in payload.agenda)
    if total != meeting.duration_minutes:
        raise HTTPException(status_code=422, detail=f"议程分钟合计必须等于会议时长 {meeting.duration_minutes} 分钟")
    meeting.agenda = payload.agenda
    meeting.agenda_edited = True
    meeting.audit_events.append(_event("人工修订议程", f"本人保存 {len(payload.agenda)} 项议程。", "本人"))
    return save_meeting(meeting)


@app.patch("/api/meetings/{meeting_id}/model", response_model=MeetingSession)
def update_meeting_model(meeting_id: str, payload: MeetingModelUpdateRequest) -> MeetingSession:
    meeting = _require_meeting(meeting_id)
    configs = {config.provider_id: config for config in (list_model_configs() or default_model_configs())}
    config = configs.get(payload.model_provider_id)
    if config is None:
        raise HTTPException(status_code=404, detail="模型配置不存在")
    meeting.model_provider_id = config.provider_id
    meeting.audit_events.append(_event("切换会议模型", f"后续新请求使用 {config.provider_name}。", "本人"))
    return save_meeting(meeting)


@app.post("/api/meetings/{meeting_id}/prepare", response_model=MeetingSession)
def prepare_meeting(meeting_id: str, replace_manual: bool = False) -> MeetingSession:
    meeting = _require_meeting(meeting_id)
    _require_status(meeting, {"draft", "prepared"})
    if meeting.agenda_edited and not replace_manual:
        raise HTTPException(status_code=409, detail="建议议程包含人工修订，请确认后再重新生成")
    if meeting.status == "prepared" or replace_manual:
        generated = build_local_agenda_draft(AgendaDraftRequest(
            content=meeting.objective or meeting.agenda_text or meeting.title,
            duration_minutes=meeting.duration_minutes,
            workspace_id=meeting.workspace_id,
            model_provider_id=meeting.model_provider_id,
        ))
        meeting.agenda = generated.agenda
        meeting.agenda_text = generated.agenda_text
        meeting.agenda_edited = False
    workspace = get_ads_workspace(meeting.workspace_id) if meeting.workspace_id else None
    objectives = workspace.objectives if workspace is not None else []
    tasks = workspace.tasks if workspace is not None else []
    rules = workspace.authorization_rules if workspace is not None else []
    if objectives:
        primary_objective = objectives[0]
        objective_summary = (
            f"当前目标“{primary_objective.title}”进度为 {primary_objective.progress}%，"
            f"主要风险是：{primary_objective.risk}。"
        )
        objective_context = f"{primary_objective.title}，当前进度 {primary_objective.progress}%"
    else:
        objective_summary = "当前工作区尚未配置业务目标。"
        objective_context = "尚未配置业务目标，请先确认本次会议希望达成的结果。"
    authorization_context = (
        rules[0].scope
        if rules
        else "尚未配置代理授权，涉及执行或承诺的事项需要本人确认。"
    )
    agenda_seed = [line.strip() for line in meeting.agenda_text.splitlines() if line.strip()]
    meeting.pre_meeting_brief = (
        f"本次会议聚焦“{meeting.title}”。"
        f"会议目标是：{meeting.objective or '确认关键风险、决策和行动项'}。{objective_summary}"
        "建议优先确认交付范围、责任边界和必须升级本人处理的事项。"
    )
    agenda_preserved = bool(meeting.agenda)
    if not meeting.agenda:
        meeting.agenda = [
            AgendaItem(
                topic=agenda_seed[0] if len(agenda_seed) > 0 else "目标与进度",
                context=objective_context,
                suggested_question="本周最影响业务目标的阻塞项是什么？",
            ),
            AgendaItem(
                topic=agenda_seed[1] if len(agenda_seed) > 1 else "任务与风险",
                context=f"当前 ADS 中有 {len(tasks)} 条任务。",
                suggested_question="责任人、截止时间和验收依据是否明确？",
            ),
            AgendaItem(
                topic=agenda_seed[2] if len(agenda_seed) > 2 else "代理授权边界",
                context=authorization_context,
                suggested_question="是否出现范围变更、技术路线替换等升级条件？",
            ),
        ]
    meeting.status = "prepared"
    meeting.meeting_status = "scheduled"
    meeting.agent_session_state = "preparing"
    agenda_detail = "并复用已确认议程" if agenda_preserved else "并形成三项建议议程"
    meeting.audit_events.append(_event("生成会前简报", f"读取 ADS 目标、任务和授权规则，{agenda_detail}。"))
    return save_meeting(meeting)


@app.post("/api/meetings/{meeting_id}/lifecycle", response_model=MeetingSession)
def control_meeting_lifecycle(
    meeting_id: str, payload: MeetingLifecycleRequest
) -> MeetingSession:
    meeting = _require_meeting(meeting_id)
    if payload.action == "start":
        if meeting.meeting_status == "in_progress":
            return meeting
        if meeting.meeting_status != "scheduled":
            raise HTTPException(status_code=409, detail="只有等待开始的会议可以开始")
        _require_status(meeting, {"prepared", "confirmed", "awaiting_confirmation"})
        if meeting.participation_mode == "delegate" and meeting.agent_session_state != "preparing":
            raise HTTPException(status_code=409, detail="当前会议不在可委托状态")
        meeting.meeting_status = "in_progress"
        meeting.agent_session_state = "delegating"
        detail = (
            "本人开始会议，并确认 ADS 智能体按本场授权范围参与。"
            if meeting.participation_mode == "delegate"
            else "本人开始会议，ADS 智能体进入协助状态。"
        )
        meeting.audit_events.append(_event("开始会议", detail, "本人"))
    elif payload.action == "end":
        if meeting.meeting_status in {"ended", "closed"}:
            return meeting
        if meeting.meeting_status != "in_progress":
            raise HTTPException(status_code=409, detail="只有进行中的会议可以结束")
        meeting.meeting_status = "ended"
        meeting.agent_session_state = "completed"
        if get_microphone_owner() == meeting.id:
            set_microphone_owner(None)
        pending = sum(1 for item in meeting.escalation_requests if item.status in {"pending", "deferred"})
        follow_up = f"仍有 {pending} 项待本人处理。" if pending else "后续行动项可继续确认和写回。"
        meeting.audit_events.append(_event("结束会议", follow_up, "本人"))
    else:
        if meeting.meeting_status == "in_progress":
            return meeting
        if meeting.meeting_status not in {"ended", "closed"}:
            raise HTTPException(status_code=409, detail="只有已结束的会议可以重新打开")
        meeting.meeting_status = "in_progress"
        meeting.agent_session_state = "delegating"
        if meeting.status == "completed":
            meeting.status = "confirmed"
        meeting.audit_events.append(_event("重新打开会议", "本人恢复会议，可继续补充发言和成果。", "本人"))
    return save_meeting(meeting)


@app.post("/api/meetings/{meeting_id}/agent/control", response_model=MeetingSession)
def control_agent(meeting_id: str, payload: AgentControlRequest) -> MeetingSession:
    meeting = _require_meeting(meeting_id)
    if meeting.participation_mode != "delegate":
        raise HTTPException(status_code=409, detail="本人参加的会议不需要委托控制")

    if payload.action == "start":
        _require_status(meeting, {"prepared", "confirmed"})
        if meeting.agent_session_state == "delegating":
            return meeting
        if meeting.agent_session_state != "preparing":
            raise HTTPException(status_code=409, detail="当前会议不在可委托状态")
        meeting.agent_session_state = "delegating"
        meeting.meeting_status = "in_progress"
        meeting.audit_events.append(_event("确认委托参会", "本人确认 ADS 智能体按本场授权范围参与会议。", "本人"))
    elif payload.action == "pause":
        if meeting.agent_session_state != "delegating" or meeting.meeting_status != "in_progress":
            raise HTTPException(status_code=409, detail="智能体当前不在进行中")
        meeting.agent_session_state = "paused"
        meeting.audit_events.append(_event("暂停智能体", "本人暂时停止智能体处理新的会议发言。", "本人"))
    else:
        if meeting.agent_session_state != "paused":
            raise HTTPException(status_code=409, detail="智能体当前未暂停")
        meeting.agent_session_state = "delegating"
        meeting.meeting_status = "in_progress"
        meeting.audit_events.append(_event("继续智能体", "本人恢复智能体处理新的会议发言。", "本人"))

    return save_meeting(meeting)


@app.post("/api/meetings/{meeting_id}/analyze", response_model=MeetingSession)
async def analyze_session(
    meeting_id: str, payload: MeetingTranscriptRequest
) -> MeetingSession:
    meeting = _require_meeting(meeting_id)
    if meeting.meeting_status != "in_progress":
        raise HTTPException(status_code=409, detail="请先开始会议；已结束的会议需重新打开后才能继续记录")
    _require_status(meeting, {"prepared", "awaiting_confirmation", "confirmed"})
    if meeting.participation_mode == "delegate" and meeting.agent_session_state != "delegating":
        raise HTTPException(status_code=409, detail="请先确认委托参会，或先恢复智能体")
    new_transcript = payload.transcript.strip()
    previous_analysis = meeting.analysis
    workspace = get_ads_workspace(meeting.workspace_id) if meeting.workspace_id else None
    selected_rules = [
        rule
        for rule in (workspace.authorization_rules if workspace else [])
        if rule.id in meeting.authorization_rule_ids
    ]
    analysis_context = workspace.model_copy(deep=True) if workspace else None
    if analysis_context is not None:
        analysis_context.authorization_rules = (
            selected_rules if meeting.participation_mode == "delegate"
            else list(workspace.authorization_rules)
        )
    analysis_request = MeetingAnalysisRequest(
        title=meeting.title,
        transcript=new_transcript,
        scenario=meeting.scenario,
        model_provider_id=meeting.model_provider_id,
        ads_context=analysis_context,
    )
    call_started = time.perf_counter()
    try:
        analysis = await build_model_analysis(analysis_request)
    except Exception as exc:
        save_model_call_audit(
            ModelCallAudit(
                id=f"call_{uuid.uuid4().hex[:10]}",
                meeting_id=meeting.id,
                provider_id=meeting.model_provider_id,
                model=meeting.model_provider_id,
                operation="meeting_analysis",
                status="failed",
                duration_ms=int((time.perf_counter() - call_started) * 1000),
                prompt_version=PROMPT_VERSION,
                error=str(exc)[:500],
                created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            )
        )
        raise HTTPException(status_code=502, detail="在线模型分析失败，请重试、切换模型或选择本地规则模式") from exc
    live_call = provider_ready(meeting.model_provider_id)
    save_model_call_audit(
        ModelCallAudit(
            id=f"call_{uuid.uuid4().hex[:10]}",
            meeting_id=meeting.id,
            provider_id=meeting.model_provider_id,
            model=meeting.model_provider_id,
            operation="meeting_analysis",
            status="success" if live_call else "fallback",
            duration_ms=int((time.perf_counter() - call_started) * 1000),
            prompt_version=PROMPT_VERSION,
            created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        )
    )
    if meeting.participation_mode == "delegate":
        forced_escalation = find_escalation_match(new_transcript, selected_rules)
        if forced_escalation:
            _, escalation_content, escalation_rule = forced_escalation
            analysis.agent_replies = [
                reply
                for reply in analysis.agent_replies
                if reply.decision == "escalate"
                or not (
                    reply.question.strip() in escalation_content
                    or escalation_content in reply.question.strip()
                )
            ]
            if not any(
                reply.decision == "escalate" and reply.question.strip() == escalation_content
                for reply in analysis.agent_replies
            ):
                evidence_ids = [escalation_rule.id]
                if analysis_context and analysis_context.objectives:
                    evidence_ids.append(analysis_context.objectives[0].id)
                analysis.agent_replies.append(
                    AgentReply(
                        question=escalation_content,
                        decision="escalate",
                        reply="该事项超出当前代理授权，需要本人确认后再继续执行。",
                        reason="原始发言命中本场授权的升级条件。",
                        evidence_object_ids=evidence_ids,
                    )
                )
    analysis.meeting_id = meeting.id
    analysis.pre_meeting_brief = meeting.pre_meeting_brief
    analysis.agenda = meeting.agenda
    analysis.writeback_tasks = []
    analysis.audit_events = []
    for item in analysis.action_items:
        item.status = _action_status(item.owner_id, item.due_date)
    current_decision_count = len(analysis.decisions)
    current_action_item_count = len(analysis.action_items)
    escalation_replies = [reply for reply in analysis.agent_replies if reply.decision == "escalate"]
    authorized_replies = [reply for reply in analysis.agent_replies if reply.decision != "escalate"]
    for reply in authorized_replies:
        sent_state = "sent" if meeting.auto_reply_enabled else "suggested"
        meeting.sent_agent_replies.append(
            SentAgentReply(
                id=f"reply_{uuid.uuid4().hex[:8]}",
                content=reply.reply,
                decision=sent_state,
                evidence_object_ids=reply.evidence_object_ids,
                authorization_rule_ids=meeting.authorization_rule_ids,
                created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            )
        )
        meeting.audit_events.append(
            _event(
                "智能体已发送" if sent_state == "sent" else "生成回复建议",
                f"回复依据 {len(reply.evidence_object_ids)} 个 ADS 对象和 {len(meeting.authorization_rule_ids)} 条本场授权。",
            )
        )
    meeting.transcript = "\n".join(part for part in [meeting.transcript.strip(), new_transcript] if part)
    meeting.analysis = _merge_analysis(previous_analysis, analysis)
    _rebuild_structured_minutes(meeting)
    _refresh_workload_metrics(meeting)
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    new_escalation_requests = [
        EscalationRequest(
            id=f"esc_{uuid.uuid4().hex[:8]}",
            meeting_id=meeting.id,
            question=reply.question,
            reason=reply.reason,
            evidence_object_ids=reply.evidence_object_ids,
            ai_recommendation=reply.reply,
            status="pending",
            created_at=now,
            updated_at=now,
            reply_deadline=(datetime.now().astimezone() + timedelta(hours=24)).isoformat(timespec="seconds"),
        )
        for reply in escalation_replies
    ]
    meeting.escalation_requests.extend(new_escalation_requests)
    requires_confirmation = any(item.status == "pending" for item in meeting.escalation_requests)
    meeting.status = "awaiting_confirmation" if requires_confirmation else "confirmed"
    meeting.agent_session_state = "delegating"
    meeting.audit_events.append(
        _event("分析会议", f"识别 {current_decision_count} 条决策和 {current_action_item_count} 条行动项。")
    )
    if new_escalation_requests:
        meeting.audit_events.append(_event("升级本人", "检测到超出代理授权边界的事项，暂停回写。"))
    meeting.analysis.export_markdown = _build_analysis_markdown(meeting)
    return save_meeting(meeting)


@app.post("/api/meetings/{meeting_id}/agent/ask", response_model=AgentQuestionResponse)
async def ask_meeting_agent(meeting_id: str, payload: AgentQuestionRequest) -> AgentQuestionResponse:
    meeting = _require_meeting(meeting_id)
    workspace = get_ads_workspace(meeting.workspace_id) if meeting.workspace_id else None
    context = workspace or AdsWorkspacePayload(name="未关联工作区")
    started = time.perf_counter()
    try:
        answer, evidence, mode, model = await answer_agent_question(
            meeting.model_provider_id, payload.question, context
        )
    except Exception as exc:
        save_model_call_audit(
            ModelCallAudit(
                id=f"call_{uuid.uuid4().hex[:10]}",
                meeting_id=meeting.id,
                provider_id=meeting.model_provider_id,
                model=meeting.model_provider_id,
                operation="agent_question",
                status="failed",
                duration_ms=int((time.perf_counter() - started) * 1000),
                prompt_version=PROMPT_VERSION,
                error=str(exc)[:500],
                created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            )
        )
        raise HTTPException(status_code=502, detail="智能体回答失败，请重试或切换模型") from exc
    save_model_call_audit(
        ModelCallAudit(
            id=f"call_{uuid.uuid4().hex[:10]}",
            meeting_id=meeting.id,
            provider_id=meeting.model_provider_id,
            model=model,
            operation="agent_question",
            status="success" if mode == "live" else "fallback",
            duration_ms=int((time.perf_counter() - started) * 1000),
            prompt_version=PROMPT_VERSION,
            created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        )
    )
    meeting.audit_events.append(_event("询问 ADS 智能体", f"回答引用 {len(evidence)} 个 ADS 对象。", "本人"))
    save_meeting(meeting)
    return AgentQuestionResponse(
        answer=answer,
        evidence_object_ids=evidence,
        model_provider_id=meeting.model_provider_id,
        mode=mode,
    )


@app.post("/api/meetings/{meeting_id}/confirm", response_model=MeetingSession)
def confirm_meeting(
    meeting_id: str, payload: MeetingConfirmationRequest
) -> MeetingSession:
    meeting = _require_meeting(meeting_id)
    _require_status(meeting, {"awaiting_confirmation"})
    pending = [item for item in meeting.escalation_requests if item.status == "pending"]
    if not pending:
        meeting.status = "confirmed"
        meeting.agent_session_state = "delegating" if meeting.meeting_status == "in_progress" else "completed"
        return save_meeting(meeting)
    for escalation in pending:
        _resolve_escalation(meeting, escalation, payload.action, payload.reply)
    return save_meeting(meeting)


@app.post(
    "/api/meetings/{meeting_id}/escalations/{escalation_id}/resolve",
    response_model=MeetingSession,
)
def resolve_escalation(
    meeting_id: str, escalation_id: str, payload: EscalationResolveRequest
) -> MeetingSession:
    meeting = _require_meeting(meeting_id)
    _require_status(meeting, {"awaiting_confirmation", "confirmed"})
    escalation = next((item for item in meeting.escalation_requests if item.id == escalation_id), None)
    if escalation is None:
        raise HTTPException(status_code=404, detail="确认事项不存在")
    return _resolve_escalation(meeting, escalation, payload.action, payload.reply)


@app.patch(
    "/api/meetings/{meeting_id}/action-items/{item_id}",
    response_model=MeetingSession,
)
def complete_action_item(
    meeting_id: str, item_id: str, payload: ActionItemUpdateRequest
) -> MeetingSession:
    meeting = _require_meeting(meeting_id)
    _require_status(meeting, {"confirmed"})
    if meeting.analysis is None:
        raise HTTPException(status_code=409, detail="会议尚未生成分析结果")
    people = _meeting_people(meeting)
    if not any(person.id == payload.owner_id for person in people):
        raise HTTPException(status_code=422, detail="负责人不在当前 ADS 人员列表中")
    action_item = next(
        (item for item in meeting.analysis.action_items if item.id == item_id), None
    )
    if action_item is None:
        raise HTTPException(status_code=404, detail="行动项不存在")
    action_item.owner_id = payload.owner_id
    action_item.due_date = payload.due_date.isoformat()
    action_item.status = _action_status(action_item.owner_id, action_item.due_date)
    linked_decision = next(
        (
            decision
            for decision in meeting.analysis.decisions
            if decision.id == action_item.linked_decision_id
        ),
        None,
    )
    if linked_decision is not None:
        linked_decision.owner_id = payload.owner_id
        linked_decision.due_date = payload.due_date.isoformat()
    _rebuild_structured_minutes(meeting)
    meeting.analysis.metrics.minutes_generated_characters = len(meeting.analysis.structured_minutes)
    meeting.analysis.export_markdown = _build_analysis_markdown(meeting)
    meeting.audit_events.append(
        _event(
            "补全任务信息",
            f"行动项 {item_id} 的负责人更新为 {_person_name(payload.owner_id, people)}，截止日期为 {payload.due_date.isoformat()}。",
            "本人",
        )
    )
    return save_meeting(meeting)


def _writeback_action_item(meeting: MeetingSession, item_id: str) -> MeetingSession:
    if meeting.analysis is None:
        raise HTTPException(status_code=409, detail="会议尚未生成分析结果")
    action_item = next((item for item in meeting.analysis.action_items if item.id == item_id), None)
    if action_item is None:
        raise HTTPException(status_code=404, detail="行动项不存在")
    if action_item.status == "written_back":
        return meeting
    known_person_ids = {person.id for person in _meeting_people(meeting)}
    if action_item.owner_id not in known_person_ids or not _valid_due_date(action_item.due_date):
        raise HTTPException(status_code=409, detail="行动项缺少有效负责人或截止日期")
    action_item.writeback_attempts += 1
    task_id = action_item.writeback_task_id or f"task_{meeting.id[4:]}_{action_item.id[-8:]}"
    task = Task(
        id=task_id,
        title=action_item.title,
        owner_id=action_item.owner_id,
        due_date=action_item.due_date,
        status="待执行",
        source_meeting_id=meeting.id,
        source_decision_id=action_item.linked_decision_id,
    )
    try:
        persist_tasks(meeting.id, [task])
        workspace = get_ads_workspace(meeting.workspace_id) if meeting.workspace_id else None
        if workspace is not None:
            workspace.tasks = [existing for existing in workspace.tasks if existing.id != task.id] + [task]
            save_ads_workspace(workspace.id, AdsWorkspacePayload(**workspace.model_dump()))
        action_item.status = "written_back"
        action_item.writeback_task_id = task.id
        action_item.writeback_error = None
        meeting.analysis.writeback_tasks = [
            existing for existing in meeting.analysis.writeback_tasks if existing.id != task.id
        ] + [task]
        meeting.audit_events.append(_event("写回行动项", f"行动项 {action_item.id} 已写回为任务 {task.id}。", "本人"))
    except Exception as exc:
        action_item.status = "writeback_failed"
        action_item.writeback_error = str(exc)[:500]
        meeting.audit_events.append(_event("行动项写回失败", f"行动项 {action_item.id} 可单独重试。", "系统"))
        save_meeting(meeting)
        raise HTTPException(status_code=500, detail="行动项写回失败，状态已保留，可重试") from exc
    _refresh_workload_metrics(meeting)
    if all(item.status == "written_back" for item in meeting.analysis.action_items):
        meeting.status = "completed"
    else:
        meeting.status = "confirmed"
    meeting.analysis.export_markdown = _build_final_markdown(meeting, meeting.analysis.writeback_tasks)
    return save_meeting(meeting)


@app.post(
    "/api/meetings/{meeting_id}/action-items/{item_id}/writeback",
    response_model=MeetingSession,
)
def writeback_action_item(meeting_id: str, item_id: str) -> MeetingSession:
    meeting = _require_meeting(meeting_id)
    _require_status(meeting, {"confirmed"})
    return _writeback_action_item(meeting, item_id)


@app.post("/api/meetings/{meeting_id}/writeback", response_model=MeetingSession)
def writeback_meeting(meeting_id: str) -> MeetingSession:
    meeting = _require_meeting(meeting_id)
    _require_status(meeting, {"confirmed"})
    if meeting.analysis is None:
        raise HTTPException(status_code=409, detail="会议尚未生成分析结果")
    known_person_ids = {person.id for person in _meeting_people(meeting)}
    incomplete_items = [
        {
            "id": item.id,
            "title": item.title,
            "missing": [
                field
                for field, missing in (
                    ("owner_id", item.owner_id not in known_person_ids),
                    ("due_date", not _valid_due_date(item.due_date)),
                )
                if missing
            ],
        }
        for item in meeting.analysis.action_items
        if item.owner_id not in known_person_ids or not _valid_due_date(item.due_date)
    ]
    if incomplete_items:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "incomplete_action_items",
                "message": "行动项缺少负责人或截止日期，请补全后再回写。",
                "items": incomplete_items,
            },
        )
    for item in list(meeting.analysis.action_items):
        meeting = _writeback_action_item(meeting, item.id)
        if meeting.status == "completed":
            break
    meeting.audit_events.append(_event("批量写回 ADS", f"已处理 {len(meeting.analysis.action_items)} 条行动项。"))
    return save_meeting(meeting)


# 保留第一版单请求接口，避免旧演示页面失效。
@app.post("/api/meetings/analyze", response_model=MeetingAnalysis)
async def analyze_meeting(payload: MeetingAnalysisRequest) -> MeetingAnalysis:
    return await build_model_analysis(payload)


@app.delete("/api/meetings/{meeting_id}", response_model=OperationResult)
def remove_meeting(meeting_id: str, scope: Literal["single", "future"] = "single") -> OperationResult:
    meeting = _require_meeting(meeting_id)
    targets = [meeting]
    if scope == "future" and meeting.series_id:
        targets = [
            item
            for item in list_meeting_sessions()
            if item.series_id == meeting.series_id
            and item.occurrence_index >= meeting.occurrence_index
        ]
    for target in targets:
        for job in list_speech_jobs(target.id):
            delete_audio_assets(job.id)
        if get_microphone_owner() == target.id:
            set_microphone_owner(None)
        if not delete_meeting(target.id):
            raise HTTPException(status_code=404, detail="会议不存在")
    if len(targets) == 1:
        return OperationResult(message="会议及其转写任务已删除")
    return OperationResult(message=f"本次及后续 {len(targets)} 场会议已删除")


@app.get("/api/metrics/baselines", response_model=list[MetricBaseline])
def metric_baselines() -> list[MetricBaseline]:
    return list_metric_baselines()


@app.post("/api/metrics/baselines", response_model=MetricBaseline)
def add_metric_baseline(payload: MetricBaseline) -> MetricBaseline:
    meeting = _require_meeting(payload.meeting_id)
    if meeting.analysis is None:
        raise HTTPException(status_code=409, detail="请先完成会议分析，再记录人工处理基准")
    saved = save_metric_baseline(payload)
    metrics = meeting.analysis.metrics
    metrics.measurement_status = "measured"
    metrics.data_source = payload.source
    metrics.sample_count = len([item for item in list_metric_baselines() if item.meeting_id == meeting.id])
    metrics.baseline_status = "available"
    metrics.baseline_minutes = payload.baseline_minutes
    metrics.post_process_minutes = payload.post_process_minutes
    metrics.savings_percent = round(
        (payload.baseline_minutes - payload.post_process_minutes) / payload.baseline_minutes * 100,
        1,
    )
    meeting.audit_events.append(
        _event(
            "记录减负基准",
            f"人工处理 {payload.baseline_minutes:.1f} 分钟，系统后处理 {payload.post_process_minutes:.1f} 分钟，来源：{payload.source}。",
            "本人",
        )
    )
    save_meeting(meeting)
    return saved


def _directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


@app.get("/api/data/overview", response_model=DataOverview)
def data_overview() -> DataOverview:
    counts = data_counts()
    return DataOverview(
        database_bytes=DB_PATH.stat().st_size if DB_PATH.exists() else 0,
        audio_bytes=_directory_size(AUDIO_ROOT),
        meetings=counts["meetings"],
        workspaces=counts["ads_workspaces"],
        speech_jobs=counts["speech_jobs"],
        backups=[item.name for item in list_backups()],
    )


@app.post("/api/data/backups", response_model=BackupResponse)
def backup_data() -> BackupResponse:
    target = create_backup()
    return BackupResponse(
        filename=target.name,
        created_at=datetime.fromtimestamp(target.stat().st_mtime).astimezone().isoformat(timespec="seconds"),
        size_bytes=target.stat().st_size,
    )


@app.post("/api/data/restore", response_model=OperationResult)
def restore_data(payload: RestoreRequest) -> OperationResult:
    try:
        restore_backup(payload.filename)
        init_db()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="备份文件不存在") from exc
    return OperationResult(message="数据已从备份恢复，请刷新页面")


@app.post("/api/data/audio/cleanup", response_model=OperationResult)
def cleanup_audio(payload: CleanupRequest) -> OperationResult:
    cleaned = 0
    allowed = {"failed", "cancelled"}
    if payload.include_confirmed:
        allowed.add("confirmed")
    for job in list_all_speech_jobs():
        if job.status in allowed and source_for_job(job.id) is not None:
            delete_audio_assets(job.id)
            cleaned += 1
    return OperationResult(message=f"已清理 {cleaned} 个音频文件", detail={"cleaned": cleaned})


@app.post("/api/data/reset", response_model=OperationResult)
def reset_data() -> OperationResult:
    if AUDIO_ROOT.exists():
        for item in AUDIO_ROOT.iterdir():
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            elif item.is_file():
                item.unlink(missing_ok=True)
    reset_product_data()
    return OperationResult(message="业务数据已恢复为空白状态")


# 生产构建存在时，FastAPI 可直接提供前端页面，便于单端口演示。
FRONTEND_DIST = Path(os.environ.get("ADS_FRONTEND_DIST", Path(__file__).resolve().parents[2] / "frontend" / "dist"))
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
