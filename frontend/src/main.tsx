import * as React from "react";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import {
  appendDiarizationOptions,
  isSpeechJobActive,
  speechModelLabel,
  speechProgressLabel,
  speechStatus,
  type DiarizationOptions,
  type SpeechJobStatus,
} from "./speechOptions";
import {
  AlertTriangle,
  Bot,
  CalendarDays,
  Check,
  ChevronRight,
  ClipboardCheck,
  Database,
  Download,
  FileAudio,
  FolderKanban,
  Gauge,
  Home,
  ListChecks,
  LoaderCircle,
  Mic,
  MicOff,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Search,
  Send,
  Settings,
  ShieldCheck,
  Target,
  Trash2,
  UserRound,
  X,
  Square,
  Upload,
  Volume2,
} from "lucide-react";
import {
  calculateDurationMinutes,
  getAgendaDurationError,
  getMeetingTimeRangeError,
  getRecurrenceError,
  getRecurrenceLabel,
  normalizeParticipants,
  validateDelegationDraft,
  type RecurrenceFrequency,
} from "./meetingDraft";
import { isOldMeeting } from "./meetingCleanup";
import {
  getModelRuntimeState,
  getRunnableModelId,
  getRunnableModels,
  type AiRuntimeLike,
  type ModelRuntimeConfig,
} from "./modelRuntime";
import { buildMetricReport, filterDashboardMetrics, findMeetingOverlapIds, isRecordingNavigationExit, savingsPercent, searchProduct, type MetricBaselineRecord, type ProductSearchDocument } from "./productCompletion";
import { findWorkspaceObject, sortDecisionQueue, type WorkspaceObjectTab } from "./workspaceLogic";
import "./styles.css";

type Person = { id: string; name: string; role: string; description?: string };
type Project = { id: string; name: string; description: string; status: string; owner_id: string | null };
type BusinessMetric = { id: string; name: string; current_value: number | null; target_value: number | null; unit: string; objective_id: string | null };
type Risk = { id: string; title: string; impact: string; owner_id: string | null; status: string; project_id: string | null };
type Policy = { id: string; title: string; content: string; scope: string };
type HistoricalStance = { id: string; person_id: string; topic: string; stance: string; effective_scope: string; updated_at: string };
type Objective = { id: string; title: string; progress: number; metric: string; risk: string };
type Task = { id: string; title: string; owner_id: string; due_date: string; status: string };
type AuthorizationRule = { id: string; person_id: string; scope: string; allowed_actions: string[]; escalation_triggers: string[] };
type AdsContext = { people: Person[]; projects: Project[]; objectives: Objective[]; metrics: BusinessMetric[]; risks: Risk[]; tasks: Task[]; policies: Policy[]; historical_stances: HistoricalStance[]; authorization_rules: AuthorizationRule[] };
type AdsWorkspace = AdsContext & { id: string; name: string; description: string; created_at: string; updated_at: string; archived: boolean };
type ModelConfig = ModelRuntimeConfig & {
  provider_name: string; base_url: string; model: string; message: string; api_key_masked: string;
  vendor_id: string; capabilities: string[];
};
type TranscriptSegment = { id: string; sequence: number; start_seconds: number; end_seconds: number; original_text: string; revised_text: string; speaker_label: string; speaker_ambiguous: boolean };
type SpeechJob = {
  id: string; meeting_id: string; source_type: "microphone" | "upload" | "text_stub";
  original_name: string; status: SpeechJobStatus;
  progress: number; language: string; model_name: string; device: string; compute_type: string; full_text: string;
  segments: TranscriptSegment[]; error_code?: string | null; error_message?: string | null;
  mime_type?: string; size_bytes?: number; duration_seconds?: number | null; processing_seconds?: number | null;
  diarization_enabled: boolean; requested_speaker_count?: number | null; detected_speaker_count?: number | null;
  diarization_model?: string | null; diarization_warning?: string | null;
  revisions: Array<{ id: string; segment_id?: string | null; previous_text: string; revised_text: string; revised_at: string }>;
};
type SpeechHealth = { status: "ready" | "degraded" | "not_configured"; ffmpeg_available: boolean; model_available: boolean; message: string; diarization_available: boolean; diarization_model_name?: string | null };
type AiRuntimeStatus = AiRuntimeLike;
type WorkloadMetrics = {
  measurement_status: "pending" | "partial" | "measured";
  data_source: string;
  sample_count: number;
  user_attendance_minutes: number | null;
  agent_processing_minutes: number | null;
  decision_confirmation_minutes: number | null;
  transcript_characters: number;
  minutes_generated_characters: number;
  minutes_edited_characters: number;
  action_items_created: number;
  action_items_written_back: number;
  escalations: number;
  baseline_status: "pending" | "available";
  baseline_minutes: number | null;
  post_process_minutes: number | null;
  savings_percent: number | null;
};
type Analysis = {
  transcript_turns: Array<{ speaker: string; content: string; agent_action: string; linked_object_ids: string[] }>;
  structured_minutes: string;
  decisions: Array<{ id: string; topic: string; content: string; owner_id: string | null; due_date: string | null; evidence: string }>;
  action_items: Array<{ id: string; title: string; owner_id: string | null; due_date: string | null; linked_decision_id: string; status: string; writeback_attempts?: number; writeback_task_id?: string | null; writeback_error?: string | null }>;
  agent_replies: Array<{ question: string; decision: string; reply: string; reason: string; evidence_object_ids: string[] }>;
  ads_relations: Array<{ source_label: string; relation: string; target_label: string }>;
  metrics: WorkloadMetrics;
  writeback_tasks: Task[]; export_markdown: string;
};
type EscalationRequest = {
  id: string; meeting_id: string; question: string; reason: string; ai_recommendation: string;
  status: "pending" | "deferred" | "approved" | "edited" | "rejected" | "expired"; user_reply?: string | null;
  evidence_object_ids: string[]; created_at: string; updated_at: string; reply_deadline?: string | null;
};
type AgendaItem = { topic: string; context: string; suggested_question: string; duration_minutes: number | null };
type AgendaDraftResponse = { agenda_text: string; agenda: AgendaItem[]; mode: "live" | "local_rules" };
type Meeting = {
  id: string; title: string; scenario: string; status: "draft" | "prepared" | "awaiting_confirmation" | "confirmed" | "rejected" | "completed";
  meeting_status: "draft" | "scheduled" | "in_progress" | "ended" | "closed" | "cancelled";
  agent_session_state: "not_started" | "preparing" | "delegating" | "paused" | "completed" | "failed";
  participation_mode: "self" | "delegate"; model_provider_id: string; meeting_type: string; scheduled_at: string; end_at?: string | null; duration_minutes: number;
  series_id?: string | null; occurrence_index: number; recurrence: { frequency: RecurrenceFrequency; end_date?: string | null };
  workspace_id?: string | null;
  agent_identity_id?: string | null; authorization_rule_ids: string[]; auto_reply_enabled: boolean;
  sent_agent_replies: Array<{ id: string; content: string; decision: "suggested" | "sent" | "escalated"; evidence_object_ids: string[]; authorization_rule_ids: string[]; created_at: string }>;
  participants: string[]; objective: string; agenda_text: string; transcript: string; pre_meeting_brief: string;
  agenda: AgendaItem[]; agenda_edited: boolean; analysis: Analysis | null;
  escalation_requests: EscalationRequest[]; confirmation_reply?: string | null;
  audit_events: Array<{ time: string; actor: string; action: string; detail: string }>;
};
type SetupStatus = { requires_onboarding: boolean; requires_migration_choice?: boolean; settings: { onboarding_complete: boolean; active_identity_id: string | null; active_workspace_id: string | null; identities: Person[] }; workspace_count: number };
type ProviderDefinition = { vendor_id: string; name: string; adapter_type: "deepseek" | "openai_compatible"; default_base_url: string; default_model: string; capabilities: string[] };
type DataOverview = { database_bytes: number; audio_bytes: number; meetings: number; workspaces: number; speech_jobs: number; backups: string[] };
type AppSettings = { onboarding_complete: boolean; active_identity_id: string | null; active_workspace_id: string | null; identities: Person[]; audio_retention_days: 0 | 30 | 90 };
type ModelCallAudit = { id: string; meeting_id?: string | null; provider_id: string; model: string; operation: string; status: "success" | "failed" | "fallback"; duration_ms: number; prompt_version: string; token_usage?: number | null; error: string; created_at: string };
type MetricBaseline = MetricBaselineRecord;
type View = "dashboard" | "metrics" | "calendar" | "create" | "meeting" | "decisions" | "ads" | "agents" | "settings";

const initialDraft = {
  title: "", scheduled_at: "", end_at: "", participants: "", objective: "", agenda_text: "",
  agenda: [] as AgendaItem[],
  recurrence_frequency: "none" as RecurrenceFrequency, recurrence_end_date: "",
  participation_mode: "self" as "self" | "delegate", model_provider_id: "", workspace_id: "",
  agent_identity_id: "", authorization_rule_ids: [] as string[], auto_reply_enabled: false,
};

function App() {
  const [view, setView] = React.useState<View>("dashboard");
  const [ads, setAds] = React.useState<AdsContext | null>(null);
  const [workspaces, setWorkspaces] = React.useState<AdsWorkspace[]>([]);
  const [models, setModels] = React.useState<ModelConfig[]>([]);
  const [setup, setSetup] = React.useState<SetupStatus | null>(null);
  const [providers, setProviders] = React.useState<ProviderDefinition[]>([]);
  const [dataOverview, setDataOverview] = React.useState<DataOverview | null>(null);
  const [appSettings, setAppSettings] = React.useState<AppSettings | null>(null);
  const [modelAudits, setModelAudits] = React.useState<ModelCallAudit[]>([]);
  const [metricBaselines, setMetricBaselines] = React.useState<MetricBaseline[]>([]);
  const [aiRuntime, setAiRuntime] = React.useState<AiRuntimeStatus | null>(null);
  const [speechHealth, setSpeechHealth] = React.useState<SpeechHealth | null>(null);
  const [meetings, setMeetings] = React.useState<Meeting[]>([]);
  const [activeMeetingId, setActiveMeetingId] = React.useState("");
  const [draft, setDraft] = React.useState(initialDraft);
  const [transcript, setTranscript] = React.useState("");
  const [speechJobs, setSpeechJobs] = React.useState<SpeechJob[]>([]);
  const [selectedJobId, setSelectedJobId] = React.useState("");
  const [busy, setBusy] = React.useState("");
  const [error, setError] = React.useState("");
  const [success, setSuccess] = React.useState("");
  const [replyDraft, setReplyDraft] = React.useState("");
  const [adsFocus, setAdsFocus] = React.useState<{ workspaceId: string; objectId: string; nonce: number } | null>(null);
  const [recordingMeetingId, setRecordingMeetingId] = React.useState("");
  const [deleteTargetId, setDeleteTargetId] = React.useState("");
  const [meetingEditorId, setMeetingEditorId] = React.useState("");
  const [agendaEditorId, setAgendaEditorId] = React.useState("");
  const speechJobsRequestRef = React.useRef(0);
  const activeMeeting = meetings.find((meeting) => meeting.id === activeMeetingId) ?? null;
  const deleteTarget = meetings.find((meeting) => meeting.id === deleteTargetId) ?? null;
  const meetingEditor = meetings.find((meeting) => meeting.id === meetingEditorId) ?? null;
  const agendaEditor = meetings.find((meeting) => meeting.id === agendaEditorId) ?? null;
  const selectedJob = speechJobs.find((job) => job.id === selectedJobId) ?? speechJobs[0] ?? null;
  const runnableModelId = getRunnableModelId(models, aiRuntime, draft.model_provider_id);
  React.useEffect(() => { void refreshAll(); }, []);
  React.useEffect(() => {
    setSpeechJobs([]);
    setSelectedJobId("");
    if (activeMeeting) void loadSpeechJobs(activeMeeting.id);
    else speechJobsRequestRef.current += 1;
  }, [activeMeeting?.id]);
  React.useEffect(() => {
    const activeJobs = speechJobs.filter((job) => isSpeechJobActive(job.status));
    if (!activeJobs.length) return;
    const timer = window.setInterval(() => { activeJobs.forEach((job) => void refreshSpeechJob(job.id)); }, 1200);
    return () => window.clearInterval(timer);
  }, [speechJobs]);

  async function request<T>(url: string, options?: RequestInit): Promise<T> {
    const response = await fetch(url, options);
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(typeof detail.detail === "string" ? detail.detail : detail.detail?.message ?? "请求失败");
    }
    return response.json() as Promise<T>;
  }
  async function refreshAll() {
    setBusy("refresh"); setError("");
    try {
      const [setupData, adsData, workspaceData, modelData, runtimeData, summaries, speechData, providerData, overviewData, settingsData, auditData, baselineData] = await Promise.all([
        request<SetupStatus>("/api/setup"),
        request<AdsContext>("/api/ads"), request<AdsWorkspace[]>("/api/workspaces"), request<ModelConfig[]>("/api/models"),
        request<AiRuntimeStatus>("/api/ai/status"), request<Array<{ id: string }>>("/api/meetings"), request<SpeechHealth>("/api/speech/health"),
        request<ProviderDefinition[]>("/api/providers"), request<DataOverview>("/api/data/overview"), request<AppSettings>("/api/settings"), request<ModelCallAudit[]>("/api/model-audits"), request<MetricBaseline[]>("/api/metrics/baselines"),
      ]);
      setSetup(setupData); setAds(adsData); setWorkspaces(workspaceData); setModels(modelData); setAiRuntime(runtimeData); setSpeechHealth(speechData); setProviders(providerData); setDataOverview(overviewData); setAppSettings(settingsData); setModelAudits(auditData); setMetricBaselines(baselineData);
      setDraft((current) => ({
        ...current,
        workspace_id: current.workspace_id || workspaceData[0]?.id || "",
        model_provider_id: getRunnableModelId(modelData, runtimeData, current.model_provider_id),
      }));
      const detailed = await Promise.all(summaries.map((meeting) => request<Meeting>(`/api/meetings/${meeting.id}`)));
      const presentable = detailed.filter(isPresentableMeeting);
      setMeetings(presentable);
      setActiveMeetingId((current) => presentable.some((meeting) => meeting.id === current) ? current : "");
    } catch (err) { setError(err instanceof Error ? err.message : "无法连接后端服务，请确认 FastAPI 已启动。"); }
    finally { setBusy(""); }
  }
  async function finishOnboarding(value: { name: string; role: string; workspace_name: string; workspace_description: string }) {
    setBusy("onboarding"); setError("");
    try {
      await request("/api/onboarding", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ identity: { id: `person_${Date.now().toString(36)}`, name: value.name, role: value.role }, workspace_name: value.workspace_name, workspace_description: value.workspace_description }),
      });
      await refreshAll(); setView("agents"); setSuccess("已构建您的 AI 分身，请检查并调整。");
    } catch (err) { setError(err instanceof Error ? err.message : "首次设置失败"); }
    finally { setBusy(""); }
  }
  async function chooseMigration(action: "use_existing" | "create_blank") {
    setBusy("migration"); setError("");
    try { await request("/api/setup/migrate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action }) }); await refreshAll(); }
    catch (err) { setError(err instanceof Error ? err.message : "旧数据迁移选择失败"); }
    finally { setBusy(""); }
  }
  async function createWorkspace() {
    const name = window.prompt("工作区名称"); if (!name?.trim()) return;
    setBusy("workspace-create"); setError("");
    try {
      const created = await request<AdsWorkspace>("/api/workspaces", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: name.trim(), description: "" }) });
      setWorkspaces((items) => [created, ...items]); setSuccess("空白工作区已创建。");
    } catch (err) { setError(err instanceof Error ? err.message : "创建工作区失败"); }
    finally { setBusy(""); }
  }
  async function archiveWorkspace(workspaceId: string, archived: boolean) {
    setBusy(`workspace-archive-${workspaceId}`); setError("");
    try {
      const saved = await request<AdsWorkspace>(`/api/workspaces/${workspaceId}/archive?archived=${archived}`, { method: "PATCH" });
      setWorkspaces((items) => items.map((item) => item.id === saved.id ? saved : item)); setSuccess(archived ? "工作区已归档。" : "工作区已恢复。");
    } catch (err) { setError(err instanceof Error ? err.message : "工作区状态更新失败"); }
    finally { setBusy(""); }
  }
  async function saveWorkspace(workspace: AdsWorkspace) {
    setBusy(`workspace-${workspace.id}`); setError(""); setSuccess("");
    try {
      const saved = await request<AdsWorkspace>(`/api/workspaces/${workspace.id}`, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: workspace.name, description: workspace.description, people: workspace.people, projects: workspace.projects, objectives: workspace.objectives, metrics: workspace.metrics, risks: workspace.risks, tasks: workspace.tasks, policies: workspace.policies, historical_stances: workspace.historical_stances, authorization_rules: workspace.authorization_rules }),
      });
      setWorkspaces((items) => items.map((item) => item.id === saved.id ? saved : item));
      if (workspace.id === workspaces[0]?.id) setAds(saved);
      setSuccess("工作区已保存。");
    } catch (err) { setError(err instanceof Error ? err.message : "ADS 工作区保存失败"); throw err; }
    finally { setBusy(""); }
  }
  async function loadSpeechJobs(meetingId: string) {
    const requestId = ++speechJobsRequestRef.current;
    try {
      const jobs = await request<SpeechJob[]>(`/api/meetings/${meetingId}/speech-jobs`);
      if (requestId !== speechJobsRequestRef.current) return;
      setSpeechJobs(jobs);
      setSelectedJobId(jobs[0]?.id ?? "");
    } catch {
      if (requestId === speechJobsRequestRef.current) {
        setSpeechJobs([]);
        setSelectedJobId("");
      }
    }
  }
  async function refreshSpeechJob(jobId: string) {
    try {
      const job = await request<SpeechJob>(`/api/speech/jobs/${jobId}`);
      setSpeechJobs((items) => items.map((item) => item.id === job.id ? job : item));
    } catch { /* The task may have been deleted from another tab. */ }
  }
  function upsertMeeting(meeting: Meeting) {
    setMeetings((items) => [meeting, ...items.filter((item) => item.id !== meeting.id)]);
  }
  async function draftMeetingAgenda() {
    if (!draft.objective.trim()) {
      setError("请先填写会议内容。");
      return;
    }
    const durationMinutes = calculateDurationMinutes(draft.scheduled_at, draft.end_at);
    if (durationMinutes === null) {
      setError(getMeetingTimeRangeError(draft.scheduled_at, draft.end_at) ?? "请输入有效的会议时间。");
      return;
    }
    const selectedWorkspace = workspaces.find((item) => item.id === draft.workspace_id) ?? workspaces[0];
    if (!runnableModelId) {
      setError("当前没有可运行模型，请先到设置页启用本地规则，或配置并测试在线模型。");
      return;
    }
    setBusy("agenda-draft"); setError(""); setSuccess("");
    try {
      const result = await request<AgendaDraftResponse>("/api/agenda/draft", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          content: draft.objective.trim(),
          duration_minutes: durationMinutes,
          workspace_id: selectedWorkspace?.id ?? null,
          model_provider_id: runnableModelId,
        }),
      });
      setDraft((current) => ({ ...current, agenda_text: result.agenda_text, agenda: result.agenda }));
      setSuccess(result.mode === "live" ? "AI 已整理议程，请检查并调整。" : "已使用本地规则整理议程，请检查并调整。");
    } catch (err) { setError(err instanceof Error ? err.message : "议程整理失败"); }
    finally { setBusy(""); }
  }
  async function createMeeting() {
    if (!draft.title.trim()) {
      setError("请输入会议名称。");
      return;
    }
    if (!draft.objective.trim()) {
      setError("请输入会议内容。");
      return;
    }
    const selectedWorkspace = workspaces.find((item) => item.id === draft.workspace_id) ?? workspaces[0];
    if (!selectedWorkspace) {
      setError("请先在 ADS 工作空间建立业务资料。");
      return;
    }
    const timeRangeError = getMeetingTimeRangeError(draft.scheduled_at, draft.end_at);
    if (timeRangeError) {
      setError(timeRangeError);
      return;
    }
    const durationMinutes = calculateDurationMinutes(draft.scheduled_at, draft.end_at);
    if (durationMinutes === null) {
      setError("请输入有效的会议时间。");
      return;
    }
    const agendaDurationError = getAgendaDurationError(draft.agenda, durationMinutes);
    if (agendaDurationError) {
      setError(agendaDurationError);
      return;
    }
    const recurrenceError = getRecurrenceError(
      draft.recurrence_frequency,
      draft.scheduled_at,
      draft.recurrence_end_date,
    );
    if (recurrenceError) {
      setError(recurrenceError);
      return;
    }
    const delegationErrors = validateDelegationDraft(draft);
    if (delegationErrors.length) {
      setError(delegationErrors[0]);
      return;
    }
    if (!runnableModelId) {
      setError("当前没有可运行模型，请先到设置页启用本地规则，或配置并测试在线模型。");
      return;
    }
    setBusy("create"); setError(""); setSuccess("");
    try {
      const { recurrence_frequency, recurrence_end_date, ...meetingDraft } = draft;
      const payload = {
        ...meetingDraft,
        scenario: "会议",
        meeting_type: "会议",
        duration_minutes: durationMinutes,
        participants: normalizeParticipants(draft.participants),
        model_provider_id: runnableModelId,
        workspace_id: selectedWorkspace?.id ?? "",
        agent_identity_id: draft.participation_mode === "delegate" ? draft.agent_identity_id : null,
        authorization_rule_ids: draft.participation_mode === "delegate" ? draft.authorization_rule_ids : [],
        auto_reply_enabled: draft.participation_mode === "delegate" && draft.auto_reply_enabled,
        recurrence: {
          frequency: recurrence_frequency,
          end_date: recurrence_frequency === "none" ? null : recurrence_end_date,
        },
      };
      const meeting = await request<Meeting>("/api/meetings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      upsertMeeting(meeting); navigate("meeting", meeting.id);
      const prepared = await prepareMeeting(meeting.id);
      if (meeting.series_id) {
        await refreshAll();
        setActiveMeetingId(meeting.id);
      }
      if (prepared) {
        setDraft({
          ...initialDraft,
          workspace_id: selectedWorkspace.id,
          model_provider_id: runnableModelId,
        });
        setSuccess(meeting.series_id ? "循环会议已创建，会前简报已生成。" : "会议已创建，会前简报已生成。");
      }
    } catch (err) { setError(err instanceof Error ? err.message : "创建会议失败"); }
    finally { setBusy(""); }
  }
  async function prepareMeeting(meetingId = activeMeeting?.id, replaceManual = false) {
    if (!meetingId) return false; setBusy("prepare"); setError(""); setSuccess("");
    try { upsertMeeting(await request<Meeting>(`/api/meetings/${meetingId}/prepare${replaceManual ? "?replace_manual=true" : ""}`, { method: "POST" })); setSuccess("会前简报已更新。"); return true; }
    catch (err) {
      const message = err instanceof Error ? err.message : "生成会前准备失败";
      if (!replaceManual && message.includes("人工修订")) {
        setBusy("");
        if (window.confirm("建议议程包含人工修订。确定“重新生成并覆盖”吗？\n取消将保留人工内容。")) return prepareMeeting(meetingId, true);
        setSuccess("已保留人工内容。");
        return false;
      }
      setError(message); return false;
    }
    finally { setBusy(""); }
  }
  async function updateMeeting(meetingId: string, scope: "single" | "future", payload: Record<string, unknown>) {
    setBusy("meeting-edit"); setError(""); setSuccess("");
    try {
      const saved = await request<Meeting>(`/api/meetings/${meetingId}?scope=${scope}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      upsertMeeting(saved);
      if (scope === "future") { await refreshAll(); setActiveMeetingId(meetingId); }
      setMeetingEditorId(""); setSuccess(scope === "future" ? "本次及后续会议已更新。" : "会议信息已更新。");
    } catch (err) { setError(err instanceof Error ? err.message : "会议信息保存失败"); }
    finally { setBusy(""); }
  }
  async function saveMeetingAgenda(meetingId: string, agenda: AgendaItem[]) {
    setBusy("agenda-edit"); setError(""); setSuccess("");
    try {
      upsertMeeting(await request<Meeting>(`/api/meetings/${meetingId}/agenda`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ agenda }) }));
      setAgendaEditorId(""); setSuccess("建议议程已保存，后台不会自动覆盖。");
    } catch (err) { setError(err instanceof Error ? err.message : "建议议程保存失败"); }
    finally { setBusy(""); }
  }
  async function controlAgent(action: "pause" | "resume") {
    if (!activeMeeting) return; setBusy("agent-control"); setError(""); setSuccess("");
    try {
      upsertMeeting(await request<Meeting>(`/api/meetings/${activeMeeting.id}/agent/control`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action }),
      }));
      setSuccess(action === "pause" ? "智能体已暂停，等待本人确认。" : "智能体已恢复协助。");
    } catch (err) { setError(err instanceof Error ? err.message : "委托参会控制失败"); }
    finally { setBusy(""); }
  }
  async function controlMeetingLifecycle(action: "start" | "end" | "reopen") {
    if (!activeMeeting) return false;
    setBusy("meeting-lifecycle"); setError(""); setSuccess("");
    try {
      const meeting = await request<Meeting>(`/api/meetings/${activeMeeting.id}/lifecycle`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action }),
      });
      upsertMeeting(meeting);
      setSuccess(action === "start" ? "会议已开始。" : action === "end" ? "会议已结束；行动项和写回仍可继续处理。" : "会议已重新打开，可以继续记录发言。");
      return true;
    } catch (err) { setError(err instanceof Error ? err.message : "会议状态更新失败"); return false; }
    finally { setBusy(""); }
  }
  async function analyzeMeeting(text = transcript) {
    if (!activeMeeting) return false; setBusy("analyze"); setError(""); setSuccess("");
    try {
      const meeting = await request<Meeting>(`/api/meetings/${activeMeeting.id}/analyze`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ transcript: text }) });
      upsertMeeting(meeting);
      const nextView = meeting.escalation_requests.some((item) => item.status === "pending") ? "decisions" : "meeting";
      if (navigate(nextView, meeting.id)) setTranscript("");
      setSuccess("会议分析已更新。"); return true;
    } catch (err) { setError(err instanceof Error ? err.message : "会议分析失败"); return false; }
    finally { setBusy(""); }
  }
  async function resolveEscalation(meetingId: string, escalationId: string, action: "approve" | "edit" | "reject" | "defer") {
    const reply = replyDraft.trim();
    if (action === "reject" && !reply) { setError("请填写拒绝理由，再返回会议。"); return; }
    setBusy(escalationId); setError(""); setSuccess("");
    try {
      const meeting = await request<Meeting>(`/api/meetings/${meetingId}/escalations/${escalationId}/resolve`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, reply }),
      });
      upsertMeeting(meeting);
      setSuccess(action === "approve" ? "已同意智能体建议。" : action === "edit" ? "已保存修改并返回会议。" : action === "defer" ? "该事项已保留，稍后仍可继续处理。" : "已拒绝该项建议。");
    } catch (err) { setError(err instanceof Error ? err.message : "处理决策失败"); }
    finally { setBusy(""); }
  }
  async function completeActionItem(itemId: string, owner_id: string, due_date: string) {
    if (!activeMeeting) return;
    setBusy(`action-item-${itemId}`); setError(""); setSuccess("");
    try {
      upsertMeeting(await request<Meeting>(`/api/meetings/${activeMeeting.id}/action-items/${itemId}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ owner_id, due_date }) }));
      setSuccess("行动项信息已保存。");
    } catch (err) { setError(err instanceof Error ? err.message : "保存行动项失败"); }
    finally { setBusy(""); }
  }
  async function writeback() {
    if (!activeMeeting) return; setBusy("writeback"); setError(""); setSuccess("");
    try { upsertMeeting(await request<Meeting>(`/api/meetings/${activeMeeting.id}/writeback`, { method: "POST" })); setSuccess("行动项已写回 ADS，会议进程未改变。"); }
    catch (err) { setError(err instanceof Error ? err.message : "回写失败，请先补全负责人和截止日期。"); }
    finally { setBusy(""); }
  }
  async function writebackItem(itemId: string) {
    if (!activeMeeting) return; setBusy(`writeback-${itemId}`); setError(""); setSuccess("");
    try { upsertMeeting(await request<Meeting>(`/api/meetings/${activeMeeting.id}/action-items/${itemId}/writeback`, { method: "POST" })); setSuccess("该行动项已写回 ADS。"); await refreshWorkspaces(); }
    catch (err) { setError(err instanceof Error ? err.message : "行动项写回失败，可单独重试。"); }
    finally { setBusy(""); }
  }
  async function refreshWorkspaces() {
    const items = await request<AdsWorkspace[]>("/api/workspaces"); setWorkspaces(items);
    const context = await request<AdsContext>("/api/ads"); setAds(context);
  }
  async function askAgent(question: string) {
    if (!activeMeeting) return null;
    setBusy("agent-ask"); setError("");
    try { return await request<{ answer: string; evidence_object_ids: string[]; mode: "live" | "local_rules" }>(`/api/meetings/${activeMeeting.id}/agent/ask`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }) }); }
    catch (err) { setError(err instanceof Error ? err.message : "智能体回答失败"); return null; }
    finally { setBusy(""); }
  }
  async function controlMicrophone(action: "acquire" | "release") {
    if (!activeMeeting) return false;
    try { await request(`/api/meetings/${activeMeeting.id}/microphone`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action }) }); return true; }
    catch (err) { setError(err instanceof Error ? err.message : "麦克风当前被其他会议占用"); return false; }
  }
  async function uploadAudio(file: File, sourceType: "upload" | "microphone", options: DiarizationOptions) {
    if (!activeMeeting) return; setBusy("speech"); setError(""); setSuccess("");
    try {
      const form = new FormData();
      form.append("meeting_id", activeMeeting.id); form.append("source_type", sourceType); form.append("language", "zh"); form.append("file", file);
      appendDiarizationOptions(form, options);
      const job = await request<SpeechJob>("/api/speech/transcriptions", { method: "POST", body: form });
      setSpeechJobs((items) => [job, ...items.filter((item) => item.id !== job.id)]); setSelectedJobId(job.id);
      if (job.status === "failed") setError(job.error_message ?? "转写失败，请改用文字输入或检查本地语音组件。");
      else setSuccess("音频已加入本地转写队列。");
    } catch (err) { setError(err instanceof Error ? err.message : "音频上传或转写失败"); }
    finally { setBusy(""); }
  }
  async function cancelSpeechJob(jobId: string) {
    setBusy(`speech-cancel-${jobId}`); setError(""); setSuccess("");
    try {
      const job = await request<SpeechJob>(`/api/speech/jobs/${jobId}/cancel`, { method: "POST" });
      setSpeechJobs((items) => items.map((item) => item.id === job.id ? job : item));
      setSuccess("转写已暂停，原始音频已保留。");
    } catch (err) { setError(err instanceof Error ? err.message : "取消转写失败"); }
    finally { setBusy(""); }
  }
  async function retrySpeechJob(jobId: string) {
    setBusy(`speech-retry-${jobId}`); setError(""); setSuccess("");
    try {
      const job = await request<SpeechJob>(`/api/speech/jobs/${jobId}/retry`, { method: "POST" });
      setSpeechJobs((items) => items.map((item) => item.id === job.id ? job : item)); setSelectedJobId(job.id);
      setSuccess("已重新加入转写队列。");
    } catch (err) { setError(err instanceof Error ? err.message : "重新转写失败"); }
    finally { setBusy(""); }
  }
  async function deleteSpeechJob(jobId: string) {
    const job = speechJobs.find((item) => item.id === jobId);
    if (!job || !window.confirm(`删除音频任务“${job.original_name}”？未确认的转写内容也会被删除。`)) return;
    setBusy(`speech-delete-${jobId}`); setError(""); setSuccess("");
    try {
      await request<SpeechJob>(`/api/speech/jobs/${jobId}`, { method: "DELETE" });
      setSpeechJobs((items) => items.filter((item) => item.id !== jobId));
      setSelectedJobId((current) => current === jobId ? "" : current);
      setSuccess("音频任务已删除。");
    } catch (err) { setError(err instanceof Error ? err.message : "删除音频任务失败"); }
    finally { setBusy(""); }
  }
  async function saveSegment(segment: TranscriptSegment, value: Partial<TranscriptSegment>) {
    if (!selectedJob) return;
    try {
      const job = await request<SpeechJob>(`/api/speech/jobs/${selectedJob.id}/segments/${segment.id}`, {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ revised_text: value.revised_text ?? segment.revised_text, speaker_label: value.speaker_label ?? segment.speaker_label }),
      });
      setSpeechJobs((items) => items.map((item) => (item.id === job.id ? job : item)));
    } catch (err) { setError(err instanceof Error ? err.message : "保存转写片段失败"); }
  }
  async function saveFullTranscript(value: string) {
    if (!selectedJob || !value.trim()) return;
    try {
      const job = await request<SpeechJob>(`/api/speech/jobs/${selectedJob.id}/transcript`, {
        method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ full_text: value }),
      });
      setSpeechJobs((items) => items.map((item) => (item.id === job.id ? job : item)));
    } catch (err) { setError(err instanceof Error ? err.message : "保存完整转写失败"); }
  }
  async function confirmSpeechAndAnalyze() {
    if (!selectedJob) return;
    setBusy("speech-confirm"); setError(""); setSuccess("");
    try {
      const result = await request<{ job: SpeechJob; transcript: string }>(`/api/speech/jobs/${selectedJob.id}/confirm`, { method: "POST" });
      setSpeechJobs((items) => items.map((item) => (item.id === result.job.id ? result.job : item)));
      setTranscript(result.transcript);
      if (await analyzeMeeting(result.transcript)) setSuccess("转写已确认，会议分析已更新。");
    } catch (err) { setError(err instanceof Error ? err.message : "确认转写失败"); }
    finally { setBusy(""); }
  }
  async function saveModel(model: ModelConfig, apiKey = "") {
    setBusy(`model-${model.provider_id}`); setError(""); setSuccess("");
    try {
      const saved = await request<ModelConfig>(`/api/models/${model.provider_id}`, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider_id: model.provider_id, provider_name: model.provider_name, adapter_type: model.adapter_type,
          base_url: model.base_url, model: model.model, api_key: apiKey,
          enabled: model.enabled, is_default: model.is_default,
        }),
      });
      const refreshed = await request<ModelConfig[]>("/api/models");
      setModels(refreshed.map((item) => item.provider_id === saved.provider_id ? saved : item));
      setSuccess("模型配置已保存。");
    } catch (err) { setError(err instanceof Error ? err.message : "模型配置保存失败"); }
    finally { setBusy(""); }
  }
  async function testModel(providerId: string) {
    setBusy(`model-test-${providerId}`); setError(""); setSuccess("");
    try {
      const tested = await request<ModelConfig>(`/api/models/${providerId}/test`, { method: "POST" });
      setModels((items) => items.map((item) => item.provider_id === providerId ? tested : item));
      setSuccess(tested.connection_status === "ok" || tested.connection_status === "mock" ? "模型连接正常。" : tested.message || "模型连接失败。");
    } catch (err) { setError(err instanceof Error ? err.message : "模型连接测试失败"); }
    finally { setBusy(""); }
  }
  async function installProvider(vendorId: string) {
    setBusy("provider-install"); setError("");
    try { const model = await request<ModelConfig>(`/api/providers/${vendorId}/install`, { method: "POST" }); setModels((items) => [...items, model]); setSuccess("模型服务已加入配置列表。"); }
    catch (err) { setError(err instanceof Error ? err.message : "添加模型服务失败"); }
    finally { setBusy(""); }
  }
  async function createDataBackup() {
    setBusy("data-backup"); setError("");
    try { await request("/api/data/backups", { method: "POST" }); setDataOverview(await request<DataOverview>("/api/data/overview")); setSuccess("本地备份已创建。"); }
    catch (err) { setError(err instanceof Error ? err.message : "创建备份失败"); }
    finally { setBusy(""); }
  }
  async function restoreData(filename: string) {
    if (!window.confirm(`从“${filename}”恢复？当前业务数据将被备份内容覆盖。`)) return;
    setBusy("data-restore"); setError("");
    try { await request("/api/data/restore", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ filename }) }); await refreshAll(); setSuccess("数据已恢复。"); }
    catch (err) { setError(err instanceof Error ? err.message : "恢复备份失败"); }
    finally { setBusy(""); }
  }
  async function cleanupAudio() {
    if (!window.confirm("清理失败、取消和已确认任务的本地音频？转写与审计记录会保留。")) return;
    setBusy("data-cleanup"); setError("");
    try { await request("/api/data/audio/cleanup", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ include_confirmed: true }) }); setDataOverview(await request<DataOverview>("/api/data/overview")); setSuccess("音频清理完成。"); }
    catch (err) { setError(err instanceof Error ? err.message : "清理音频失败"); }
    finally { setBusy(""); }
  }
  async function saveAudioRetention(days: 0 | 30 | 90) {
    setBusy("settings-retention"); setError("");
    try { const saved = await request<AppSettings>("/api/settings", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ audio_retention_days: days }) }); setAppSettings(saved); setSuccess(days ? `原始音频将在 ${days} 天后自动清理。` : "原始音频将长期保留。"); }
    catch (err) { setError(err instanceof Error ? err.message : "保存音频保留期失败"); }
    finally { setBusy(""); }
  }
  async function saveIdentity(identity: Person) {
    setBusy("identity-save"); setError(""); setSuccess("");
    try {
      const saved = await request<AppSettings>("/api/settings", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ identity, active_identity_id: identity.id }) });
      setAppSettings(saved); await refreshWorkspaces(); setSuccess("本人身份已保存并同步到当前工作区。");
    } catch (err) { setError(err instanceof Error ? err.message : "保存本人身份失败"); }
    finally { setBusy(""); }
  }
  async function selectIdentity(identityId: string) {
    setBusy("identity-select"); setError("");
    try { setAppSettings(await request<AppSettings>("/api/settings", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ active_identity_id: identityId }) })); setSuccess("当前本人身份已切换。"); }
    catch (err) { setError(err instanceof Error ? err.message : "切换本人身份失败"); }
    finally { setBusy(""); }
  }
  async function saveMetricBaseline(baseline: MetricBaseline) {
    setBusy("metric-baseline"); setError(""); setSuccess("");
    try {
      const saved = await request<MetricBaseline>("/api/metrics/baselines", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(baseline) });
      setMetricBaselines((items) => [saved, ...items.filter((item) => item.id !== saved.id)]);
      upsertMeeting(await request<Meeting>(`/api/meetings/${saved.meeting_id}`));
      setSuccess("人工基准已保存，单场减负结果已更新。");
    } catch (err) { setError(err instanceof Error ? err.message : "保存减负基准失败"); }
    finally { setBusy(""); }
  }
  async function resetData() {
    if (!window.confirm("恢复空白数据？会议、工作区、语音任务和本地音频都会删除，建议先创建备份。")) return;
    setBusy("data-reset"); setError("");
    try { await request("/api/data/reset", { method: "POST" }); window.location.reload(); }
    catch (err) { setError(err instanceof Error ? err.message : "恢复空白数据失败"); }
    finally { setBusy(""); }
  }
  async function requestDeleteMeeting(meetingId: string) {
    const meeting = meetings.find((item) => item.id === meetingId);
    if (!meeting) return;
    if (meeting.series_id) {
      setDeleteTargetId(meetingId);
      return;
    }
    if (!window.confirm(`删除会议“${meeting.title}”及其音频任务？`)) return;
    await deleteMeetingData(meetingId, "single");
  }
  async function deleteMeetingData(meetingId: string, scope: "single" | "future") {
    const meeting = meetings.find((item) => item.id === meetingId);
    if (!meeting) return;
    setBusy(`meeting-delete-${meetingId}`); setError("");
    try {
      await request(`/api/meetings/${meetingId}?scope=${scope}`, { method: "DELETE" });
      setMeetings((items) => items.filter((item) => (
        scope === "future" && meeting.series_id
          ? item.series_id !== meeting.series_id || item.occurrence_index < meeting.occurrence_index
          : item.id !== meetingId
      )));
      setDeleteTargetId("");
      setDataOverview(await request<DataOverview>("/api/data/overview"));
      setSuccess(scope === "future" ? "本次及后续会议已删除。" : "本次会议已删除。");
    }
    catch (err) { setError(err instanceof Error ? err.message : "删除会议失败"); }
    finally { setBusy(""); }
  }
  async function selectMeetingModel(providerId: string) {
    if (!activeMeeting) return; setBusy("meeting-model"); setError(""); setSuccess("");
    try {
      upsertMeeting(await request<Meeting>(`/api/meetings/${activeMeeting.id}/model`, {
        method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ model_provider_id: providerId }),
      }));
      setSuccess("本场会议模型已更新。");
    } catch (err) { setError(err instanceof Error ? err.message : "切换会议模型失败"); }
    finally { setBusy(""); }
  }
  function openAdsObject(workspaceId: string | null | undefined, objectId: string) {
    if (!workspaceId) { setError("该来源未关联 ADS 工作区。"); return; }
    if (navigate("ads")) setAdsFocus({ workspaceId, objectId, nonce: Date.now() });
  }
  function navigate(nextView: View, meetingId?: string) {
    const leavesRecording = isRecordingNavigationExit(recordingMeetingId, nextView, meetingId);
    if (leavesRecording && !window.confirm("当前会议正在录音。离开将取消并丢弃本次未结束的录音，是否继续？")) return false;
    const switchesMeeting = Boolean(meetingId && meetingId !== activeMeetingId);
    if (switchesMeeting && transcript.trim() && !window.confirm("当前会议有未提交文字。切换会议将丢弃这些内容，是否继续？")) return false;
    if (leavesRecording) setRecordingMeetingId("");
    if (switchesMeeting) setTranscript("");
    if (meetingId) setActiveMeetingId(meetingId);
    setView(nextView);
    return true;
  }
  function openMetricBaseline() {
    if (!navigate("settings")) return;
    window.setTimeout(() => {
      const target = document.getElementById("metric-baseline");
      target?.focus({ preventScroll: true });
      target?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 0);
  }

  if (!setup) return <main className="startup-loading"><LoaderCircle className="spin" size={24} /><span>正在检查本地运行环境</span>{error && <p>{error}</p>}</main>;
  if (setup.requires_migration_choice) return <main className="onboarding-shell"><section className="onboarding-rail"><div className="logo large">ADS</div><div><span>发现旧版本数据</span><h1>选择如何开始</h1><p>旧工作区不会被自动删除，也不会被注入新业务数据。</p></div></section><section className="onboarding-form"><header><span>首次升级</span><h2>保留现有工作区吗？</h2></header>{error && <div className="inline-error">{error}</div>}<button className="primary-button" disabled={busy === "migration"} onClick={() => void chooseMigration("use_existing")}>继续使用已有工作区</button><button className="secondary-button" disabled={busy === "migration"} onClick={() => void chooseMigration("create_blank")}>创建新的空白工作区</button></section></main>;
  if (setup.requires_onboarding) return <Onboarding busy={busy === "onboarding"} error={error} speechHealth={speechHealth} onComplete={finishOnboarding} />;

  const overlapIds = findMeetingOverlapIds(meetings);
  const activeIdentity = appSettings?.identities.find((item) => item.id === appSettings.active_identity_id) ?? appSettings?.identities[0];
  const activeWorkspaceId = workspaces.some((item) => item.id === appSettings?.active_workspace_id)
    ? appSettings?.active_workspace_id ?? ""
    : workspaces.find((item) => !item.archived)?.id ?? workspaces[0]?.id ?? "";

  return (
    <main className="app">
      <Sidebar view={view} setView={(next) => void navigate(next)} pending={meetings.flatMap((m) => m.escalation_requests).filter((e) => e.status === "pending").length} />
      <section className="main-shell">
        <Topbar meetings={meetings} workspaces={workspaces} activeMeetingId={activeMeeting?.id ?? ""} activeIdentity={activeIdentity} busy={busy} onRefresh={refreshAll} onNavigate={(next) => void navigate(next)} onOpenMeeting={(id) => void navigate("meeting", id)} onOpenDecision={(id) => void navigate("decisions", id)} onOpenSource={openAdsObject} />
        {error && <div className="feedback-banner error-banner" role="alert"><AlertTriangle size={17} /><span>{error}</span><button type="button" className="notice-dismiss" onClick={() => setError("")} title="关闭提示" aria-label="关闭错误提示"><X size={15} /></button></div>}
        {success && <div className="feedback-banner success-banner" role="status" aria-live="polite"><Check size={17} /><span>{success}</span><button type="button" className="notice-dismiss" onClick={() => setSuccess("")} title="关闭提示" aria-label="关闭成功提示"><X size={15} /></button></div>}
        {view === "dashboard" && <Dashboard meetings={meetings} overlapIds={overlapIds} onOpenMeeting={(id) => void navigate("meeting", id)} onNavigate={(next) => void navigate(next)} />}
        {view === "metrics" && <DataDashboard meetings={meetings} baselines={metricBaselines} workspaces={workspaces} initialWorkspaceId={activeWorkspaceId} onOpenBaseline={openMetricBaseline} />}
        {view === "calendar" && <CalendarView meetings={meetings} overlapIds={overlapIds} busy={busy} onOpenMeeting={(id) => void navigate("meeting", id)} onDeleteMeeting={requestDeleteMeeting} />}
        {view === "create" && <CreateMeeting draft={draft} setDraft={setDraft} models={models} aiRuntime={aiRuntime} workspaces={workspaces.filter((item) => !item.archived)} busy={busy === "create"} agendaBusy={busy === "agenda-draft"} onDraftAgenda={draftMeetingAgenda} onCreate={createMeeting} />}
        {view === "meeting" && (activeMeeting ? <MeetingWorkspace meeting={activeMeeting} ads={workspaces.find((item) => item.id === activeMeeting.workspace_id) ?? ads} speechHealth={speechHealth} transcript={transcript} setTranscript={setTranscript} busy={busy} speechJobs={speechJobs} selectedJob={selectedJob} selectJob={setSelectedJobId} recordingActive={recordingMeetingId === activeMeeting.id} onRecordingChange={(active) => setRecordingMeetingId(active ? activeMeeting.id : "")} onPrepare={() => prepareMeeting()} onEditMeeting={() => setMeetingEditorId(activeMeeting.id)} onEditAgenda={() => setAgendaEditorId(activeMeeting.id)} onAgentControl={controlAgent} onLifecycle={controlMeetingLifecycle} onAnalyze={() => analyzeMeeting()} onUploadAudio={uploadAudio} onCancelSpeech={cancelSpeechJob} onRetrySpeech={retrySpeechJob} onDeleteSpeech={deleteSpeechJob} onSaveSegment={saveSegment} onSaveFullTranscript={saveFullTranscript} onConfirmSpeech={confirmSpeechAndAnalyze} onCompleteActionItem={completeActionItem} onWriteback={writeback} onWritebackItem={writebackItem} onMicrophone={controlMicrophone} onOpenSource={(id) => openAdsObject(activeMeeting.workspace_id, id)} /> : <MeetingSelection meetings={meetings} onSelect={(id) => void navigate("meeting", id)} onCreate={() => void navigate("create")} />)}
        {view === "decisions" && <DecisionCenter meetings={meetings} workspaces={workspaces} replyDraft={replyDraft} setReplyDraft={setReplyDraft} onOpenMeeting={(id) => void navigate("meeting", id)} onOpenSource={openAdsObject} onResolve={resolveEscalation} busy={busy} />}
        {view === "ads" && <AdsWorkspace workspaces={workspaces} focus={adsFocus} busy={busy} onSave={saveWorkspace} onCreate={createWorkspace} onArchive={archiveWorkspace} />}
        {view === "agents" && <AgentCenter meetings={meetings} workspaces={workspaces} settings={appSettings} models={models} aiRuntime={aiRuntime} busy={busy} onSaveIdentity={saveIdentity} onSelectIdentity={selectIdentity} onNavigate={(next) => void navigate(next)} onOpenMeeting={(id) => void navigate("meeting", id)} />}
        {view === "settings" && <SettingsView models={models} aiRuntime={aiRuntime} providers={providers} audits={modelAudits} baselines={metricBaselines} meetings={meetings} settings={appSettings} speechHealth={speechHealth} dataOverview={dataOverview} busy={busy} onSave={saveModel} onTest={testModel} onInstallProvider={installProvider} onSaveBaseline={saveMetricBaseline} onBackup={createDataBackup} onRestore={restoreData} onCleanup={cleanupAudio} onRetention={saveAudioRetention} onReset={resetData} onDeleteMeeting={requestDeleteMeeting} />}
      </section>
      {deleteTarget && <DeleteMeetingDialog meeting={deleteTarget} busy={busy === `meeting-delete-${deleteTarget.id}`} onCancel={() => setDeleteTargetId("")} onDelete={(scope) => void deleteMeetingData(deleteTarget.id, scope)} />}
      {meetingEditor && <MeetingEditDialog meeting={meetingEditor} workspace={workspaces.find((item) => item.id === meetingEditor.workspace_id) ?? null} busy={busy === "meeting-edit"} onClose={() => setMeetingEditorId("")} onSave={(scope, payload) => void updateMeeting(meetingEditor.id, scope, payload)} />}
      {agendaEditor && <AgendaEditDialog meeting={agendaEditor} busy={busy === "agenda-edit"} onClose={() => setAgendaEditorId("")} onSave={(agenda) => void saveMeetingAgenda(agendaEditor.id, agenda)} />}
    </main>
  );
}

function DeleteMeetingDialog(props: { meeting: Meeting; busy: boolean; onCancel: () => void; onDelete: (scope: "single" | "future") => void }) {
  return <div className="modal-backdrop delete-scope-backdrop"><section className="delete-scope-dialog" role="dialog" aria-modal="true" aria-labelledby="delete-scope-title">
    <header><div><span>循环会议</span><h2 id="delete-scope-title">删除哪一部分？</h2></div></header>
    <div className="dialog-body"><strong>{cleanText(props.meeting.title)}</strong><p>{formatMeetingTimeRange(props.meeting.scheduled_at, props.meeting.duration_minutes)} · {getRecurrenceLabel(props.meeting.recurrence.frequency)}</p><div className="delete-scope-note"><AlertTriangle size={17} /><span>删除会同时清理对应会议的转写任务和音频，无法撤销。</span></div></div>
    <footer><button type="button" className="secondary-button" autoFocus onClick={props.onCancel} disabled={props.busy}>取消</button><button type="button" className="danger-button" onClick={() => props.onDelete("single")} disabled={props.busy}>仅本次</button><button type="button" className="danger-button danger-filled" onClick={() => props.onDelete("future")} disabled={props.busy}>{props.busy ? "正在删除" : "本次及后续"}</button></footer>
  </section></div>;
}

function meetingDateTimeInput(value: string) { return value.replace(" ", "T").slice(0, 16); }
function meetingEndInput(meeting: Meeting) {
  if (meeting.end_at) return meetingDateTimeInput(meeting.end_at);
  const start = new Date(meetingDateTimeInput(meeting.scheduled_at));
  if (Number.isNaN(start.getTime())) return "";
  start.setMinutes(start.getMinutes() + meeting.duration_minutes);
  const local = new Date(start.getTime() - start.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function MeetingEditDialog(props: { meeting: Meeting; workspace: AdsWorkspace | null; busy: boolean; onClose: () => void; onSave: (scope: "single" | "future", payload: Record<string, unknown>) => void }) {
  const locked = !["draft", "scheduled"].includes(props.meeting.meeting_status);
  const originalEnd = meetingEndInput(props.meeting);
  const [draft, setDraft] = React.useState({ title: props.meeting.title, scheduled_at: meetingDateTimeInput(props.meeting.scheduled_at), end_at: originalEnd, participants: props.meeting.participants.join("、"), objective: props.meeting.objective, participation_mode: props.meeting.participation_mode, agent_identity_id: props.meeting.agent_identity_id ?? props.workspace?.people[0]?.id ?? "", authorization_rule_ids: props.meeting.authorization_rule_ids.length ? props.meeting.authorization_rule_ids : props.workspace?.authorization_rules.slice(0, 1).map((item) => item.id) ?? [], auto_reply_enabled: props.meeting.auto_reply_enabled });
  const [scope, setScope] = React.useState<"single" | "future">("single");
  const [validation, setValidation] = React.useState("");
  function save() {
    if (!draft.title.trim()) { setValidation("请填写会议名称。"); return; }
    const timeError = locked ? null : getMeetingTimeRangeError(draft.scheduled_at, draft.end_at);
    if (timeError) { setValidation(timeError); return; }
    if (!locked && draft.participation_mode === "delegate" && (!draft.agent_identity_id || !draft.authorization_rule_ids.length)) { setValidation("委托智能体时，请选择代理身份和至少一条本场授权。"); return; }
    const participants = normalizeParticipants(draft.participants);
    const payload: Record<string, unknown> = {};
    if (draft.title.trim() !== props.meeting.title) payload.title = draft.title.trim();
    if (draft.objective.trim() !== props.meeting.objective) payload.objective = draft.objective.trim();
    if (participants.join("\n") !== props.meeting.participants.join("\n")) payload.participants = participants;
    if (!locked) {
      if (draft.scheduled_at !== meetingDateTimeInput(props.meeting.scheduled_at)) payload.scheduled_at = draft.scheduled_at;
      if (draft.end_at !== originalEnd) payload.end_at = draft.end_at;
      if (draft.participation_mode !== props.meeting.participation_mode) payload.participation_mode = draft.participation_mode;
      if (draft.participation_mode === "delegate") {
        payload.agent_identity_id = draft.agent_identity_id;
        payload.authorization_rule_ids = draft.authorization_rule_ids;
        payload.auto_reply_enabled = draft.auto_reply_enabled;
      }
    }
    if (!Object.keys(payload).length) { props.onClose(); return; }
    props.onSave(scope, payload);
  }
  return <div className="modal-backdrop" onMouseDown={props.onClose}><section className="edit-dialog meeting-edit-dialog" role="dialog" aria-modal="true" aria-labelledby="meeting-edit-title" onMouseDown={(event) => event.stopPropagation()}><header><div><span>会议设置</span><h2 id="meeting-edit-title">编辑会议信息</h2></div><button className="icon-button" onClick={props.onClose} title="关闭"><X size={18} /></button></header><div className="dialog-body meeting-edit-fields">
    {locked && <div className="edit-lock-note"><AlertTriangle size={17} /><span>会议已开始或结束，时间、参会人和参会方式已锁定；名称和会议内容仍可修改。</span></div>}
    <label>会议名称<input autoFocus value={draft.title} onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))} /></label>
    <div className="form-grid"><label>开始时间<input type="datetime-local" value={draft.scheduled_at} disabled={locked} onChange={(event) => setDraft((current) => ({ ...current, scheduled_at: event.target.value }))} /></label><label>结束时间<input type="datetime-local" value={draft.end_at} disabled={locked} onChange={(event) => setDraft((current) => ({ ...current, end_at: event.target.value }))} /></label></div>
    <label>参会人<input value={draft.participants} disabled={locked} onChange={(event) => setDraft((current) => ({ ...current, participants: event.target.value }))} placeholder="用顿号或换行分隔" /></label>
    <label>会议内容<textarea value={draft.objective} onChange={(event) => setDraft((current) => ({ ...current, objective: event.target.value }))} /></label>
    <label>参会方式<select value={draft.participation_mode} disabled={locked} onChange={(event) => setDraft((current) => ({ ...current, participation_mode: event.target.value as "self" | "delegate" }))}><option value="self">本人参加</option><option value="delegate">委托智能体</option></select></label>
    {!locked && draft.participation_mode === "delegate" && <div className="delegation-edit-fields"><label>代理身份<select value={draft.agent_identity_id} onChange={(event) => setDraft((current) => ({ ...current, agent_identity_id: event.target.value }))}><option value="">请选择</option>{props.workspace?.people.map((person) => <option key={person.id} value={person.id}>{person.name} · {person.role}</option>)}</select></label><fieldset><legend>本场授权</legend>{props.workspace?.authorization_rules.map((rule) => <label className="check-row" key={rule.id}><input type="checkbox" checked={draft.authorization_rule_ids.includes(rule.id)} onChange={(event) => setDraft((current) => ({ ...current, authorization_rule_ids: event.target.checked ? [...current.authorization_rule_ids, rule.id] : current.authorization_rule_ids.filter((id) => id !== rule.id) }))} /><span>{rule.scope}</span></label>)}</fieldset><label className="check-row"><input type="checkbox" checked={draft.auto_reply_enabled} onChange={(event) => setDraft((current) => ({ ...current, auto_reply_enabled: event.target.checked }))} /><span>授权范围内自动回复</span></label></div>}
    {validation && <p className="validation-hint">{validation}</p>}
  </div><footer>{props.meeting.series_id && <div className="scope-choice"><span>保存范围</span><button type="button" className={scope === "single" ? "active" : ""} onClick={() => setScope("single")}>仅本次</button><button type="button" className={scope === "future" ? "active" : ""} onClick={() => setScope("future")}>本次及后续</button></div>}<button type="button" className="secondary-button" onClick={props.onClose} disabled={props.busy}>取消</button><button type="button" className="primary-button" onClick={save} disabled={props.busy}>{props.busy ? "正在保存" : "保存更改"}</button></footer></section></div>;
}

function AgendaEditDialog(props: { meeting: Meeting; busy: boolean; onClose: () => void; onSave: (agenda: AgendaItem[]) => void }) {
  const [agenda, setAgenda] = React.useState(() => props.meeting.agenda.map((item) => ({ ...item })));
  const [validation, setValidation] = React.useState("");
  function update(index: number, value: Partial<AgendaItem>) { setAgenda((items) => items.map((item, itemIndex) => itemIndex === index ? { ...item, ...value } : item)); }
  function save() {
    const error = getAgendaDurationError(agenda, props.meeting.duration_minutes);
    if (error) { setValidation(error); return; }
    props.onSave(agenda);
  }
  return <div className="modal-backdrop" onMouseDown={props.onClose}><section className="edit-dialog agenda-edit-dialog" role="dialog" aria-modal="true" aria-labelledby="agenda-edit-title" onMouseDown={(event) => event.stopPropagation()}><header><div><span>人工修订</span><h2 id="agenda-edit-title">编辑建议议程</h2></div><button className="icon-button" onClick={props.onClose} title="关闭"><X size={18} /></button></header><div className="dialog-body agenda-edit-list"><div className="agenda-duration-summary"><span>会议总时长</span><strong>{agenda.reduce((sum, item) => sum + (item.duration_minutes ?? 0), 0)} / {props.meeting.duration_minutes} 分钟</strong></div>{agenda.map((item, index) => <article key={index}><div className="agenda-edit-index">{String(index + 1).padStart(2, "0")}</div><label>议题<input value={item.topic} onChange={(event) => update(index, { topic: event.target.value })} /></label><label className="minutes-field">分钟<input type="number" min={1} max={480} value={item.duration_minutes ?? ""} onChange={(event) => update(index, { duration_minutes: Number(event.target.value) || null })} /></label><label className="wide-field">背景<textarea value={item.context} onChange={(event) => update(index, { context: event.target.value })} /></label><label className="wide-field">建议问题<input value={item.suggested_question} onChange={(event) => update(index, { suggested_question: event.target.value })} /></label></article>)}{validation && <p className="validation-hint">{validation}</p>}</div><footer><span className="dialog-footnote">保存后，重新生成必须明确确认覆盖。</span><button type="button" className="secondary-button" onClick={props.onClose} disabled={props.busy}>取消</button><button type="button" className="primary-button" onClick={save} disabled={props.busy}>{props.busy ? "正在保存" : "保存议程"}</button></footer></section></div>;
}

function Onboarding(props: { busy: boolean; error: string; speechHealth: SpeechHealth | null; onComplete: (value: { name: string; role: string; workspace_name: string; workspace_description: string }) => void }) {
  const [form, setForm] = React.useState({ name: "", role: "", workspace_name: "", workspace_description: "" });
  const update = (key: keyof typeof form, value: string) => setForm((current) => ({ ...current, [key]: value }));
  return <main className="onboarding-shell"><section className="onboarding-rail"><div className="logo large">ADS</div><div><span>本地会议协作产品</span><h1>建立你的工作环境</h1><p>一次完成人员身份和空白工作区。进入产品后可在设置中调整运行模型。</p></div><div className="readiness-list"><div className={props.speechHealth?.status === "ready" ? "ready" : "warn"}><Mic size={18} /><span>本地语音</span><strong>{props.speechHealth?.status === "ready" ? "可用" : "需检查"}</strong></div><div className="ready"><Database size={18} /><span>本地数据</span><strong>空白</strong></div></div></section><section className="onboarding-form"><header><span>首次启动</span><h2>身份与工作区</h2></header><div className="onboarding-fields"><label>你的姓名<input autoFocus value={form.name} onChange={(event) => update("name", event.target.value)} placeholder="用于代理身份和审计记录" /></label><label>岗位或职责<input value={form.role} onChange={(event) => update("role", event.target.value)} placeholder="例如：项目负责人" /></label><label>团队工作区名称<input value={form.workspace_name} onChange={(event) => update("workspace_name", event.target.value)} placeholder="例如：产品研发团队" /></label><label>工作区说明<textarea value={form.workspace_description} onChange={(event) => update("workspace_description", event.target.value)} placeholder="说明团队范围或主要业务" /></label><div className={props.speechHealth?.status === "ready" ? "onboarding-check ready" : "onboarding-check warn"}><Mic size={16} /><span>{props.speechHealth?.message ?? "正在检查本地语音"}</span></div></div>{props.error && <div className="inline-error">{props.error}</div>}<button className="primary-button onboarding-submit" disabled={props.busy || !form.name.trim() || !form.workspace_name.trim()} onClick={() => props.onComplete(form)}>{props.busy ? <LoaderCircle className="spin" size={17} /> : <ChevronRight size={17} />}{props.busy ? "正在保存" : "完成配置并检查 AI 分身"}</button></section></main>;
}

function Sidebar(props: { view: View; setView: (view: View) => void; pending: number }) {
  const items: Array<[View, React.ReactNode, string]> = [["dashboard", <Home size={20} />, "工作台"], ["metrics", <Gauge size={20} />, "数据看板"], ["calendar", <CalendarDays size={20} />, "会议"], ["create", <Plus size={20} />, "创建"], ["meeting", <Bot size={20} />, "现场"], ["decisions", <AlertTriangle size={20} />, "决策"], ["ads", <Database size={20} />, "ADS"], ["agents", <ShieldCheck size={20} />, "智能体"], ["settings", <Settings size={20} />, "设置"]];
  return <aside className="sidebar"><div className="logo">ADS</div>{items.map(([id, icon, label]) => <button className={props.view === id ? "nav-item active" : "nav-item"} key={id} onClick={() => props.setView(id)}>{icon}<span>{label}</span>{id === "decisions" && props.pending > 0 && <b>{props.pending}</b>}</button>)}</aside>;
}
function Topbar(props: { meetings: Meeting[]; workspaces: AdsWorkspace[]; activeMeetingId: string; activeIdentity?: Person; busy: string; onRefresh: () => void; onNavigate: (view: View) => void; onOpenMeeting: (id: string) => void; onOpenDecision: (meetingId: string) => void; onOpenSource: (workspaceId: string, objectId: string) => void }) {
  const [query, setQuery] = React.useState("");
  const [now, setNow] = React.useState(new Date());
  React.useEffect(() => { const timer = window.setInterval(() => setNow(new Date()), 30_000); return () => window.clearInterval(timer); }, []);
  const documents = React.useMemo(() => {
    const items: ProductSearchDocument[] = [];
    props.meetings.forEach((meeting) => {
      items.push({ id: meeting.id, kind: "会议", title: cleanText(meeting.title), searchText: `${meeting.objective} ${meeting.participants.join(" ")}`, meetingId: meeting.id });
      meeting.analysis?.decisions.forEach((decision) => items.push({ id: decision.id, kind: "决策", title: cleanText(decision.content), searchText: decision.evidence, meetingId: meeting.id }));
      meeting.escalation_requests.forEach((decision) => items.push({ id: decision.id, kind: "决策", title: cleanText(decision.question), searchText: `${decision.reason} ${decision.user_reply ?? ""}`, meetingId: meeting.id }));
    });
    props.workspaces.forEach((workspace) => {
      items.push({ id: workspace.id, kind: "工作区", title: workspace.name, searchText: workspace.description, workspaceId: workspace.id });
      workspace.people.forEach((item) => items.push({ id: item.id, kind: "成员", title: item.name, searchText: item.role, workspaceId: workspace.id }));
      workspace.projects.forEach((item) => items.push({ id: item.id, kind: "项目", title: item.name, searchText: `${item.description} ${item.status}`, workspaceId: workspace.id }));
      workspace.objectives.forEach((item) => items.push({ id: item.id, kind: "目标", title: item.title, searchText: `${item.metric} ${item.risk}`, workspaceId: workspace.id }));
      workspace.metrics.forEach((item) => items.push({ id: item.id, kind: "指标", title: item.name, searchText: `${item.current_value ?? ""} ${item.target_value ?? ""} ${item.unit}`, workspaceId: workspace.id }));
      workspace.risks.forEach((item) => items.push({ id: item.id, kind: "风险", title: item.title, searchText: `${item.impact} ${item.status}`, workspaceId: workspace.id }));
      workspace.tasks.forEach((item) => items.push({ id: item.id, kind: "任务", title: item.title, searchText: `${item.status} ${item.due_date}`, workspaceId: workspace.id }));
      workspace.policies.forEach((item) => items.push({ id: item.id, kind: "制度", title: item.title, searchText: `${item.content} ${item.scope}`, workspaceId: workspace.id }));
      workspace.historical_stances.forEach((item) => items.push({ id: item.id, kind: "历史立场", title: item.topic, searchText: `${item.stance} ${item.effective_scope}`, workspaceId: workspace.id }));
      workspace.authorization_rules.forEach((item) => items.push({ id: item.id, kind: "授权", title: item.scope, searchText: `${item.allowed_actions.join(" ")} ${item.escalation_triggers.join(" ")}`, workspaceId: workspace.id }));
    });
    return items;
  }, [props.meetings, props.workspaces]);
  const results = searchProduct(query, documents);
  function openResult(item: ProductSearchDocument) {
    if (item.kind === "会议" && item.meetingId) props.onOpenMeeting(item.meetingId);
    else if (item.kind === "决策" && item.meetingId) props.onOpenDecision(item.meetingId);
    else if (item.kind === "工作区") props.onNavigate("ads");
    else if (item.workspaceId) props.onOpenSource(item.workspaceId, item.id);
    setQuery("");
  }
  return <header className="topbar"><div className="search-wrap"><div className="search-box"><Search size={17} /><input aria-label="全局搜索" placeholder="搜索会议、决策及全部 ADS 对象" value={query} onChange={(event) => setQuery(event.target.value)} /></div>{query.trim() && <div className="search-results">{results.map((item) => <button key={`${item.kind}-${item.id}`} onClick={() => openResult(item)}><span>{item.kind}</span><strong>{item.title}</strong></button>)}{!results.length && <p>没有匹配结果</p>}</div>}</div><label className="current-meeting-selector"><span>当前会议</span><select aria-label="当前会议" value={props.activeMeetingId} onChange={(event) => props.onOpenMeeting(event.target.value)}><option value="" disabled>选择当前会议</option>{props.meetings.map((meeting) => <option key={meeting.id} value={meeting.id}>{cleanText(meeting.title)} · {meeting.scheduled_at.slice(0, 16)} · {meetingLifecycleText(meeting.meeting_status)}</option>)}</select></label><span className="clock">{now.toLocaleString("zh-CN", { month: "long", day: "numeric", weekday: "short", hour: "2-digit", minute: "2-digit", hour12: false })}</span><button className="icon-button" onClick={props.onRefresh} title="刷新"><RefreshCw size={17} className={props.busy === "refresh" ? "spin" : ""} /></button><div className="avatar" title={props.activeIdentity ? `${props.activeIdentity.name} · ${props.activeIdentity.role}` : "本人身份未配置"}>{props.activeIdentity?.name.slice(0, 1) ?? "人"}</div></header>;
}
function MeetingSelection(props: { meetings: Meeting[]; onSelect: (id: string) => void; onCreate: () => void }) {
  return <section className="page-grid meeting-selection-page"><header className="page-heading"><div><span className="kicker">会议现场</span><h1>选择当前会议</h1><p>尚未选择当前会议。确认会议名称、时间和状态后再进入，避免把发言或录音提交到错误会议。</p></div></header><section className="panel wide"><div className="section-bar"><h2>可选择的会议</h2><button className="primary-button" onClick={props.onCreate}><Plus size={16} />新建会议</button></div><div className="meeting-list">{props.meetings.map((meeting) => <MeetingRow key={meeting.id} title={cleanText(meeting.title)} time={meeting.scheduled_at} mode={meeting.participation_mode === "delegate" ? "委托智能体" : "本人参加"} status={<MeetingStateSummary meeting={meeting} compact />} onClick={() => props.onSelect(meeting.id)} />)}{!props.meetings.length && <Empty text="还没有会议。请先新建会议，再进入现场。" />}</div></section></section>;
}
function Dashboard(props: { meetings: Meeting[]; overlapIds: Set<string>; onOpenMeeting: (id: string) => void; onNavigate: (view: View) => void }) {
  const pending = props.meetings.flatMap((meeting) => meeting.escalation_requests.filter((item) => item.status === "pending"));
  const delegated = props.meetings.filter((meeting) => meeting.participation_mode === "delegate" && meeting.meeting_status !== "cancelled");
  const closed = props.meetings.filter((meeting) => meeting.meeting_status === "ended" || meeting.meeting_status === "closed");
  const upcoming = props.meetings.slice(0, 6);
  const headline = props.meetings.length
    ? `你有 ${props.meetings.length} 场会议，${delegated.length} 场由 ADS 智能体协助处理。`
    : "开始你的会议";
  return <section className="dashboard-grid"><div className="hero-panel"><div><span className="kicker">会议工作台</span><h1>{headline}</h1></div><button className="primary-button" onClick={() => props.onNavigate("create")}><Plus size={17} />新建会议</button></div><Metric label="全部会议" value={`${props.meetings.length} 场`} tone="blue" /><Metric label="智能体协助" value={`${delegated.length} 场`} tone="green" /><Metric label="待处理决策" value={`${pending.length} 项`} tone="orange" /><Metric label="已完成会议" value={`${closed.length} 场`} tone="green" />{props.overlapIds.size > 0 && <section className="overlap-alert wide"><AlertTriangle size={19} /><div><strong>发现 {props.overlapIds.size} 场时间重叠的活动会议</strong><span>请确认本人参加和智能体委托安排；同一时刻只有一场会议可以占用麦克风。</span></div></section>}<section className="panel wide"><PanelTitle icon={<CalendarDays size={18} />} title="近期会议" /><div className="meeting-list">{upcoming.map((meeting) => <MeetingRow key={meeting.id} title={cleanText(meeting.title)} time={meeting.scheduled_at} mode={`${meeting.participation_mode === "delegate" ? "委托智能体" : "本人参加"}${props.overlapIds.has(meeting.id) ? " · 时间重叠" : ""}`} status={<MeetingStateSummary meeting={meeting} compact />} hot={meeting.meeting_status === "in_progress" || props.overlapIds.has(meeting.id)} onClick={() => props.onOpenMeeting(meeting.id)} />)}{!upcoming.length && <Empty text="还没有会议。新建会议后，会前简报、会议过程和行动项会集中显示在这里。" />}</div></section><section className="panel"><PanelTitle icon={<AlertTriangle size={18} />} title="需要你处理" />{pending.length ? pending.slice(0, 4).map((item) => <article className="decision-mini" key={item.id}><strong>{cleanText(item.question)}</strong><span>{cleanText(item.reason)}</span></article>) : <Empty text="当前没有需要本人处理的决策。" />}</section></section>;
}
function DataDashboard(props: { meetings: Meeting[]; baselines: MetricBaseline[]; workspaces: AdsWorkspace[]; initialWorkspaceId: string; onOpenBaseline: () => void }) {
  const [workspaceId, setWorkspaceId] = React.useState(props.initialWorkspaceId);
  const [startDate, setStartDate] = React.useState("");
  const [endDate, setEndDate] = React.useState("");
  const selectedWorkspaceId = props.workspaces.some((item) => item.id === workspaceId)
    ? workspaceId
    : props.initialWorkspaceId || props.workspaces[0]?.id || "";
  const selectedWorkspace = props.workspaces.find((item) => item.id === selectedWorkspaceId) ?? null;
  const invalidDateRange = Boolean(startDate && endDate && startDate > endDate);
  const scoped = filterDashboardMetrics(props.meetings, props.baselines, selectedWorkspaceId, startDate, endDate);
  const dateLabel = startDate && endDate ? `${startDate} 至 ${endDate}` : startDate ? `${startDate} 起` : endDate ? `截至 ${endDate}` : "全部时间";
  const scopeLabel = `${selectedWorkspace?.name ?? "未选择工作区"} · ${dateLabel}`;
  return <section className="page-grid">
    <header className="page-heading"><div><h1>数据看板</h1><p>按明确范围查看会议处理过程、人工对照和减负成效。</p></div><button className="secondary-button" onClick={props.onOpenBaseline}><Plus size={15} />录入人工基准</button></header>
    <section className="panel wide dashboard-scope" aria-labelledby="dashboard-scope-title">
      <div className="section-heading"><div><h2 id="dashboard-scope-title">统计范围</h2><p>会议按开始日期筛选；人工对照还需关联入选会议，并按样本日期筛选。</p></div></div>
      <div className="dashboard-scope-fields">
        <label>业务工作区<select value={selectedWorkspaceId} onChange={(event) => setWorkspaceId(event.target.value)} disabled={!props.workspaces.length}>{props.workspaces.map((workspace) => <option key={workspace.id} value={workspace.id}>{workspace.name}{workspace.archived ? "（已归档）" : ""}</option>)}{!props.workspaces.length && <option value="">暂无工作区</option>}</select></label>
        <label>开始日期<input type="date" max={endDate || undefined} value={startDate} onChange={(event) => setStartDate(event.target.value)} /></label>
        <label>结束日期<input type="date" min={startDate || undefined} value={endDate} onChange={(event) => setEndDate(event.target.value)} /></label>
        <button className="secondary-button" onClick={() => { setStartDate(""); setEndDate(""); }} disabled={!startDate && !endDate}>全部时间</button>
      </div>
      {invalidDateRange ? <p className="inline-error" role="alert">结束日期不能早于开始日期，请调整统计范围。</p> : <p className="scope-summary">当前范围：<strong>{scopeLabel}</strong> · {scoped.meetings.length} 场会议 · {scoped.baselines.length} 组人工对照</p>}
    </section>
    <WorkloadImpactPanel meetings={scoped.meetings} baselines={scoped.baselines} scopeLabel={scopeLabel} />
    <section className="panel wide metric-definitions"><div className="section-heading"><div><h2>指标口径</h2><p>所有数字只来自当前筛选范围内的已保存记录。</p></div></div><dl><div><dt>系统样本</dt><dd>存在分析结果且已经记录过程数据的会议数。</dd></div><div><dt>会议发言 / 结构化纪要</dt><dd>分别汇总已保存转写和当前有效纪要的字符数。</dd></div><div><dt>行动项 / 本人确认</dt><dd>分别汇总已识别行动项和授权外升级事项数量。</dd></div><div><dt>人工对照</dt><dd>必须关联当前范围内会议，并按基准样本日期计入。</dd></div><div><dt>综合节省比例</dt><dd>（总人工处理分钟－总系统后处理分钟）÷ 总人工处理分钟。</dd></div><div><dt>无人工基准时</dt><dd>只展示过程数据，不根据字符数或主观判断推算节省比例。</dd></div></dl></section>
  </section>;
}
function WorkloadImpactPanel(props: { meetings: Meeting[]; baselines: MetricBaseline[]; scopeLabel: string }) {
  const analyses = props.meetings.flatMap((meeting) => {
    const metrics = meeting.analysis?.metrics;
    return metrics && metrics.measurement_status !== "pending" ? [metrics] : [];
  });
  const transcriptCharacters = analyses.reduce((sum, metrics) => sum + metrics.transcript_characters, 0);
  const minutesCharacters = analyses.reduce((sum, metrics) => sum + metrics.minutes_generated_characters, 0);
  const actions = analyses.reduce((sum, metrics) => sum + metrics.action_items_created, 0);
  const escalations = analyses.reduce((sum, metrics) => sum + metrics.escalations, 0);
  const baselineMinutes = props.baselines.reduce((sum, item) => sum + item.baseline_minutes, 0);
  const postMinutes = props.baselines.reduce((sum, item) => sum + item.post_process_minutes, 0);
  const savings = baselineMinutes > 0 ? savingsPercent(baselineMinutes, postMinutes) : null;
  return <section className="panel wide workload-panel"><div className="workload-heading"><PanelTitle icon={<Gauge size={18} />} title="减负成效" /><span className="data-status">{props.baselines.length ? "人工基准已记录" : analyses.length ? "过程数据已记录" : "待采集"}</span></div><div className="workload-meta"><span>范围：{props.scopeLabel}</span><span>系统样本：{analyses.length}</span><span>人工对照：{props.baselines.length}</span></div><div className="workload-grid"><article><span>会议发言</span><strong>{formatCount(transcriptCharacters)}</strong><small>已记录字符</small></article><article><span>结构化纪要</span><strong>{formatCount(minutesCharacters)}</strong><small>已生成字符</small></article><article><span>行动项</span><strong>{actions}</strong><small>已识别</small></article><article><span>本人确认</span><strong>{escalations}</strong><small>待处理或已处理</small></article></div><div className="comparison-bars"><div><span>人工处理</span><b>{props.baselines.length ? `${baselineMinutes.toFixed(1)} 分钟` : "待采集"}</b><i><em style={{ width: props.baselines.length ? "100%" : "0%" }} /></i></div><div><span>系统后处理</span><b>{props.baselines.length ? `${postMinutes.toFixed(1)} 分钟` : analyses.length ? "过程已记录" : "待采集"}</b><i><em className="active" style={{ width: baselineMinutes > 0 ? `${Math.max(0, Math.min(100, postMinutes / baselineMinutes * 100))}%` : "0%" }} /></i></div></div><p className="workload-note">{savings === null ? "补齐实际人工计时后，系统才会计算节省比例。" : `基于 ${props.baselines.length} 组实际计时，综合节省比例为 ${savings.toFixed(1)}%。`}</p></section>;
}
function CalendarView(props: { meetings: Meeting[]; overlapIds: Set<string>; busy: string; onOpenMeeting: (id: string) => void; onDeleteMeeting: (meetingId: string) => Promise<void> }) {
  const oldMeetings = props.meetings.filter((meeting) => isOldMeeting(meeting));
  return <section className="page-grid"><section className="panel wide"><PanelTitle icon={<CalendarDays size={18} />} title="日历与会议" />{props.overlapIds.size > 0 && <div className="calendar-overlap-note"><AlertTriangle size={16} />{props.overlapIds.size} 场活动会议存在时间重叠</div>}<details className="calendar-cleanup"><summary><span><Trash2 size={15} />清理旧会议</span><b>{oldMeetings.length}</b></summary><p>只列出已结束、已关闭、已取消或时间已过的会议。删除时会同时清理该会议的转写任务和音频。</p>{oldMeetings.length ? <div className="cleanup-meeting-list">{oldMeetings.map((meeting) => <article key={meeting.id}><div><strong>{cleanText(meeting.title)}{meeting.series_id && <span className="recurrence-badge">{getRecurrenceLabel(meeting.recurrence.frequency)}</span>}</strong><span>{formatMeetingTimeRange(meeting.scheduled_at, meeting.duration_minutes)} · {statusText(meeting)}</span></div><button className="danger-button" aria-label={`删除会议 ${cleanText(meeting.title)}`} onClick={() => void props.onDeleteMeeting(meeting.id)} disabled={props.busy === `meeting-delete-${meeting.id}`}><Trash2 size={14} />删除</button></article>)}</div> : <Empty text="当前没有可清理的旧会议。" />}</details><div className="timeline">{props.meetings.map((meeting) => <button className={props.overlapIds.has(meeting.id) ? "timeline-row overlap" : "timeline-row"} key={meeting.id} onClick={() => props.onOpenMeeting(meeting.id)}><span>{meeting.scheduled_at}</span><strong>{cleanText(meeting.title)}{meeting.series_id && <span className="recurrence-badge">{getRecurrenceLabel(meeting.recurrence.frequency)}</span>}</strong><em>{meeting.participation_mode === "delegate" ? "委托智能体" : "本人参加"}</em><small>{props.overlapIds.has(meeting.id) ? "时间重叠" : statusText(meeting)}</small></button>)}{!props.meetings.length && <Empty text="还没有会议。创建会议后，会前准备和会议结果会显示在这里。" />}</div></section></section>;
}
function CreateMeeting(props: { draft: typeof initialDraft; setDraft: React.Dispatch<React.SetStateAction<typeof initialDraft>>; models: ModelConfig[]; aiRuntime: AiRuntimeStatus | null; workspaces: AdsWorkspace[]; busy: boolean; agendaBusy: boolean; onDraftAgenda: () => void; onCreate: () => void }) {
  function update<K extends keyof typeof initialDraft>(key: K, value: (typeof initialDraft)[K]) { props.setDraft((draft) => ({ ...draft, [key]: value })); }
  function selectMode(mode: "self" | "delegate") {
    props.setDraft((draft) => ({
      ...draft,
      participation_mode: mode,
      ...(mode === "self" ? { agent_identity_id: "", authorization_rule_ids: [], auto_reply_enabled: false } : {}),
    }));
  }
  function selectWorkspace(workspaceId: string) {
    props.setDraft((draft) => ({ ...draft, workspace_id: workspaceId, agent_identity_id: "", authorization_rule_ids: [] }));
  }
  function selectRecurrence(frequency: RecurrenceFrequency) {
    props.setDraft((draft) => ({
      ...draft,
      recurrence_frequency: frequency,
      recurrence_end_date: frequency === "none" ? "" : draft.recurrence_end_date,
    }));
  }
  function toggleAuthorization(ruleId: string) {
    props.setDraft((draft) => ({
      ...draft,
      authorization_rule_ids: draft.authorization_rule_ids.includes(ruleId)
        ? draft.authorization_rule_ids.filter((id) => id !== ruleId)
        : [...draft.authorization_rule_ids, ruleId],
    }));
  }
  function updateAgenda(index: number, patch: Partial<AgendaItem>) {
    props.setDraft((draft) => {
      const agenda = draft.agenda.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item);
      const agenda_text = agenda.map((item) => `${item.duration_minutes ?? 0} 分钟｜${item.topic}`).join("\n");
      return { ...draft, agenda, agenda_text };
    });
  }
  const workspace = props.workspaces.find((item) => item.id === props.draft.workspace_id) ?? props.workspaces[0];
  const participantNames = normalizeParticipants(props.draft.participants);
  const timeRangeError = getMeetingTimeRangeError(props.draft.scheduled_at, props.draft.end_at);
  const recurrenceError = getRecurrenceError(props.draft.recurrence_frequency, props.draft.scheduled_at, props.draft.recurrence_end_date);
  const durationMinutes = calculateDurationMinutes(props.draft.scheduled_at, props.draft.end_at);
  const agendaDurationError = durationMinutes === null ? null : getAgendaDurationError(props.draft.agenda, durationMinutes);
  const agendaTotal = props.draft.agenda.reduce((sum, item) => sum + (item.duration_minutes ?? 0), 0);
  const delegationErrors = validateDelegationDraft(props.draft);
  const runnableModels = getRunnableModels(props.models, props.aiRuntime);
  const selectedModelId = getRunnableModelId(props.models, props.aiRuntime, props.draft.model_provider_id);
  const selectedModel = runnableModels.find((model) => model.provider_id === selectedModelId);
  return <section className="create-page">
    <header className="page-heading"><h1>新建会议</h1></header>
    <div className="create-steps"><span className="active"><b>1</b>会议信息</span><span><b>2</b>会议关联信息</span><span><b>3</b>参会方式与 AI</span></div>
    <div className="create-grid">
      <section className="panel create-section">
        <PanelTitle icon={<ClipboardCheck size={18} />} title="会议信息" />
        <label>会议名称<input value={props.draft.title} placeholder="输入会议名称" onChange={(event) => update("title", event.target.value)} /></label>
        <fieldset className="time-range"><legend>会议时间</legend><div className="form-pair"><label>开始时间<input type="datetime-local" value={props.draft.scheduled_at.replace(" ", "T")} onChange={(event) => update("scheduled_at", event.target.value.replace("T", " "))} /></label><label>结束时间<input type="datetime-local" min={props.draft.scheduled_at.replace(" ", "T")} value={props.draft.end_at.replace(" ", "T")} onChange={(event) => update("end_at", event.target.value.replace("T", " "))} /></label></div>{timeRangeError && (props.draft.scheduled_at || props.draft.end_at) && <p className="validation-hint">{timeRangeError}</p>}<div className={props.draft.recurrence_frequency === "none" ? "recurrence-control" : "recurrence-control active"}><label>重复<select value={props.draft.recurrence_frequency} onChange={(event) => selectRecurrence(event.target.value as RecurrenceFrequency)}><option value="none">不重复</option><option value="weekly">每周</option><option value="biweekly">每两周</option><option value="monthly">每月</option></select></label>{props.draft.recurrence_frequency !== "none" && <label>循环截止日期<input type="date" min={props.draft.scheduled_at.slice(0, 10)} value={props.draft.recurrence_end_date} onChange={(event) => update("recurrence_end_date", event.target.value)} /></label>}</div>{recurrenceError && props.draft.recurrence_frequency !== "none" && <p className="validation-hint recurrence-error">{recurrenceError}</p>}</fieldset>
        <label>参会人员<input value={props.draft.participants} placeholder="使用顿号、逗号或换行分隔" onChange={(event) => update("participants", event.target.value)} /></label>
        {participantNames.length > 0 && <div className="participant-chips">{participantNames.map((name) => <span key={name}>{name.slice(0, 1)}<b>{name}</b></span>)}</div>}
      </section>
      <section className="panel create-section">
        <PanelTitle icon={<Database size={18} />} title="会议关联信息" />
        <p className="section-description">选择本次会议要使用的团队资料，智能体将据此识别相关目标、任务和授权边界。</p>
        <label>业务工作区<select value={workspace?.id ?? ""} onChange={(event) => selectWorkspace(event.target.value)}>{props.workspaces.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
        {workspace ? <div className="context-summary"><strong>{workspace.name}</strong><p>{workspace.description || "该工作区暂未填写说明"}</p><dl><div><dt>成员</dt><dd>{workspace.people.length}</dd></div><div><dt>目标</dt><dd>{workspace.objectives.length}</dd></div><div><dt>任务</dt><dd>{workspace.tasks.length}</dd></div><div><dt>授权</dt><dd>{workspace.authorization_rules.length}</dd></div></dl></div> : <p className="inline-error">请先在 ADS 工作空间建立业务资料。</p>}
        <div className="meeting-content-field"><div className="content-field-heading"><label htmlFor="meeting-content">会议内容</label><button type="button" className="secondary-button" onClick={props.onDraftAgenda} disabled={props.agendaBusy || !props.draft.objective.trim() || !selectedModelId} aria-busy={props.agendaBusy}>{props.agendaBusy ? <LoaderCircle className="spin" size={15} /> : <Bot size={15} />}{props.agendaBusy ? "正在整理" : "AI 自动整理"}</button></div><textarea id="meeting-content" value={props.draft.objective} placeholder="自由描述本次会议要讨论、确认和推进的事项" onChange={(event) => update("objective", event.target.value)} /></div>
        {props.draft.agenda.length > 0 && <section className="agenda-draft-preview"><header><div><span>建议议程</span><strong>可在创建前调整</strong></div><b className={agendaDurationError ? "invalid" : ""}>{agendaTotal} / {durationMinutes ?? 0} 分钟</b></header><div>{props.draft.agenda.map((item, index) => <article key={`${index}-${item.topic}`}><label>分钟<input type="number" min={1} max={durationMinutes ?? 480} value={item.duration_minutes ?? ""} onChange={(event) => updateAgenda(index, { duration_minutes: Number(event.target.value) || null })} /></label><label>议题<input value={item.topic} onChange={(event) => updateAgenda(index, { topic: event.target.value })} /></label><label className="agenda-context">背景<textarea value={item.context} onChange={(event) => updateAgenda(index, { context: event.target.value })} /></label><label className="agenda-question">建议问题<input value={item.suggested_question} onChange={(event) => updateAgenda(index, { suggested_question: event.target.value })} /></label></article>)}</div>{agendaDurationError && <p className="validation-hint">{agendaDurationError}</p>}</section>}
      </section>
      <section className="panel create-section">
        <PanelTitle icon={<Bot size={18} />} title="参会方式与 AI" />
        <div className="mode-selector"><button type="button" className={props.draft.participation_mode === "self" ? "active" : ""} onClick={() => selectMode("self")}><UserRound size={19} /><strong>本人参加</strong><span>智能体协助转写、总结与任务提取</span></button><button type="button" className={props.draft.participation_mode === "delegate" ? "active" : ""} onClick={() => selectMode("delegate")}><Bot size={19} /><strong>委托智能体</strong><span>授权内自主处理，超权时请求确认</span></button></div>
        <label>使用模型<select value={selectedModelId} onChange={(event) => update("model_provider_id", event.target.value)} disabled={!runnableModels.length}>{runnableModels.map((model) => <option key={model.provider_id} value={model.provider_id}>{model.provider_name} · {model.model}</option>)}</select></label>
        <p className={selectedModel?.adapter_type === "mock" ? "model-runtime-note mock" : "model-runtime-note"}><strong>当前实际运行：</strong>{selectedModel ? selectedModel.adapter_type === "mock" ? "本地规则，本场不会调用在线大模型。" : `${selectedModel.provider_name} · ${selectedModel.model}` : "没有可运行模型，请先到设置页完成配置。"}</p>
        {props.draft.participation_mode === "delegate" ? <div className="delegation-config">
          <label>代理身份<select aria-label="代理身份" value={props.draft.agent_identity_id} onChange={(event) => update("agent_identity_id", event.target.value)}><option value="">请选择工作区成员</option>{workspace?.people.map((person) => <option key={person.id} value={person.id}>{person.name} · {person.role}</option>)}</select></label>
          <fieldset className="authorization-picker"><legend>本场授权</legend>{workspace?.authorization_rules.length ? <div className="authorization-options">{workspace.authorization_rules.map((rule) => <label className="authorization-option" key={rule.id}><input type="checkbox" checked={props.draft.authorization_rule_ids.includes(rule.id)} onChange={() => toggleAuthorization(rule.id)} /><span><strong>{workspace.people.find((person) => person.id === rule.person_id)?.name ?? "工作区成员"}</strong><small>{rule.scope}</small></span></label>)}</div> : <p className="inline-error">当前工作区没有授权规则，请先到 ADS 中添加。</p>}</fieldset>
          <label className="auto-reply-control"><input type="checkbox" checked={props.draft.auto_reply_enabled} onChange={(event) => update("auto_reply_enabled", event.target.checked)} /><span><strong>授权内自动回复</strong><small>关闭时只生成回复建议；超权事项始终交由本人确认。</small></span></label>
          {delegationErrors.length > 0 && <p className="delegation-hint">{delegationErrors.join(" ")}</p>}
        </div> : <div className="authorization-preview"><ShieldCheck size={18} /><div><strong>本人参加</strong><p>智能体只提供转写、整理和回复建议，不会自动代表你发言。</p></div></div>}
        <button className="primary-button create-submit" onClick={props.onCreate} disabled={props.busy || !selectedModelId} aria-busy={props.busy}>{props.busy ? <LoaderCircle className="spin" size={17} /> : <Plus size={17} />}{props.busy ? "正在创建" : "创建并生成会前简报"}</button>
      </section>
    </div>
  </section>;
}

type MeetingTab = "overview" | "brief" | "live" | "results" | "audit";
function MeetingWorkspace(props: { meeting: Meeting; ads: AdsContext | null; speechHealth: SpeechHealth | null; transcript: string; setTranscript: (value: string) => void; busy: string; speechJobs: SpeechJob[]; selectedJob: SpeechJob | null; selectJob: (id: string) => void; recordingActive: boolean; onRecordingChange: (active: boolean) => void; onPrepare: () => void; onEditMeeting: () => void; onEditAgenda: () => void; onAgentControl: (action: "pause" | "resume") => void; onLifecycle: (action: "start" | "end" | "reopen") => Promise<boolean>; onAnalyze: () => void; onUploadAudio: (file: File, sourceType: "upload" | "microphone", options: DiarizationOptions) => void; onCancelSpeech: (jobId: string) => void; onRetrySpeech: (jobId: string) => void; onDeleteSpeech: (jobId: string) => void; onSaveSegment: (segment: TranscriptSegment, value: Partial<TranscriptSegment>) => void; onSaveFullTranscript: (value: string) => void; onConfirmSpeech: () => void; onCompleteActionItem: (itemId: string, ownerId: string, dueDate: string) => void; onWriteback: () => void; onWritebackItem: (itemId: string) => void; onMicrophone: (action: "acquire" | "release") => Promise<boolean>; onOpenSource: (id: string) => void }) {
  const meeting = props.meeting;
  const [tab, setTab] = React.useState<MeetingTab>(meeting.status === "draft" ? "brief" : "live");
  React.useEffect(() => setTab(meeting.status === "draft" ? "brief" : "live"), [meeting.id]);
  const tabItems: Array<[MeetingTab, string, number?]> = [["overview", "概览"], ["brief", "会前准备"], ["live", "会议现场"], ["results", "会议成果", meeting.analysis?.action_items.length], ["audit", "审计与来源"]];
  function openTab(next: MeetingTab) {
    if (tab === "live" && next !== "live" && props.recordingActive && !window.confirm("当前正在录音。切换页签将取消并丢弃本次录音，是否继续？")) return;
    setTab(next);
  }
  const lifecycleAction = meeting.meeting_status === "scheduled" ? "start" : meeting.meeting_status === "in_progress" ? "end" : meeting.meeting_status === "ended" || meeting.meeting_status === "closed" ? "reopen" : null;
  async function runLifecycle(action: "start" | "end" | "reopen") {
    if (action === "end") {
      if (props.recordingActive) return;
      if (!window.confirm("确认结束本场会议？结束后不能继续提交发言，但行动项和 ADS 写回仍可继续处理。")) return;
    }
    if (await props.onLifecycle(action)) setTab(action === "end" ? "results" : "live");
  }
  return <section className="meeting-control-room">
    <header className="meeting-commandbar"><div><span className="kicker">{formatMeetingTimeRange(meeting.scheduled_at, meeting.duration_minutes)}</span><h1>{cleanText(meeting.title)}</h1><div className="meeting-meta"><span>{meeting.participants.length} 位参会人</span><span>{meeting.participation_mode === "delegate" ? "委托智能体" : "本人参加"}</span>{meeting.series_id && <span className="series-meta">{getRecurrenceLabel(meeting.recurrence.frequency)} · 第 {meeting.occurrence_index + 1} 场</span>}{meeting.auto_reply_enabled && <span>授权内自动回复</span>}</div></div><div className="command-status"><div className="command-actions"><button type="button" className="secondary-button" onClick={props.onEditMeeting}>编辑会议信息</button>{lifecycleAction === "start" && <button type="button" className="primary-button" onClick={() => void runLifecycle("start")} disabled={props.busy === "meeting-lifecycle"}><Play size={15} />开始会议</button>}{lifecycleAction === "end" && <button type="button" className="danger-button" title={props.recordingActive ? "请先结束或取消当前录音" : "结束本场会议"} onClick={() => void runLifecycle("end")} disabled={props.busy === "meeting-lifecycle" || props.recordingActive}><Square size={15} />结束会议</button>}{lifecycleAction === "reopen" && <button type="button" className="secondary-button" onClick={() => void runLifecycle("reopen")} disabled={props.busy === "meeting-lifecycle"}><RefreshCw size={15} />重新打开会议</button>}</div><MeetingStateSummary meeting={meeting} /></div></header>
    <div className="meeting-people">{meeting.participants.map((name, index) => <Avatar key={name} name={name} subtitle={index === 0 ? "会议负责人" : "参会人"} />)}<Avatar name="AI" subtitle={meeting.agent_session_state === "paused" ? "等待本人确认" : "ADS 智能体在线"} ai /></div>
    <nav className="meeting-tabs">{tabItems.map(([id, label, count]) => <button className={tab === id ? "active" : ""} key={id} onClick={() => openTab(id)}>{label}{Boolean(count) && <b>{count}</b>}</button>)}</nav>
    <div className="meeting-stage"><main className="meeting-surface">{tab === "overview" && <MeetingOverview meeting={meeting} ads={props.ads} onTab={openTab} />}{tab === "brief" && <MeetingBrief meeting={meeting} ads={props.ads} busy={props.busy} onPrepare={props.onPrepare} onEditAgenda={props.onEditAgenda} onAgentControl={props.onAgentControl} />}{tab === "live" && <LiveMeeting meeting={meeting} transcript={props.transcript} setTranscript={props.setTranscript} busy={props.busy} speechHealth={props.speechHealth} speechJobs={props.speechJobs} selectedJob={props.selectedJob} selectJob={props.selectJob} recordingActive={props.recordingActive} onRecordingChange={props.onRecordingChange} onAnalyze={props.onAnalyze} onUploadAudio={props.onUploadAudio} onCancelSpeech={props.onCancelSpeech} onRetrySpeech={props.onRetrySpeech} onDeleteSpeech={props.onDeleteSpeech} onSaveSegment={props.onSaveSegment} onSaveFullTranscript={props.onSaveFullTranscript} onConfirmSpeech={props.onConfirmSpeech} onMicrophone={props.onMicrophone} onOpenSource={props.onOpenSource} />}{tab === "results" && <section className="meeting-view"><ViewHeading eyebrow="会后闭环" title="会议成果" text="逐项确认并写回 ADS 工作区，失败项可以单独重试。" />{meeting.analysis ? <Results meeting={meeting} ads={props.ads} completeActionItem={props.onCompleteActionItem} writeback={props.onWriteback} writebackItem={props.onWritebackItem} busy={props.busy} /> : <Empty text="会议分析完成后，这里会集中显示纪要、决策和行动项。" />}</section>}{tab === "audit" && <MeetingAudit meeting={meeting} speechJobs={props.speechJobs} onOpenSource={props.onOpenSource} />}</main></div>
  </section>;
}

function ViewHeading(props: { eyebrow: string; title: string; text: string; action?: React.ReactNode }) { return <header className="view-heading"><div><span>{props.eyebrow}</span><h2>{props.title}</h2><p>{props.text}</p></div>{props.action}</header>; }

function MeetingOverview(props: { meeting: Meeting; ads: AdsContext | null; onTab: (tab: MeetingTab) => void }) {
  const analysis = props.meeting.analysis;
  const pending = props.meeting.escalation_requests.filter((item) => item.status === "pending");
  return <section className="meeting-view"><ViewHeading eyebrow="会议概览" title="当前进展" text="分别查看会议进程、成果写回和代理状态。" /><div className="overview-band"><article><span>会议进程</span><strong>{meetingLifecycleText(props.meeting.meeting_status)}</strong></article><article><span>成果/写回</span><strong>{meetingOutcomeText(props.meeting.status)}</strong></article><article><span>代理状态</span><strong>{agentStateText(props.meeting.agent_session_state)}</strong></article><article><span>行动项</span><strong>{analysis?.action_items.length ?? 0}</strong></article></div><div className="overview-columns"><section><h3>会议目标</h3><p className="meeting-objective">{props.meeting.objective || "尚未填写会议目标。"}</p><h3>关联 ADS 目标</h3>{props.ads?.objectives.slice(0, 2).map((item) => <article className="linked-objective" key={item.id}><div><strong>{item.title}</strong><span>{item.metric}</span></div><b>{item.progress}%</b></article>)}</section><section><div className="section-bar"><h3>需要你处理</h3>{pending.length > 0 && <button onClick={() => props.onTab("live")}>返回会议现场 <ChevronRight size={15} /></button>}</div>{pending.map((item) => <article className="overview-alert" key={item.id}><AlertTriangle size={18} /><div><strong>{cleanText(item.question)}</strong><span>{cleanText(item.reason)}</span></div></article>)}{!pending.length && <Empty text="当前没有等待本人处理的事项。" />}<h3>最近活动</h3>{props.meeting.audit_events.slice(-3).reverse().map((item, index) => <div className="activity-line" key={index}><i /><div><strong>{item.action}</strong><span>{formatAuditTime(item.time)} · {item.actor}</span></div></div>)}</section></div></section>;
}

function MeetingBrief(props: { meeting: Meeting; ads: AdsContext | null; busy: string; onPrepare: () => void; onEditAgenda: () => void; onAgentControl: (action: "pause" | "resume") => void }) {
  const rule = props.ads?.authorization_rules[0];
  const agentAction = props.meeting.participation_mode !== "delegate" ? undefined
    : props.meeting.agent_session_state === "delegating"
        ? <button className="secondary-button" onClick={() => props.onAgentControl("pause")} disabled={props.busy === "agent-control"}><Pause size={16} />暂停智能体</button>
        : props.meeting.agent_session_state === "paused"
          ? <button className="primary-button" onClick={() => props.onAgentControl("resume")} disabled={props.busy === "agent-control"}><Play size={16} />继续智能体</button>
          : undefined;
  const action = <div className="heading-actions">
    {props.meeting.agenda.length > 0 && <button className="secondary-button" onClick={props.onEditAgenda}>编辑建议议程</button>}
    <button className={props.meeting.pre_meeting_brief ? "secondary-button" : "primary-button"} onClick={props.onPrepare} disabled={props.busy === "prepare"}><ClipboardCheck size={16} />{props.busy === "prepare" ? "正在生成" : props.meeting.pre_meeting_brief ? "重新生成" : "生成会前简报"}</button>
    {agentAction}
  </div>;
  return <section className="meeting-view"><ViewHeading eyebrow="会前准备" title="简报与代理边界" text="确认会议目标、业务依据和本场可自主处理的范围。" action={action} />{props.meeting.pre_meeting_brief && <p className="brief prominent">{cleanText(props.meeting.pre_meeting_brief)}</p>}<div className="brief-layout"><section><div className="section-bar"><h3>建议议程</h3>{props.meeting.agenda_edited && <span className="manual-badge">已人工修订</span>}</div><div className="agenda-list">{props.meeting.agenda.map((item, index) => <article key={`${index}-${item.topic}`}><b>{String(index + 1).padStart(2, "0")}</b><div><strong>{cleanText(item.topic)}{item.duration_minutes && <small>{item.duration_minutes} 分钟</small>}</strong><p>{cleanText(item.context)}</p><span>{cleanText(item.suggested_question)}</span></div></article>)}</div></section><aside className="authorization-sheet"><ShieldCheck size={21} /><span>本场授权</span><strong>{rule?.scope ?? "尚未配置代理授权"}</strong><h4>必须升级本人</h4><ul>{rule?.escalation_triggers.map((item) => <li key={item}>{item}</li>) ?? <li>任何超出既定范围的决定</li>}</ul></aside></div></section>;
}

function LiveMeeting(props: { meeting: Meeting; transcript: string; setTranscript: (value: string) => void; busy: string; speechHealth: SpeechHealth | null; speechJobs: SpeechJob[]; selectedJob: SpeechJob | null; selectJob: (id: string) => void; recordingActive: boolean; onRecordingChange: (active: boolean) => void; onAnalyze: () => void; onUploadAudio: (file: File, sourceType: "upload" | "microphone", options: DiarizationOptions) => void; onCancelSpeech: (jobId: string) => void; onRetrySpeech: (jobId: string) => void; onDeleteSpeech: (jobId: string) => void; onSaveSegment: (segment: TranscriptSegment, value: Partial<TranscriptSegment>) => void; onSaveFullTranscript: (value: string) => void; onConfirmSpeech: () => void; onMicrophone: (action: "acquire" | "release") => Promise<boolean>; onOpenSource: (id: string) => void }) {
  const [inputMode, setInputMode] = React.useState<"text" | "audio">("text");
  const turns = props.meeting.analysis?.transcript_turns ?? [];
  const pending = props.meeting.escalation_requests.filter((item) => item.status === "pending").length;
  const meetingActive = props.meeting.meeting_status === "in_progress";
  const meetingEnded = props.meeting.meeting_status === "ended" || props.meeting.meeting_status === "closed";
  const workflowReady = props.meeting.status === "prepared" || props.meeting.status === "awaiting_confirmation" || props.meeting.status === "confirmed";
  const canAnalyze = meetingActive && workflowReady && (props.meeting.participation_mode === "self" || props.meeting.agent_session_state === "delegating");
  const meetingContinues = pending > 0 && meetingActive;
  const waitingForDelegate = meetingActive && props.meeting.participation_mode === "delegate" && props.meeting.agent_session_state === "preparing";
  const heading = !meetingActive ? meetingEnded ? "会议已结束" : "会议尚未开始" : meetingContinues ? "会议继续进行，授权事项待确认" : waitingForDelegate ? "智能体尚未开始代理" : props.meeting.agent_session_state === "paused" ? "代理已暂停，等待本人确认" : "智能体正在跟进会议";
  const liveStatus = props.busy === "analyze" ? "正在分析最新发言" : !meetingActive ? meetingEnded ? "会议已结束，现场输入已关闭" : "等待开始会议" : meetingContinues ? "会议进行中，等待本人处理授权事项" : waitingForDelegate ? "智能体尚未开始代理" : props.meeting.agent_session_state === "paused" ? "智能体已暂停" : "监听新发言";
  const composerHint = canAnalyze ? (meetingContinues ? "会议可以继续记录；只有超出授权的事项会暂停执行。" : "分析后将更新会议时间线、授权判断和行动项。") : waitingForDelegate ? "请先重新开始智能体。" : props.meeting.agent_session_state === "paused" ? "智能体已暂停，请先继续智能体。" : "会议准备完成后才能提交发言。";
  const latestReturn = [...props.meeting.audit_events].reverse().find((event) => event.action === "回复会议");
  function selectInputMode(next: "text" | "audio") {
    if (inputMode === "audio" && next === "text" && props.recordingActive && !window.confirm("当前正在录音。切换到文字输入将取消并丢弃本次录音，是否继续？")) return;
    setInputMode(next);
  }
  return <section className="meeting-view live-view"><ViewHeading eyebrow="会议现场" title={heading} text="每条发言都会经过 ADS 检索和授权判断，结果记录在右侧控制面板。" /><div className="live-status-line"><span className="live-pulse" /><strong>{liveStatus}</strong><span>{turns.length} 条已处理发言</span></div>{latestReturn && <article className="meeting-return"><Check size={18} /><div><strong>本人决定已返回会议</strong><span>{cleanText(latestReturn.detail)}</span><small>{formatAuditTime(latestReturn.time)}</small></div></article>}<div className="trace-feed">{turns.map((turn, index) => <article className="trace-turn" key={`${turn.speaker}-${index}`}><div className="trace-avatar">{turn.speaker.slice(0, 1)}</div><div className="trace-content"><header><strong>{cleanText(turn.speaker)}</strong><span>发言 {index + 1}</span></header><p>{cleanText(turn.content)}</p><footer><span className={turn.agent_action.includes("升级") ? "trace-action warn" : "trace-action"}><Bot size={14} />{cleanText(turn.agent_action)}</span>{turn.linked_object_ids.slice(0, 3).map((id) => <button className="source-id" key={id} onClick={() => props.onOpenSource(id)}>{id}</button>)}</footer></div></article>)}{!turns.length && <div className="waiting-state"><div className="listening-rings"><Bot size={24} /></div><strong>等待会议发言</strong><p>输入文字或上传音频后，智能体会在这里展示逐条判断过程。</p></div>}</div>{meetingActive ? <section className="meeting-composer"><div className="input-segments"><button className={inputMode === "text" ? "active" : ""} onClick={() => selectInputMode("text")}><ListChecks size={15} />文字输入</button><button className={inputMode === "audio" ? "active" : ""} onClick={() => selectInputMode("audio")}><Mic size={15} />录音与音频</button></div>{inputMode === "text" ? <><label>新增会议发言<textarea value={props.transcript} placeholder="按“发言人：内容”输入，可一次提交多条发言。" onChange={(event) => props.setTranscript(event.target.value)} /></label><div className="composer-footer"><span>{composerHint}</span><button className="primary-button" onClick={props.onAnalyze} disabled={props.busy === "analyze" || !canAnalyze}><Bot size={17} />{props.busy === "analyze" ? "正在分析" : "提交给智能体"}</button></div></> : <AudioInputPanel health={props.speechHealth} busy={props.busy} jobs={props.speechJobs} selectedJob={props.selectedJob} selectJob={props.selectJob} uploadAudio={props.onUploadAudio} cancelJob={props.onCancelSpeech} retryJob={props.onRetrySpeech} deleteJob={props.onDeleteSpeech} saveSegment={props.onSaveSegment} saveFullTranscript={props.onSaveFullTranscript} confirmSpeech={props.onConfirmSpeech} onMicrophone={props.onMicrophone} onRecordingChange={props.onRecordingChange} />}</section> : <section className="meeting-input-closed" role="status"><Square size={18} /><div><strong>{meetingEnded ? "会议现场已关闭" : "会议尚未开始"}</strong><span>{meetingEnded ? "如需继续记录，请先重新打开会议。" : "请先点击页面上方的“开始会议”。"}</span></div></section>}</section>;
}

function MeetingAudit(props: { meeting: Meeting; speechJobs: SpeechJob[]; onOpenSource: (id: string) => void }) {
  const analysis = props.meeting.analysis;
  const ids = [...new Set([
    ...(analysis?.transcript_turns.flatMap((item) => item.linked_object_ids) ?? []),
    ...props.meeting.escalation_requests.flatMap((item) => item.evidence_object_ids),
    ...props.meeting.sent_agent_replies.flatMap((item) => item.evidence_object_ids),
  ])];
  const sources = (objectIds: string[]) => objectIds.map((id) => <button className="source-id" key={id} onClick={() => props.onOpenSource(id)}>{id}</button>);
  return <section className="meeting-view"><ViewHeading eyebrow="审计与来源" title="可追溯执行回放" text="按链路查看原始音频或文字、智能体判断、授权依据、本人决定和 ADS 写回。" /><div className="source-chain refined"><span>原始输入</span><ChevronRight size={15} /><span>转写与修订</span><ChevronRight size={15} /><span>智能体判断</span><ChevronRight size={15} /><span>授权/升级</span><ChevronRight size={15} /><span>本人决定</span><ChevronRight size={15} /><span>行动项</span><ChevronRight size={15} /><span>ADS 任务</span></div>{ids.length > 0 && <div className="source-object-list"><strong>可下钻 ADS 来源</strong>{sources(ids)}</div>}<div className="audit-replay-grid"><section><h3>1. 原始输入与判断</h3>{props.speechJobs.map((job) => <article key={job.id}><strong>{cleanText(job.original_name)}</strong><span>{speechStatus(job.status)} · {job.segments.length} 个时间片 · {job.revisions.length} 次修订</span><code>{job.id}</code></article>)}{analysis?.transcript_turns.map((turn, index) => <article key={`${turn.speaker}-${index}`}><strong>{turn.speaker}：{cleanText(turn.content)}</strong><span>{cleanText(turn.agent_action)}</span><footer>{sources(turn.linked_object_ids)}</footer></article>)}{!props.speechJobs.length && !analysis?.transcript_turns.length && <Empty text="尚无可回放的会议输入。" />}</section><section><h3>2. 回复、授权与本人决定</h3>{props.meeting.sent_agent_replies.map((reply) => <article key={reply.id}><strong>{reply.decision === "sent" ? "已自动回复" : "回复建议"}：{cleanText(reply.content)}</strong><span>{reply.authorization_rule_ids.length} 条授权依据</span><footer>{sources(reply.evidence_object_ids)}{reply.authorization_rule_ids.map((id) => <button className="source-id" key={id} onClick={() => props.onOpenSource(id)}>{id}</button>)}</footer></article>)}{props.meeting.escalation_requests.map((item) => <article key={item.id}><strong>升级本人：{cleanText(item.question)}</strong><span>{decisionText(item.status)} · {cleanText(item.reason)}</span>{item.user_reply && <p>本人回复：{cleanText(item.user_reply)}</p>}<footer>{sources(item.evidence_object_ids)}</footer></article>)}{!props.meeting.sent_agent_replies.length && !props.meeting.escalation_requests.length && <Empty text="本场尚无代理回复或升级事项。" />}</section><section className="wide"><h3>3. 决策、行动项与写回</h3>{analysis?.decisions.map((decision) => <article key={decision.id}><strong>{cleanText(decision.content)}</strong><span>决策 ID：{decision.id} · 依据：{cleanText(decision.evidence)}</span></article>)}{analysis?.action_items.map((item) => <article key={item.id}><strong>{cleanText(item.title)}</strong><span>行动项 {item.id} → 决策 {item.linked_decision_id} → ADS 任务 {item.writeback_task_id ?? "尚未写回"}</span><StatusBadge text={item.status} tone={item.status === "written_back" ? "green" : "orange"} /></article>)}{!analysis?.decisions.length && !analysis?.action_items.length && <Empty text="本场尚无决策和行动项。" />}</section></div><h3 className="audit-event-heading">事件时间线</h3><div className="audit-timeline">{props.meeting.audit_events.map((event, index) => <article key={index}><time>{formatAuditTime(event.time)}</time><i /><div><strong>{cleanText(event.action)}</strong><span>{event.actor}</span><p>{cleanText(event.detail)}</p></div></article>)}</div></section>;
}
function AudioInputPanel(props: { health: SpeechHealth | null; busy: string; jobs: SpeechJob[]; selectedJob: SpeechJob | null; selectJob: (id: string) => void; uploadAudio: (file: File, sourceType: "upload" | "microphone", options: DiarizationOptions) => void; cancelJob: (jobId: string) => void; retryJob: (jobId: string) => void; deleteJob: (jobId: string) => void; saveSegment: (segment: TranscriptSegment, value: Partial<TranscriptSegment>) => void; saveFullTranscript: (value: string) => void; confirmSpeech: () => void; onMicrophone: (action: "acquire" | "release") => Promise<boolean>; onRecordingChange: (active: boolean) => void }) {
  const [recorder, setRecorder] = React.useState<MediaRecorder | null>(null);
  const [recordingState, setRecordingState] = React.useState<"idle" | "recording" | "paused">("idle");
  const [elapsed, setElapsed] = React.useState(0);
  const [volume, setVolume] = React.useState(0);
  const [recordError, setRecordError] = React.useState("");
  const [permissionState, setPermissionState] = React.useState<"unknown" | "requesting" | "granted" | "denied" | "unavailable">("unknown");
  const [isDragOver, setIsDragOver] = React.useState(false);
  const [diarizationEnabled, setDiarizationEnabled] = React.useState(true);
  const [speakerCount, setSpeakerCount] = React.useState<number | null>(null);
  const chunks = React.useRef<Blob[]>([]);
  const recorderRef = React.useRef<MediaRecorder | null>(null);
  const streamRef = React.useRef<MediaStream | null>(null);
  const analyserRef = React.useRef<AnalyserNode | null>(null);
  const audioContextRef = React.useRef<AudioContext | null>(null);
  const meterFrameRef = React.useRef<number | null>(null);
  const recordingStartedAtRef = React.useRef(0);
  const accumulatedMsRef = React.useRef(0);
  const discardOnStopRef = React.useRef(false);

  React.useEffect(() => {
    if (recordingState === "idle") return;
    const timer = window.setInterval(() => {
      const runningMs = recordingState === "recording" ? Date.now() - recordingStartedAtRef.current : 0;
      setElapsed(Math.floor((accumulatedMsRef.current + runningMs) / 1000));
    }, 250);
    return () => window.clearInterval(timer);
  }, [recordingState]);
  React.useEffect(() => {
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if (recordingState === "idle") return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", beforeUnload);
    return () => window.removeEventListener("beforeunload", beforeUnload);
  }, [recordingState]);
  React.useEffect(() => () => {
    discardOnStopRef.current = true;
    const active = recorderRef.current;
    if (active && active.state !== "inactive") active.stop();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    stopMeter();
    void props.onMicrophone("release");
    props.onRecordingChange(false);
  }, []);

  function stopMeter() {
    if (meterFrameRef.current !== null) window.cancelAnimationFrame(meterFrameRef.current);
    meterFrameRef.current = null;
    analyserRef.current = null;
    const context = audioContextRef.current;
    audioContextRef.current = null;
    if (context && context.state !== "closed") void context.close();
    setVolume(0);
  }
  function startMeter(stream: MediaStream) {
    const AudioContextConstructor = window.AudioContext ?? (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AudioContextConstructor) return;
    try {
      const context = new AudioContextConstructor();
      const analyser = context.createAnalyser();
      analyser.fftSize = 256;
      context.createMediaStreamSource(stream).connect(analyser);
      const data = new Uint8Array(analyser.fftSize);
      audioContextRef.current = context;
      analyserRef.current = analyser;
      const sample = () => {
        if (!analyserRef.current) return;
        analyser.getByteTimeDomainData(data);
        let sum = 0;
        for (const sampleValue of data) {
          const normalized = (sampleValue - 128) / 128;
          sum += normalized * normalized;
        }
        const rms = Math.sqrt(sum / data.length);
        setVolume(Math.max(3, Math.min(100, Math.round(rms * 360))));
        meterFrameRef.current = window.requestAnimationFrame(sample);
      };
      sample();
    } catch {
      setRecordError("无法读取麦克风音量，但录音仍可继续。结束后会正常上传音频。");
    }
  }
  async function startRecording() {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setPermissionState("unavailable");
      setRecordError("当前浏览器不支持录音，请改用上传音频或直接输入。");
      return;
    }
    if (!await props.onMicrophone("acquire")) {
      setRecordError("麦克风正在被另一场会议使用，请结束对应录音后重试。");
      return;
    }
    setPermissionState("requesting");
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      setPermissionState("granted");
      setRecordError("");
    } catch (error) {
      const denied = error instanceof DOMException && ["NotAllowedError", "SecurityError"].includes(error.name);
      setPermissionState(denied ? "denied" : "unavailable");
      setRecordError(denied ? "麦克风权限被拒绝，请在浏览器网站设置中重新授权，或改用上传音频。" : "未检测到可用麦克风，请检查设备连接，或改用上传音频。");
      await props.onMicrophone("release");
      return;
    }
    const preferred = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"].find((type) => MediaRecorder.isTypeSupported(type));
    let mediaRecorder: MediaRecorder;
    try {
      mediaRecorder = new MediaRecorder(stream, preferred ? { mimeType: preferred } : undefined);
    } catch {
      stream.getTracks().forEach((track) => track.stop());
      await props.onMicrophone("release");
      setPermissionState("unavailable");
      setRecordError("当前浏览器无法创建录音任务，请改用上传音频文件。");
      return;
    }
    chunks.current = [];
    discardOnStopRef.current = false;
    streamRef.current = stream;
    mediaRecorder.ondataavailable = (event) => { if (event.data.size > 0) chunks.current.push(event.data); };
    mediaRecorder.onerror = () => setRecordError("录音设备发生中断，请检查麦克风后重试。");
    mediaRecorder.onstop = () => {
      const blob = new Blob(chunks.current, { type: mediaRecorder.mimeType || "audio/webm" });
      stream.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      stopMeter();
      void props.onMicrophone("release");
      props.onRecordingChange(false);
      if (discardOnStopRef.current) return;
      if (!blob.size) { setRecordError("没有检测到有效录音，请检查麦克风音量后重试。"); return; }
      props.uploadAudio(new File([blob], `meeting-recording-${Date.now()}.webm`, { type: blob.type }), "microphone", { diarizationEnabled, speakerCount });
    };
    mediaRecorder.start(250);
    recorderRef.current = mediaRecorder;
    setRecorder(mediaRecorder);
    accumulatedMsRef.current = 0;
    recordingStartedAtRef.current = Date.now();
    setElapsed(0);
    setVolume(3);
    setRecordingState("recording");
    props.onRecordingChange(true);
    startMeter(stream);
  }
  function togglePause() {
    const active = recorderRef.current;
    if (!active) return;
    if (recordingState === "recording") {
      active.pause();
      accumulatedMsRef.current += Date.now() - recordingStartedAtRef.current;
      setRecordingState("paused");
      setVolume(0);
    } else {
      active.resume();
      recordingStartedAtRef.current = Date.now();
      setRecordingState("recording");
    }
  }
  function stopRecording() {
    const active = recorderRef.current;
    if (!active) return;
    if (recordingState === "recording") accumulatedMsRef.current += Date.now() - recordingStartedAtRef.current;
    setElapsed(Math.floor(accumulatedMsRef.current / 1000));
    active.stop();
    recorderRef.current = null;
    setRecorder(null);
    setRecordingState("idle");
  }
  function cancelRecording() {
    const active = recorderRef.current;
    if (!active) return;
    discardOnStopRef.current = true;
    active.stop();
    recorderRef.current = null;
    setRecorder(null);
    setRecordingState("idle");
    setElapsed(0);
    props.onRecordingChange(false);
    setRecordError("");
  }
  function handleFiles(files: FileList | File[]) {
    const file = files[0];
    if (!file) return;
    const supported = [".mp3", ".wav", ".m4a", ".webm", ".mp4", ".flac"];
    const extension = `.${file.name.split(".").pop()?.toLowerCase() ?? ""}`;
    if (!supported.includes(extension)) { setRecordError("暂不支持该格式，请使用 MP3、WAV、M4A 或 WebM。"); return; }
    if (!file.size) { setRecordError("音频文件为空，请重新选择文件。"); return; }
    if (file.size > 500 * 1024 * 1024) { setRecordError("音频超过 500 MB，请压缩或拆分后重试。"); return; }
    setRecordError("");
    props.uploadAudio(file, "upload", { diarizationEnabled, speakerCount });
  }
  const activeJobs = props.jobs.filter((job) => isSpeechJobActive(job.status)).length;
  const isUploading = props.busy === "speech";
  const uploadDisabled = recordingState !== "idle" || isUploading;
  function jobBusy(jobId: string) { return props.busy === `speech-cancel-${jobId}` || props.busy === `speech-retry-${jobId}` || props.busy === `speech-delete-${jobId}`; }
  const permissionLabel = { unknown: "尚未请求", requesting: "请求中", granted: "已授权", denied: "权限被拒绝", unavailable: "设备不可用" }[permissionState];
  return <div className="audio-panel">
    <div className={props.health?.status === "ready" ? "speech-runtime ready" : "speech-runtime degraded"}>
      <div className="runtime-title"><span>{props.health?.status === "ready" ? "本地转写可用" : "本地转写组件未就绪"}</span><small>{props.health?.message ?? "正在检查语音组件"}</small></div>
      <FileAudio size={19} />
    </div>
    <div className="input-modes">
      <button type="button" className={recordingState !== "idle" ? "record-button active" : "record-button"} onClick={recordingState === "idle" ? startRecording : stopRecording}>{recordingState === "idle" ? <Mic size={17} /> : <Square size={17} />}{recordingState === "idle" ? "开始录音" : `结束并转写 ${formatTime(elapsed)}`}</button>
      {recordingState !== "idle" && <button type="button" className="secondary-button" onClick={togglePause}>{recordingState === "recording" ? <Pause size={16} /> : <Play size={16} />}{recordingState === "recording" ? "暂停" : "继续"}</button>}
      {recordingState !== "idle" && <button type="button" className="danger-button" onClick={cancelRecording}><X size={16} />取消录音</button>}
      <div className={`audio-dropzone ${isDragOver ? "drag-over" : ""} ${uploadDisabled ? "disabled" : ""}`} onDragEnter={(event) => { event.preventDefault(); if (!uploadDisabled) setIsDragOver(true); }} onDragOver={(event) => event.preventDefault()} onDragLeave={() => setIsDragOver(false)} onDrop={(event) => { event.preventDefault(); setIsDragOver(false); if (!uploadDisabled) handleFiles(event.dataTransfer.files); }}>
        <Upload size={16} /><span>拖放音频到这里，或</span><label className="file-button">选择文件<input type="file" accept=".mp3,.wav,.m4a,.webm,.mp4,.flac,audio/*" disabled={uploadDisabled} onChange={(event) => { handleFiles(event.target.files ?? []); event.currentTarget.value = ""; }} /></label>
      </div>
      <span className="audio-format-hint">MP3、WAV、M4A、WebM，单文件不超过 500 MB</span>
    </div>
    <div className="diarization-options">
      <label className="check-control"><input type="checkbox" checked={diarizationEnabled} disabled={recordingState !== "idle" || isUploading} onChange={(event) => setDiarizationEnabled(event.target.checked)} />区分不同发言人</label>
      <label><span>说话人数</span><select value={speakerCount ?? ""} disabled={!diarizationEnabled || recordingState !== "idle" || isUploading} onChange={(event) => setSpeakerCount(event.target.value ? Number(event.target.value) : null)}><option value="">自动判断</option>{Array.from({ length: 9 }, (_, index) => index + 2).map((count) => <option key={count} value={count}>{count} 人</option>)}</select></label>
      <small>全程本地处理，仅生成“发言人 1/2/3”等匿名标签。</small>
    </div>
    <div className="mic-status-row"><span className={`mic-status ${permissionState}`}><Mic size={13} />麦克风：{permissionLabel}</span><span>{recordingState === "paused" ? "录音已暂停" : recordingState === "recording" ? "正在采集音频" : "开始录音后显示实时音量"}</span></div>
    <div className="recorder-meter" aria-label={recordingState === "idle" ? "录音未开始" : recordingState === "paused" ? "录音已暂停" : "实时音量反馈"}><span style={{ width: `${recordingState === "idle" ? 0 : Math.max(3, volume)}%` }} /></div>
    {recordingState !== "idle" && <p className="recording-note"><span className="live-pulse" />{recordingState === "paused" ? "录音已暂停" : "正在采集麦克风音频"} · {formatTime(elapsed)}</p>}
    {recordError && <p className="inline-error">{recordError}</p>}
    {isUploading && <p className="hint">正在上传音频，任务会在后台继续处理。</p>}
    <section className="speech-queue">
      <header className="queue-heading"><div><strong>音频任务</strong><span>{activeJobs ? `${activeJobs} 个任务处理中` : props.jobs.length ? "没有正在处理的任务" : "上传或录音后，任务会显示在这里"}</span></div>{props.jobs.length > 0 && <small>{props.jobs.length} 个</small>}</header>
      {props.jobs.length ? <div className="job-list">{props.jobs.map((job) => <SpeechJobRow key={job.id} job={job} selected={props.selectedJob?.id === job.id} busy={jobBusy(job.id)} onSelect={() => props.selectJob(job.id)} onCancel={() => props.cancelJob(job.id)} onRetry={() => props.retryJob(job.id)} onDelete={() => props.deleteJob(job.id)} />)}</div> : <div className="queue-empty"><FileAudio size={20} /><span>还没有音频任务</span><small>可上传会议录音，或用浏览器开始一段录音。</small></div>}
    </section>
    {props.selectedJob && <TranscriptReview job={props.selectedJob} saveSegment={props.saveSegment} saveFullTranscript={props.saveFullTranscript} confirmSpeech={props.confirmSpeech} />}
  </div>;
}
function SpeechJobRow(props: { job: SpeechJob; selected: boolean; busy: boolean; onSelect: () => void; onCancel: () => void; onRetry: () => void; onDelete: () => void }) {
  const { job } = props;
  const active = isSpeechJobActive(job.status);
  const statusClass = job.status === "failed" ? "orange" : job.status === "confirmed" ? "green" : job.status === "awaiting_review" ? "blue" : "neutral";
  return <article className={`speech-job ${props.selected ? "selected" : ""}`}>
    <button type="button" className="job-select" onClick={props.onSelect} aria-pressed={props.selected}>
      <span className="job-file-icon"><FileAudio size={16} /></span>
      <span className="job-copy"><strong title={job.original_name}>{cleanText(job.original_name)}</strong><small>{job.source_type === "microphone" ? "浏览器录音" : "上传文件"} · {job.model_name === "stub-provider" ? "本地文本" : `${job.device} · ${job.compute_type}`} · {audioMeta(job)}</small></span>
      <span className={`job-status ${statusClass}`}>{speechStatus(job.status)}</span>
    </button>
    <div className="job-progress"><div className="progress"><span style={{ width: `${Math.max(0, Math.min(100, job.progress))}%` }} /></div><span>{active ? `${job.progress}% · ${speechProgressLabel(job.status)}` : job.status === "failed" ? cleanText(job.error_message ?? "需要恢复") : job.status === "cancelled" ? "已取消，可重新尝试" : job.status === "confirmed" ? "已进入会议分析" : `转写完成，等待审核${processingMeta(job)}`}</span></div>
    <div className="job-actions">
      {active && <button type="button" className="icon-button compact" onClick={props.onCancel} disabled={props.busy} title="取消转写" aria-label={`取消 ${job.original_name}`}><X size={15} /></button>}
      {(job.status === "failed" || job.status === "cancelled") && <button type="button" className="icon-button compact" onClick={props.onRetry} disabled={props.busy} title="重新转写" aria-label={`重新转写 ${job.original_name}`}><RefreshCw size={15} className={props.busy ? "spin" : ""} /></button>}
      {job.status !== "confirmed" && !active && <button type="button" className="icon-button compact danger-icon" onClick={props.onDelete} disabled={props.busy} title="删除任务" aria-label={`删除 ${job.original_name}`}><Trash2 size={15} /></button>}
    </div>
  </article>;
}
function TranscriptReview(props: { job: SpeechJob; saveSegment: (segment: TranscriptSegment, value: Partial<TranscriptSegment>) => void; saveFullTranscript: (value: string) => void; confirmSpeech: () => void }) {
  const [fullText, setFullText] = React.useState(props.job.full_text);
  React.useEffect(() => setFullText(props.job.full_text), [props.job.id, props.job.full_text]);
  if (isSpeechJobActive(props.job.status)) return <div className="speech-progress-card"><div className="speech-progress-head"><div><LoaderCircle size={17} className="spin" /><strong>{speechProgressLabel(props.job.status)}</strong></div><b>{props.job.progress}%</b></div><div className="progress large"><span style={{ width: `${Math.max(0, Math.min(100, props.job.progress))}%` }} /></div><p>音频正在后台处理，可以继续查看会议内容。任务完成后会在这里进入审核。</p></div>;
  if (props.job.status === "failed") return <div className="recover-box"><MicOff size={17} /><strong>{cleanText(props.job.error_message ?? "转写失败")}</strong><span>请重新转写或上传其他文件。原始音频仍保留在本地，直到删除任务。</span></div>;
  if (props.job.status === "cancelled") return <div className="recover-box cancelled"><X size={17} /><strong>转写已取消</strong><span>原始音频已保留，可以在任务列表中重新转写或删除。</span></div>;
  if (!props.job.segments.length) return <div className="queue-empty compact-empty"><Check size={18} /><span>转写结果暂时为空</span><small>请重新转写或改用文字输入。</small></div>;
  async function saveFullText() {
    if (fullText.trim() && fullText.trim() !== props.job.full_text.trim()) await props.saveFullTranscript(fullText.trim());
  }
  return <div className="review-box"><div className="review-head"><strong>转写审核</strong><span>{speechModelLabel(props.job.model_name)} · {props.job.device}/{props.job.compute_type}{processingMeta(props.job)}</span></div>{props.job.diarization_warning && <p className="diarization-warning"><AlertTriangle size={15} />{cleanText(props.job.diarization_warning)}</p>}{props.job.diarization_enabled && !props.job.diarization_warning && <p className="diarization-summary">本地匿名分离完成 · 检测到 {props.job.detected_speaker_count ?? "未知"} 位发言人</p>}<label className="full-transcript"><span>完整转写</span><textarea value={fullText} onChange={(event) => setFullText(event.target.value)} onBlur={() => void saveFullText()} /><small>可直接修改总稿；片段修改会重新拼接完整转写。</small></label><div className="segment-list">{props.job.segments.map((segment) => <TranscriptSegmentEditor key={segment.id} segment={segment} saveSegment={props.saveSegment} />)}</div><button className="primary-button" onClick={props.confirmSpeech} disabled={props.job.status !== "awaiting_review" || !fullText.trim()}><Check size={17} />确认并进入智能分析</button></div>;
}
function TranscriptSegmentEditor(props: { segment: TranscriptSegment; saveSegment: (segment: TranscriptSegment, value: Partial<TranscriptSegment>) => void }) {
  const [speaker, setSpeaker] = React.useState(props.segment.speaker_label);
  const [text, setText] = React.useState(props.segment.revised_text);
  React.useEffect(() => { setSpeaker(props.segment.speaker_label); setText(props.segment.revised_text); }, [props.segment.id, props.segment.speaker_label, props.segment.revised_text]);
  function commit() {
    if (speaker.trim() && text.trim() && (speaker.trim() !== props.segment.speaker_label || text.trim() !== props.segment.revised_text)) props.saveSegment(props.segment, { speaker_label: speaker.trim(), revised_text: text.trim() });
  }
  return <article className={props.segment.speaker_ambiguous ? "segment-row ambiguous" : "segment-row"}><span>{formatTime(props.segment.start_seconds)}-{formatTime(props.segment.end_seconds)}{props.segment.speaker_ambiguous && <small>重叠发言，建议人工核对</small>}</span><input aria-label="发言人" value={speaker} onChange={(event) => setSpeaker(event.target.value)} onBlur={commit} /><textarea aria-label="转写片段" value={text} onChange={(event) => setText(event.target.value)} onBlur={commit} /></article>;
}
function AgentPanel(props: { meeting: Meeting; ads: AdsContext | null; models: ModelConfig[]; aiRuntime: AiRuntimeStatus | null; busy: string; onSelectModel: (id: string) => void; onAsk: (question: string) => Promise<{ answer: string; evidence_object_ids: string[]; mode: "live" | "local_rules" } | null>; onOpenSource: (id: string) => void }) {
  const pending = props.meeting.escalation_requests.filter((item) => item.status === "pending");
  const replies = props.meeting.analysis?.agent_replies ?? [];
  const [question, setQuestion] = React.useState("");
  const [answer, setAnswer] = React.useState<{ answer: string; evidence_object_ids: string[]; mode: "live" | "local_rules" } | null>(null);
  const currentModel = props.models.find((item) => item.provider_id === props.meeting.model_provider_id) ?? props.models[0];
  const runtimeIsMock = props.aiRuntime?.mode === "mock" || currentModel?.adapter_type === "mock" || !currentModel?.configured;
  const playedReplyRef = React.useRef("");
  const stages = props.busy === "analyze" ? ["倾听发言", "检索 ADS", "判断授权", "生成答复"] : props.meeting.agent_session_state === "paused" ? ["已理解发言", "已检索 ADS", "发现超权事项", "等待本人确认"] : props.meeting.analysis ? ["已理解发言", "已检索 ADS", "已生成答复", "持续记录成果"] : ["监听会议", "等待新发言", "准备检索 ADS", "检查授权边界"];
  async function askAgent() {
    const value = question.trim(); if (!value) return;
    const next = await props.onAsk(value);
    if (next) { setAnswer(next); setQuestion(""); if (localStorage.getItem("ads.tts.auto") !== "false") speak(next.answer); }
  }
  function speak(value: string) { if (!("speechSynthesis" in window) || !value) return; window.speechSynthesis.cancel(); const utterance = new SpeechSynthesisUtterance(value); utterance.lang = "zh-CN"; window.speechSynthesis.speak(utterance); }
  const latestReply = replies[replies.length - 1];
  React.useEffect(() => {
    if (!latestReply || latestReply.decision === "escalate" || playedReplyRef.current === latestReply.reply || localStorage.getItem("ads.tts.auto") === "false") return;
    playedReplyRef.current = latestReply.reply; speak(cleanText(latestReply.reply));
  }, [latestReply?.reply]);
  React.useEffect(() => () => { if ("speechSynthesis" in window) window.speechSynthesis.cancel(); }, [props.meeting.id]);
  return <aside className="agent-panel control-panel"><div className="agent-head"><div className="agent-symbol"><Bot size={18} /></div><div><strong>ADS 智能体</strong><span>{props.meeting.participation_mode === "delegate" ? "代表你参与当前会议" : "辅助整理当前会议"}</span></div><i className={props.meeting.agent_session_state === "paused" ? "agent-dot warn" : "agent-dot"} /></div><label className="agent-model"><span>当前模型</span><select value={currentModel?.provider_id ?? ""} onChange={(event) => props.onSelectModel(event.target.value)} disabled={props.busy === "meeting-model"}>{props.models.filter((item) => item.enabled).map((model) => <option key={model.provider_id} value={model.provider_id}>{model.provider_name} · {model.model}</option>)}</select><small className={runtimeIsMock ? "runtime-note mock" : "runtime-note"}>{runtimeIsMock ? "本地规则模式：当前分析不调用在线大模型" : props.aiRuntime?.message ?? "当前分析使用在线模型"}</small></label><section className="agent-trace"><div className="agent-section-title"><h3>判断轨迹</h3><span>{props.busy === "analyze" ? "处理中" : "实时"}</span></div><div className="agent-stages">{stages.map((stage, index) => <div className={index === stages.length - 1 ? "active" : "done"} key={stage}><i /><span>{stage}</span>{index < stages.length - 1 && <b />}</div>)}</div></section>{pending.length > 0 ? <section className="agent-attention"><div className="agent-section-title"><h3>等待本人</h3><span>{pending.length}</span></div>{pending.map((item) => <article key={item.id}><AlertTriangle size={17} /><div><strong>{cleanText(item.question)}</strong><p>{cleanText(item.reason)}</p><small>{cleanText(item.ai_recommendation)}</small></div></article>)}</section> : <section className="agent-clear"><Check size={17} /><div><strong>授权边界正常</strong><span>当前没有需要本人处理的事项</span></div></section>}<section className="agent-context"><div className="agent-section-title"><h3>当前依据</h3></div><dl><div><dt>业务目标</dt><dd>{props.ads?.objectives[0]?.title ?? "未关联"}</dd></div><div><dt>授权规则</dt><dd>{props.ads?.authorization_rules.length ?? 0} 条</dd></div><div><dt>进行中任务</dt><dd>{props.ads?.tasks.filter((item) => item.status !== "已完成").length ?? 0} 条</dd></div></dl></section>{latestReply && <section className={latestReply.decision === "escalate" ? "latest-reply warn" : "latest-reply"}><div className="agent-section-title"><h3>{latestReply.decision === "escalate" ? "建议升级本人" : "最近一次回复"}</h3><button className="speak-inline" onClick={() => speak(cleanText(latestReply.reply))} title="播放智能体回复"><Volume2 size={15} /></button></div><p>{cleanText(latestReply.reply)}</p><small>{cleanText(latestReply.reason)}</small></section>}{answer && <section className="agent-answer refined"><div><Bot size={16} /><strong>ADS 回答 · {answer.mode === "live" ? "在线模型" : "本地规则"}</strong><button className="speak-inline" onClick={() => speak(answer.answer)} title="播放回答"><Volume2 size={15} /></button></div><p>{cleanText(answer.answer)}</p>{answer.evidence_object_ids.length > 0 && <footer className="answer-evidence">依据：{answer.evidence_object_ids.map((id) => <button className="source-id" key={id} onClick={() => props.onOpenSource(id)}>{id}</button>)}</footer>}</section>}<div className="ask-box agent-ask"><input aria-label="询问 ADS 智能体" placeholder="询问当前会议或 ADS…" value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void askAgent(); }} /><button onClick={() => void askAgent()} disabled={props.busy === "agent-ask"} title="发送问题"><Send size={17} /></button></div></aside>;
}
type DecisionFilter = "pending" | "resolved" | "all";
function DecisionCenter(props: { meetings: Meeting[]; workspaces: AdsWorkspace[]; replyDraft: string; setReplyDraft: (value: string) => void; onOpenMeeting: (id: string) => void; onOpenSource: (workspaceId: string | null | undefined, objectId: string) => void; onResolve: (meetingId: string, id: string, action: "approve" | "edit" | "reject" | "defer") => void; busy: string }) {
  const [filter, setFilter] = React.useState<DecisionFilter>("pending");
  const [selectedId, setSelectedId] = React.useState("");
  const cards = sortDecisionQueue(props.meetings
    .flatMap((meeting) => meeting.escalation_requests.map((request) => ({ ...request, meeting, request }))));
  const unresolved = (status: EscalationRequest["status"]) => status === "pending" || status === "deferred";
  const pendingCount = cards.filter((item) => unresolved(item.request.status)).length;
  const resolvedCount = cards.length - pendingCount;
  const affectedMeetings = new Set(cards.filter((item) => unresolved(item.request.status)).map((item) => item.meeting.id)).size;
  const filtered = cards.filter((item) => filter === "all" || (filter === "pending" ? unresolved(item.request.status) : !unresolved(item.request.status)));
  const selected = filtered.find((item) => item.request.id === selectedId) ?? filtered[0] ?? null;
  React.useEffect(() => {
    if (selected && selected.request.id !== selectedId) setSelectedId(selected.request.id);
  }, [selected?.request.id, selectedId]);
  React.useEffect(() => {
    if (selected) props.setReplyDraft(selected.request.user_reply || selected.request.ai_recommendation);
  }, [selected?.request.id]);
  const workspace = selected ? props.workspaces.find((item) => item.id === selected.meeting.workspace_id) : null;
  const objective = workspace?.objectives.find((item) => selected?.request.evidence_object_ids.includes(item.id));
  const rule = workspace?.authorization_rules.find((item) => selected?.request.evidence_object_ids.includes(item.id));
  const knownEvidence = new Set([objective?.id, rule?.id].filter(Boolean));
  const missingEvidence = selected?.request.evidence_object_ids.filter((id) => !knownEvidence.has(id)) ?? [];

  return <section className="decision-workspace">
    <header className="decision-header">
      <div><span className="kicker">需要你判断的事项</span><h1>决策中心</h1><p>集中处理超出智能体授权边界的问题，回复会返回对应会议。</p></div>
      <div className="decision-summary"><div><strong>{pendingCount}</strong><span>待处理</span></div><div><strong>{affectedMeetings}</strong><span>受影响会议</span></div><div><strong>{resolvedCount}</strong><span>已处理</span></div></div>
    </header>
    <div className="decision-body">
      <aside className="decision-queue">
        <div className="decision-tabs">{(["pending", "resolved", "all"] as DecisionFilter[]).map((item) => <button className={filter === item ? "active" : ""} key={item} onClick={() => setFilter(item)}>{item === "pending" ? "待处理" : item === "resolved" ? "已处理" : "全部"}<span>{item === "pending" ? pendingCount : item === "resolved" ? resolvedCount : cards.length}</span></button>)}</div>
        <div className="decision-queue-list">{filtered.map(({ meeting, request }) => <button className={selected?.request.id === request.id ? "decision-queue-row active" : "decision-queue-row"} key={request.id} onClick={() => setSelectedId(request.id)}><div><span>{cleanText(meeting.title)}</span><StatusBadge text={decisionText(request.status)} tone={request.status === "pending" ? "orange" : "green"} /></div><strong>{cleanText(request.question)}</strong><small>{formatAuditTime(request.created_at)} · {request.status === "pending" ? formatDecisionAge(request.created_at) : "已完成处理"}</small></button>)}</div>
        {!filtered.length && <div className="decision-empty"><Check size={24} /><strong>{filter === "pending" ? "待处理事项已清空" : "当前分类暂无记录"}</strong><span>{filter === "pending" ? "新的授权升级会自动进入这里。" : "切换其他分类查看决策记录。"}</span></div>}
      </aside>
      <main className="decision-detail">{selected ? <>
        <div className="decision-detail-head"><div><h2>{cleanText(selected.meeting.title)}</h2><button onClick={() => props.onOpenMeeting(selected.meeting.id)}>进入会议 <ChevronRight size={15} /></button></div><StatusBadge text={decisionText(selected.request.status)} tone={selected.request.status === "pending" ? "orange" : "green"} /></div>
        <section className="decision-question"><span>需要确认的问题</span><h3>{cleanText(selected.request.question)}</h3><div><span>收到时间：{formatAuditTime(selected.request.created_at)}</span><span>回复时限：{selected.request.reply_deadline ? formatAuditTime(selected.request.reply_deadline) : "尽快处理"}</span></div></section>
        <section className="decision-section"><h3><ShieldCheck size={17} />超出授权的原因</h3><p>{cleanText(selected.request.reason)}</p>{rule && <button className="evidence-line source-link" onClick={() => props.onOpenSource(workspace?.id, rule.id)}><span>当前授权范围</span><strong>{cleanText(rule.scope)}</strong></button>}{missingEvidence.map((id) => <div className="evidence-line missing" key={id}><span>{id}</span><strong>来源对象已不存在</strong></div>)}</section>
        <section className="decision-context"><div><span>关联目标</span><strong>{objective?.title ?? "未关联业务目标"}</strong><p>{objective ? `${objective.metric}，当前进度 ${objective.progress}%` : "该会议尚未关联可展示的目标。"}</p></div><div><span>当前风险</span><strong>{objective?.risk ?? "暂无已登记风险"}</strong><p>智能体已暂停该事项，会议中的其他授权内工作可继续。</p></div></section>
        <section className="decision-section recommendation"><h3><Bot size={17} />AI 建议与影响</h3><p>{cleanText(selected.request.ai_recommendation)}</p><small>同意或修改后回复将解除本事项暂停；拒绝后不执行该超权内容。</small></section>
        {unresolved(selected.request.status) ? <section className="decision-response"><label>给会议的回复<textarea value={props.replyDraft} onChange={(event) => props.setReplyDraft(event.target.value)} placeholder="输入明确的决定、边界和后续要求" /></label><div className="decision-actions"><button className="danger-button" onClick={() => props.onResolve(selected.meeting.id, selected.request.id, "reject")} disabled={props.busy === selected.request.id}><X size={16} />拒绝</button><button className="secondary-button" onClick={() => props.onResolve(selected.meeting.id, selected.request.id, "defer")} disabled={props.busy === selected.request.id}>暂不处理</button><button className="secondary-button" onClick={() => props.onResolve(selected.meeting.id, selected.request.id, "edit")} disabled={props.busy === selected.request.id || !props.replyDraft.trim()}><Send size={16} />修改后回复</button><button className="primary-button" onClick={() => props.onResolve(selected.meeting.id, selected.request.id, "approve")} disabled={props.busy === selected.request.id}><Check size={16} />同意建议</button></div></section> : <section className="decision-resolution"><Check size={18} /><div><span>本人回复</span><strong>{cleanText(selected.request.user_reply || "已完成处理")}</strong><small>处理时间：{formatAuditTime(selected.request.updated_at)}</small></div></section>}
      </> : <div className="decision-detail-empty"><AlertTriangle size={28} /><strong>没有可查看的决策事项</strong><span>会议中出现超出授权范围的问题后，会在这里形成独立处理记录。</span></div>}</main>
    </div>
  </section>;
}
function Results(props: { meeting: Meeting; ads: AdsContext | null; completeActionItem: (itemId: string, ownerId: string, dueDate: string) => void; writeback: () => void; writebackItem: (itemId: string) => void; busy: string }) {
  const analysis = props.meeting.analysis!;
  const awaitingDecision = props.meeting.status !== "confirmed";
  const hasIncompleteItems = analysis.action_items.some((item) => item.status === "incomplete");
  return <div className="results-grid">
    <article className="result-block"><strong>结构化纪要</strong><p>{cleanText(analysis.structured_minutes)}</p></article>
    <WorkloadMetricsCard metrics={analysis.metrics} />
    {analysis.decisions.map((decision) => <article className="result-block" key={decision.id}><strong>{cleanText(decision.topic)}</strong><p>{cleanText(decision.content)}</p><small>{cleanText(decision.evidence)}</small></article>)}
    {analysis.action_items.map((item) => {
      const writtenBack = item.status === "written_back";
      const failed = item.status === "writeback_failed";
      const incomplete = item.status === "incomplete";
      return <article className="task-card" key={item.id}>
        <strong>{cleanText(item.title)}</strong>
        <form className="form-pair" onChange={(event) => {
          const fields = new FormData(event.currentTarget);
          const ownerId = String(fields.get("owner_id") ?? "");
          const dueDate = String(fields.get("due_date") ?? "");
          if (ownerId && dueDate) props.completeActionItem(item.id, ownerId, dueDate);
        }}><select name="owner_id" disabled={awaitingDecision || writtenBack} defaultValue={item.owner_id ?? ""}><option value="" disabled>选择负责人</option>{props.ads?.people.map((person) => <option key={person.id} value={person.id}>{person.name}</option>)}</select><input name="due_date" type="date" disabled={awaitingDecision || writtenBack} defaultValue={item.due_date ?? ""} /></form>
        <div className="action-writeback-row"><StatusBadge text={writtenBack ? "已写回" : awaitingDecision ? "待本人确认" : failed ? "写回失败" : incomplete ? "信息不完整" : "待写回"} tone={writtenBack ? "green" : "orange"} /><button className="secondary-button" onClick={() => props.writebackItem(item.id)} disabled={awaitingDecision || writtenBack || incomplete || props.busy === `writeback-${item.id}`}>{awaitingDecision ? "等待本人决定" : props.busy === `writeback-${item.id}` ? "写回中" : failed ? "重试写回" : "写回此项"}</button></div>
        {(item.writeback_attempts ?? 0) > 0 && <small>尝试 {item.writeback_attempts} 次{item.writeback_task_id ? ` · 任务 ${item.writeback_task_id}` : ""}</small>}
        {item.writeback_error && <p className="inline-error">{cleanText(item.writeback_error)}</p>}
      </article>;
    })}
    <button className="primary-button" onClick={props.writeback} disabled={awaitingDecision || hasIncompleteItems || props.busy === "writeback"}><Database size={17} />批量写回可用行动项</button>
  </div>;
}
function WorkloadMetricsCard(props: { metrics: WorkloadMetrics }) {
  const metrics = props.metrics;
  return <article className="result-block workload-result"><div className="result-card-heading"><strong>本场可核验数据</strong><span className="data-status">{metrics.measurement_status === "measured" ? "已测量" : metrics.measurement_status === "partial" ? "部分记录" : "待采集"}</span></div><div className="result-metrics"><div><span>发言字符</span><b>{formatCount(metrics.transcript_characters)}</b></div><div><span>纪要字符</span><b>{formatCount(metrics.minutes_generated_characters)}</b></div><div><span>行动项</span><b>{metrics.action_items_created}</b></div><div><span>待确认</span><b>{metrics.escalations}</b></div></div><div className="metric-source"><span>改造前人工基准</span><strong>待采集</strong></div><small>来源：{metrics.data_source} · 样本数 {metrics.sample_count}。人工处理时长、确认耗时和节省比例暂不推算。</small></article>;
}
type AdsTab = "overview" | WorkspaceObjectTab;
type AdsEntity = Person | Project | Objective | BusinessMetric | Risk | Task | Policy | HistoricalStance | AuthorizationRule;
const adsTabLabels: Record<AdsTab, string> = { overview: "概览", people: "成员", projects: "项目", objectives: "目标", metrics: "指标", risks: "风险", tasks: "任务", policies: "制度", historical_stances: "历史立场", authorization: "授权" };
const adsTabs = Object.keys(adsTabLabels) as AdsTab[];
function AdsWorkspace(props: { workspaces: AdsWorkspace[]; focus: { workspaceId: string; objectId: string; nonce: number } | null; busy: string; onSave: (workspace: AdsWorkspace) => Promise<void>; onCreate: () => Promise<void>; onArchive: (workspaceId: string, archived: boolean) => Promise<void> }) {
  const [workspaceId, setWorkspaceId] = React.useState("");
  const [tab, setTab] = React.useState<AdsTab>("overview");
  const [query, setQuery] = React.useState("");
  const [editor, setEditor] = React.useState<{ kind: Exclude<AdsTab, "overview">; index: number | null } | null>(null);
  const workspace = props.workspaces.find((item) => item.id === workspaceId) ?? props.workspaces[0];
  React.useEffect(() => { if (!workspaceId && props.workspaces[0]) setWorkspaceId(props.workspaces[0].id); }, [workspaceId, props.workspaces]);
  React.useEffect(() => {
    if (!props.focus) return;
    const target = props.workspaces.find((item) => item.id === props.focus?.workspaceId);
    const located = target ? findWorkspaceObject(target, props.focus.objectId) : null;
    setWorkspaceId(props.focus.workspaceId);
    if (!located) { setEditor(null); window.alert(`来源对象已不存在：${props.focus.objectId}`); return; }
    setTab(located.tab); setEditor({ kind: located.tab, index: located.index });
  }, [props.focus?.nonce, props.workspaces]);
  if (!workspace) return <section className="page-grid"><section className="panel wide workspace-empty"><Empty text="还没有 ADS 工作区。先创建一个空白工作区，再录入你的团队资料。" /><button className="primary-button" onClick={() => void props.onCreate()} disabled={props.busy === "workspace-create"}><Plus size={17} />创建工作区</button></section></section>;
  const ownerName = (id: string | null) => workspace.people.find((person) => person.id === id)?.name ?? "待指定";
  const normalized = query.trim().toLowerCase();
  const saveEntity = async (kind: Exclude<AdsTab, "overview">, index: number | null, value: AdsEntity) => {
    const key = kind === "authorization" ? "authorization_rules" : kind;
    const list = [...workspace[key]] as AdsEntity[];
    if (index === null) list.push(value); else list[index] = value;
    await props.onSave({ ...workspace, [key]: list }); setEditor(null);
  };
  const counts = [{ label: "成员", value: workspace.people.length, icon: <UserRound size={18} /> }, { label: "目标", value: workspace.objectives.length, icon: <Target size={18} /> }, { label: "进行中任务", value: workspace.tasks.filter((item) => item.status !== "已完成").length, icon: <ListChecks size={18} /> }, { label: "授权规则", value: workspace.authorization_rules.length, icon: <ShieldCheck size={18} /> }];
  return <section className="ads-workspace"><header className="ads-header"><div className="workspace-identity"><div className="workspace-mark"><FolderKanban size={22} /></div><div><label>ADS 工作区<select value={workspace.id} onChange={(event) => setWorkspaceId(event.target.value)}>{props.workspaces.map((item) => <option value={item.id} key={item.id}>{item.name}{item.archived ? "（已归档）" : ""}</option>)}</select></label><p>{workspace.description || "尚未填写工作区说明"}</p></div></div><div className="workspace-actions"><button className="secondary-button" onClick={() => void props.onCreate()} disabled={props.busy === "workspace-create"}><Plus size={17} />新建工作区</button><button className="secondary-button" onClick={() => void props.onArchive(workspace.id, !workspace.archived)} disabled={props.busy === `workspace-archive-${workspace.id}`}>{workspace.archived ? "恢复工作区" : "归档工作区"}</button>{tab !== "overview" && <button className="primary-button" onClick={() => setEditor({ kind: tab, index: null })}><Plus size={17} />新建{adsTabLabels[tab]}</button>}</div></header><nav className="ads-tabs">{adsTabs.map((item) => <button className={tab === item ? "active" : ""} key={item} onClick={() => { setTab(item); setQuery(""); }}>{adsTabLabels[item]}</button>)}</nav>{tab === "overview" ? <div className="ads-overview"><div className="ads-stat-row">{counts.map((item) => <article key={item.label}>{item.icon}<span>{item.label}</span><strong>{item.value}</strong></article>)}</div><section className="ads-overview-grid"><div><div className="section-bar"><h2>目标进展</h2><button onClick={() => setTab("objectives")}>查看全部 <ChevronRight size={15} /></button></div>{workspace.objectives.slice(0, 4).map((item) => <article className="objective-row" key={item.id}><div><strong>{item.title}</strong><span>{item.metric}</span></div><div className="objective-progress"><b>{item.progress}%</b><div className="progress"><span style={{ width: `${item.progress}%` }} /></div></div></article>)}</div><div><div className="section-bar"><h2>近期任务</h2><button onClick={() => setTab("tasks")}>查看全部 <ChevronRight size={15} /></button></div>{workspace.tasks.slice(0, 5).map((item) => <article className="task-row" key={item.id}><div><strong>{item.title}</strong><span>{ownerName(item.owner_id)} · {item.due_date}</span></div><StatusBadge text={item.status} tone={item.status === "已完成" ? "green" : "blue"} /></article>)}</div></section></div> : <AdsObjectList workspace={workspace} tab={tab} query={query} setQuery={setQuery} ownerName={ownerName} onEdit={(index) => setEditor({ kind: tab, index })} />}{editor && <AdsEditor workspace={workspace} kind={editor.kind} index={editor.index} saving={props.busy === `workspace-${workspace.id}`} onClose={() => setEditor(null)} onSave={(value) => saveEntity(editor.kind, editor.index, value)} />}</section>;
}

function AdsObjectList(props: { workspace: AdsWorkspace; tab: Exclude<AdsTab, "overview">; query: string; setQuery: (value: string) => void; ownerName: (id: string | null) => string; onEdit: (index: number) => void }) {
  const key = props.tab === "authorization" ? "authorization_rules" : props.tab;
  const rows = props.workspace[key] as AdsEntity[];
  const filtered = rows.map((item, index) => ({ item, index })).filter(({ item }) => !props.query.trim() || JSON.stringify(item).toLowerCase().includes(props.query.trim().toLowerCase()));
  const detail = (item: AdsEntity) => {
    if ("role" in item) return item.role;
    if ("description" in item) return `${item.status} · ${props.ownerName(item.owner_id)}`;
    if ("current_value" in item) return `${item.current_value ?? "—"} / ${item.target_value ?? "—"} ${item.unit}`;
    if ("impact" in item) return `${item.status} · ${item.impact}`;
    if ("content" in item) return `${item.scope} · ${item.content}`;
    if ("stance" in item) return `${props.ownerName(item.person_id)} · ${item.stance}`;
    if ("progress" in item) return `${item.progress}% · ${item.metric}`;
    if ("due_date" in item) return `${props.ownerName(item.owner_id)} · ${item.due_date} · ${item.status}`;
    return `${props.ownerName(item.person_id)} · ${item.scope}`;
  };
  const title = (item: AdsEntity) => "name" in item ? item.name : "title" in item ? item.title : "topic" in item ? item.topic : "scope" in item ? item.scope : (item as { id: string }).id;
  return <div className="ads-content"><div className="content-toolbar"><div className="search-box compact"><Search size={16} /><input placeholder={`搜索${adsTabLabels[props.tab]}`} value={props.query} onChange={(event) => props.setQuery(event.target.value)} /></div><span>共 {rows.length} 条</span></div><div className="data-list">{filtered.map(({ item, index }) => <button className="data-row object-data" key={item.id} onClick={() => props.onEdit(index)}><div><strong>{title(item)}</strong><span>{detail(item)}</span></div><code>{item.id}</code><ChevronRight size={16} /></button>)}{!filtered.length && <Empty text={`还没有${adsTabLabels[props.tab]}，可从右上角新建。`} />}</div></div>;
}

function AdsEditor(props: { workspace: AdsWorkspace; kind: Exclude<AdsTab, "overview">; index: number | null; saving: boolean; onClose: () => void; onSave: (value: AdsEntity) => void }) {
  const existing = props.index === null ? null : (props.kind === "authorization" ? props.workspace.authorization_rules : props.workspace[props.kind])[props.index];
  const [form, setForm] = React.useState<Record<string, string>>(() => existing ? Object.fromEntries(Object.entries(existing).map(([key, value]) => [key, Array.isArray(value) ? value.join("、") : String(value ?? "")])) : {});
  const set = (key: string, value: string) => setForm((current) => ({ ...current, [key]: value }));
  const title = adsTabLabels[props.kind];
  function submit() {
    const id = form.id || `${props.kind.slice(0, 4)}_${Date.now().toString(36)}`;
    if (props.kind === "people") props.onSave({ id, name: form.name?.trim() || "新成员", role: form.role?.trim() || "成员" });
    if (props.kind === "projects") props.onSave({ id, name: form.name?.trim() || "新项目", description: form.description?.trim() || "", status: form.status || "进行中", owner_id: form.owner_id || null });
    if (props.kind === "objectives") props.onSave({ id, title: form.title?.trim() || "新目标", progress: Math.max(0, Math.min(100, Number(form.progress) || 0)), metric: form.metric?.trim() || "待补充衡量指标", risk: form.risk?.trim() || "暂无风险" });
    if (props.kind === "tasks") props.onSave({ id, title: form.title?.trim() || "新任务", owner_id: form.owner_id || props.workspace.people[0]?.id || "", due_date: form.due_date || new Date().toISOString().slice(0, 10), status: form.status || "未开始" });
    if (props.kind === "metrics") props.onSave({ id, name: form.name?.trim() || "新指标", current_value: form.current_value ? Number(form.current_value) : null, target_value: form.target_value ? Number(form.target_value) : null, unit: form.unit?.trim() || "", objective_id: form.objective_id || null });
    if (props.kind === "risks") props.onSave({ id, title: form.title?.trim() || "新风险", impact: form.impact?.trim() || "", owner_id: form.owner_id || null, status: form.status || "开放", project_id: form.project_id || null });
    if (props.kind === "policies") props.onSave({ id, title: form.title?.trim() || "新制度", content: form.content?.trim() || "", scope: form.scope?.trim() || "" });
    if (props.kind === "historical_stances") props.onSave({ id, person_id: form.person_id || props.workspace.people[0]?.id || "", topic: form.topic?.trim() || "新主题", stance: form.stance?.trim() || "", effective_scope: form.effective_scope?.trim() || "", updated_at: new Date().toISOString() });
    if (props.kind === "authorization") props.onSave({ id, person_id: form.person_id || props.workspace.people[0]?.id || "", scope: form.scope?.trim() || "允许检索并说明已有业务信息", allowed_actions: (form.allowed_actions || "提供信息").split(/[、,，\n]/).map((item) => item.trim()).filter(Boolean), escalation_triggers: (form.escalation_triggers || "新增预算、改变技术路线").split(/[、,，\n]/).map((item) => item.trim()).filter(Boolean) });
  }
  const personOptions = <><option value="">待指定</option>{props.workspace.people.map((person) => <option key={person.id} value={person.id}>{person.name} · {person.role}</option>)}</>;
  return <div className="modal-backdrop" onMouseDown={props.onClose}><section className="edit-dialog" onMouseDown={(event) => event.stopPropagation()}><header><div><span>{props.index === null ? "新建" : "编辑"}</span><h2>{title}</h2></div><button className="icon-button" onClick={props.onClose} title="关闭"><X size={18} /></button></header><div className="dialog-body">
    {props.kind === "people" && <><label>姓名<input value={form.name || ""} onChange={(event) => set("name", event.target.value)} autoFocus /></label><label>岗位或职责<input value={form.role || ""} onChange={(event) => set("role", event.target.value)} /></label></>}
    {props.kind === "projects" && <><label>项目名称<input value={form.name || ""} onChange={(event) => set("name", event.target.value)} autoFocus /></label><label>说明<textarea value={form.description || ""} onChange={(event) => set("description", event.target.value)} /></label><div className="form-pair"><label>状态<select value={form.status || "进行中"} onChange={(event) => set("status", event.target.value)}><option>未开始</option><option>进行中</option><option>已暂停</option><option>已完成</option></select></label><label>负责人<select value={form.owner_id || ""} onChange={(event) => set("owner_id", event.target.value)}>{personOptions}</select></label></div></>}
    {props.kind === "objectives" && <><label>目标名称<input value={form.title || ""} onChange={(event) => set("title", event.target.value)} autoFocus /></label><label>当前进度：{form.progress || 0}%<input type="range" min="0" max="100" value={form.progress || 0} onChange={(event) => set("progress", event.target.value)} /></label><label>衡量指标<textarea value={form.metric || ""} onChange={(event) => set("metric", event.target.value)} /></label><label>当前风险<textarea value={form.risk || ""} onChange={(event) => set("risk", event.target.value)} /></label></>}
    {props.kind === "metrics" && <><label>指标名称<input value={form.name || ""} onChange={(event) => set("name", event.target.value)} autoFocus /></label><div className="form-pair"><label>当前值<input type="number" value={form.current_value || ""} onChange={(event) => set("current_value", event.target.value)} /></label><label>目标值<input type="number" value={form.target_value || ""} onChange={(event) => set("target_value", event.target.value)} /></label></div><div className="form-pair"><label>单位<input value={form.unit || ""} onChange={(event) => set("unit", event.target.value)} /></label><label>所属目标<select value={form.objective_id || ""} onChange={(event) => set("objective_id", event.target.value)}><option value="">未关联</option>{props.workspace.objectives.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label></div></>}
    {props.kind === "risks" && <><label>风险标题<input value={form.title || ""} onChange={(event) => set("title", event.target.value)} autoFocus /></label><label>影响<textarea value={form.impact || ""} onChange={(event) => set("impact", event.target.value)} /></label><div className="form-pair"><label>负责人<select value={form.owner_id || ""} onChange={(event) => set("owner_id", event.target.value)}>{personOptions}</select></label><label>状态<select value={form.status || "开放"} onChange={(event) => set("status", event.target.value)}><option>开放</option><option>处理中</option><option>已缓解</option><option>已关闭</option></select></label></div><label>所属项目<select value={form.project_id || ""} onChange={(event) => set("project_id", event.target.value)}><option value="">未关联</option>{props.workspace.projects.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label></>}
    {props.kind === "tasks" && <><label>任务名称<input value={form.title || ""} onChange={(event) => set("title", event.target.value)} autoFocus /></label><label>负责人<select value={form.owner_id || props.workspace.people[0]?.id || ""} onChange={(event) => set("owner_id", event.target.value)}>{personOptions}</select></label><div className="form-pair"><label>截止日期<input type="date" value={form.due_date || ""} onChange={(event) => set("due_date", event.target.value)} /></label><label>状态<select value={form.status || "未开始"} onChange={(event) => set("status", event.target.value)}><option>未开始</option><option>进行中</option><option>待确认</option><option>已完成</option></select></label></div></>}
    {props.kind === "policies" && <><label>制度标题<input value={form.title || ""} onChange={(event) => set("title", event.target.value)} autoFocus /></label><label>内容<textarea value={form.content || ""} onChange={(event) => set("content", event.target.value)} /></label><label>适用范围<input value={form.scope || ""} onChange={(event) => set("scope", event.target.value)} /></label></>}
    {props.kind === "historical_stances" && <><label>人员<select value={form.person_id || props.workspace.people[0]?.id || ""} onChange={(event) => set("person_id", event.target.value)}>{personOptions}</select></label><label>主题<input value={form.topic || ""} onChange={(event) => set("topic", event.target.value)} autoFocus /></label><label>历史立场<textarea value={form.stance || ""} onChange={(event) => set("stance", event.target.value)} /></label><label>生效范围<input value={form.effective_scope || ""} onChange={(event) => set("effective_scope", event.target.value)} /></label></>}
    {props.kind === "authorization" && <><label>授权人<select value={form.person_id || props.workspace.people[0]?.id || ""} onChange={(event) => set("person_id", event.target.value)}>{personOptions}</select></label><label>授权范围<textarea value={form.scope || ""} onChange={(event) => set("scope", event.target.value)} autoFocus /></label><label>允许执行的操作<textarea value={form.allowed_actions || ""} placeholder="使用顿号或换行分隔" onChange={(event) => set("allowed_actions", event.target.value)} /></label><label>必须升级本人的条件<textarea value={form.escalation_triggers || ""} placeholder="使用顿号或换行分隔" onChange={(event) => set("escalation_triggers", event.target.value)} /></label></>}
  </div><footer><button className="secondary-button" onClick={props.onClose}>取消</button><button className="primary-button" onClick={submit} disabled={props.saving}>{props.saving ? "保存中" : "保存"}</button></footer></section></div>;
}
function AgentCenter(props: { meetings: Meeting[]; workspaces: AdsWorkspace[]; settings: AppSettings | null; models: ModelConfig[]; aiRuntime: AiRuntimeStatus | null; busy: string; onSaveIdentity: (identity: Person) => Promise<void>; onSelectIdentity: (identityId: string) => Promise<void>; onNavigate: (view: View) => void; onOpenMeeting: (id: string) => void }) {
  const activeIdentity = props.settings?.identities.find((item) => item.id === props.settings?.active_identity_id) ?? props.settings?.identities[0];
  const activeWorkspace = props.workspaces.find((item) => item.id === props.settings?.active_workspace_id) ?? props.workspaces[0];
  const delegated = props.meetings.filter((meeting) => meeting.participation_mode === "delegate");
  const running = delegated.filter((meeting) => meeting.agent_session_state === "delegating").length;
  const runnableModels = getRunnableModels(props.models, props.aiRuntime);
  const [form, setForm] = React.useState({ id: "", name: "", role: "", description: "" });
  function editIdentity(identity?: Person) { setForm(identity ? { id: identity.id, name: identity.name, role: identity.role, description: identity.description ?? "" } : { id: "", name: "", role: "", description: "" }); }
  function submitIdentity() {
    if (!form.name.trim()) return;
    void props.onSaveIdentity({ id: form.id || `person_${Date.now().toString(36)}`, name: form.name.trim(), role: form.role.trim(), description: form.description.trim() });
  }
  return <section className="agent-center page-grid">
    <section className="panel wide"><div className="section-heading"><div><PanelTitle icon={<Bot size={18} />} title="智能体中心" /><p>集中管理本人身份、会议代理、授权来源和运行模型。</p></div><button className="secondary-button" onClick={() => props.onNavigate("settings")}><Settings size={15} />模型设置</button></div><div className="agent-config-grid"><Metric label="当前身份" value={activeIdentity?.name ?? "尚未配置"} tone="blue" /><Metric label="代理中会议" value={`${running} 场`} tone="green" /><Metric label="当前可运行模型" value={`${runnableModels.length} 个`} tone="blue" /></div><p className="agent-runtime-summary"><strong>当前实际运行：</strong>{props.aiRuntime ? `${props.aiRuntime.label} · ${props.aiRuntime.message}` : "正在读取运行状态"}</p></section>
    <section className="panel identity-panel"><div className="section-heading"><PanelTitle icon={<UserRound size={18} />} title="本人身份" /><button className="secondary-button" onClick={() => editIdentity()}><Plus size={15} />新增身份</button></div><label>当前使用身份<select value={activeIdentity?.id ?? ""} onChange={(event) => void props.onSelectIdentity(event.target.value)} disabled={props.busy === "identity-select"}>{props.settings?.identities.map((identity) => <option key={identity.id} value={identity.id}>{identity.name} · {identity.role || "未填写职责"}</option>)}</select></label><div className="identity-list">{props.settings?.identities.map((identity) => <button key={identity.id} className={activeIdentity?.id === identity.id ? "identity-row active" : "identity-row"} onClick={() => editIdentity(identity)}><span className="avatar">{identity.name.slice(0, 1)}</span><div><strong>{identity.name}</strong><small>{identity.role || "未填写职责"}</small></div><ChevronRight size={15} /></button>)}</div><div className="identity-form"><h3>{form.id ? "编辑身份" : "新增身份"}</h3><label>姓名<input value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} /></label><label>岗位或职责<input value={form.role} onChange={(event) => setForm((current) => ({ ...current, role: event.target.value }))} /></label><label>身份说明<textarea value={form.description} onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))} /></label><button className="primary-button" onClick={submitIdentity} disabled={!form.name.trim() || props.busy === "identity-save"}>{props.busy === "identity-save" ? "保存中" : "保存并设为当前身份"}</button></div></section>
    <section className="panel agent-session-panel"><div className="section-heading"><PanelTitle icon={<ShieldCheck size={18} />} title="代理会话与授权" /><button className="secondary-button" onClick={() => props.onNavigate("ads")}>管理 ADS 授权</button></div><div className="agent-session-list">{delegated.map((meeting) => { const workspace = props.workspaces.find((item) => item.id === meeting.workspace_id); const identity = workspace?.people.find((item) => item.id === meeting.agent_identity_id); return <button key={meeting.id} onClick={() => props.onOpenMeeting(meeting.id)}><div><strong>{cleanText(meeting.title)}</strong><span>{identity?.name ?? "未识别身份"} · {meeting.authorization_rule_ids.length} 条本场授权</span></div><StatusBadge text={agentStateText(meeting.agent_session_state)} tone={meeting.agent_session_state === "failed" ? "orange" : "green"} /></button>; })}{!delegated.length && <Empty text="尚无委托智能体参与的会议。" />}</div><div className="agent-boundary-summary"><span>当前工作区</span><strong>{activeWorkspace?.name ?? "未选择"}</strong><p>{activeWorkspace ? `${activeWorkspace.authorization_rules.length} 条授权、${activeWorkspace.people.length} 位可选身份。` : "请先创建工作区并配置授权。"}</p></div></section>
  </section>;
}
function SettingsView(props: { models: ModelConfig[]; aiRuntime: AiRuntimeStatus | null; providers: ProviderDefinition[]; audits: ModelCallAudit[]; baselines: MetricBaseline[]; meetings: Meeting[]; settings: AppSettings | null; speechHealth: SpeechHealth | null; dataOverview: DataOverview | null; busy: string; onSave: (model: ModelConfig, apiKey?: string) => void; onTest: (providerId: string) => void; onInstallProvider: (vendorId: string) => Promise<void>; onSaveBaseline: (baseline: MetricBaseline) => Promise<void>; onBackup: () => Promise<void>; onRestore: (filename: string) => Promise<void>; onCleanup: () => Promise<void>; onRetention: (days: 0 | 30 | 90) => Promise<void>; onReset: () => Promise<void>; onDeleteMeeting: (meetingId: string) => Promise<void> }) {
  const availableProviders = props.providers.filter((provider) => !props.models.some((model) => model.vendor_id === provider.vendor_id || model.provider_id === provider.vendor_id || model.provider_name === provider.name));
  const runnableModels = getRunnableModels(props.models, props.aiRuntime);
  const [backup, setBackup] = React.useState("");
  const [ttsAuto, setTtsAuto] = React.useState(() => localStorage.getItem("ads.tts.auto") !== "false");
  React.useEffect(() => { if (!backup && props.dataOverview?.backups[0]) setBackup(props.dataOverview.backups[0]); }, [backup, props.dataOverview?.backups]);
  return <section className="settings-grid">
    <section className="panel settings-main">
      <div className="section-heading"><div><PanelTitle icon={<Settings size={18} />} title="模型服务" /><p>会议工作流统一使用已配置模型，API Key 只保存在本机后端。</p></div></div>
      <div className={props.aiRuntime?.mode === "mock" ? "model-runtime-summary mock" : "model-runtime-summary"}><div><strong>当前实际运行：{props.aiRuntime?.label ?? "正在确认"}</strong><span>{props.aiRuntime?.message ?? "正在读取后端运行状态。"}</span></div><StatusBadge text={`${runnableModels.length} 个可运行`} tone={runnableModels.length ? "green" : "orange"} /></div>
      <div className="model-editor-list">{props.models.map((model) => <ModelEditor key={model.provider_id} model={model} aiRuntime={props.aiRuntime} saving={props.busy === `model-${model.provider_id}`} testing={props.busy === `model-test-${model.provider_id}`} onSave={props.onSave} onTest={() => props.onTest(model.provider_id)} />)}</div>
      {availableProviders.length > 0 && <section className="provider-catalog"><h3>添加模型服务</h3><p>只添加实际需要配置的服务，添加后再填写本机 API Key。</p><div>{availableProviders.map((provider) => <button className="secondary-button" key={provider.vendor_id} onClick={() => void props.onInstallProvider(provider.vendor_id)} disabled={props.busy === "provider-install"}><Plus size={15} />{provider.name}</button>)}</div></section>}
      <section className="model-audit-section"><h3>模型调用审计</h3><div className="model-audit-list">{props.audits.slice(0, 20).map((audit) => <article key={audit.id}><div><strong>{audit.provider_id} · {audit.model}</strong><StatusBadge text={audit.status === "success" ? "成功" : audit.status === "fallback" ? "本地降级" : "失败"} tone={audit.status === "success" ? "green" : "orange"} /></div><span>{audit.operation} · {audit.duration_ms} ms · Token {audit.token_usage ?? "未返回"}</span><small>{formatAuditTime(audit.created_at)} · Prompt {audit.prompt_version}{audit.error ? ` · ${audit.error}` : ""}</small></article>)}{!props.audits.length && <Empty text="尚无模型调用记录。" />}</div></section>
      <MetricBaselinePanel baselines={props.baselines} meetings={props.meetings} saving={props.busy === "metric-baseline"} onSave={props.onSaveBaseline} />
    </section>
    <aside className="settings-side">
      <section className="panel"><PanelTitle icon={<Mic size={18} />} title="本地语音" /><div className={props.speechHealth?.status === "ready" ? "health-summary ready" : "health-summary degraded"}><strong>{props.speechHealth?.status === "ready" ? "组件可用" : "组件未就绪"}</strong><span>{props.speechHealth?.message ?? "正在检测"}</span></div><dl><div><dt>FFmpeg</dt><dd>{props.speechHealth?.ffmpeg_available ? "可用" : "未安装"}</dd></div><div><dt>Whisper 模型</dt><dd>{props.speechHealth?.model_available ? "可用" : "未安装"}</dd></div></dl><p className="settings-note">{props.speechHealth?.status === "ready" ? "录音和音频文件会在本机完成转写，不上传到第三方语音服务。" : "语音组件不可用时，仍可直接输入会议文字。"}</p></section>
      <section className="panel"><PanelTitle icon={<Volume2 size={18} />} title="回复播放" /><label className="check-control"><input type="checkbox" checked={ttsAuto} onChange={(event) => { const checked = event.target.checked; setTtsAuto(checked); localStorage.setItem("ads.tts.auto", String(checked)); if (!checked && "speechSynthesis" in window) window.speechSynthesis.cancel(); }} />自动播放新的智能体回复</label><p className="settings-note">使用 Windows / 浏览器原生中文语音；关闭或切换会议时会立即停止播放。</p></section>
      <section className="panel local-data-panel"><PanelTitle icon={<Database size={18} />} title="本地数据" /><dl><div><dt>数据库</dt><dd>{formatBytes(props.dataOverview?.database_bytes)}</dd></div><div><dt>音频</dt><dd>{formatBytes(props.dataOverview?.audio_bytes)}</dd></div><div><dt>会议 / 工作区</dt><dd>{props.dataOverview ? `${props.dataOverview.meetings} / ${props.dataOverview.workspaces}` : "正在读取"}</dd></div><div><dt>转写任务</dt><dd>{props.dataOverview?.speech_jobs ?? 0}</dd></div></dl><label>原始音频保留期<select value={props.settings?.audio_retention_days ?? 0} onChange={(event) => void props.onRetention(Number(event.target.value) as 0 | 30 | 90)} disabled={props.busy === "settings-retention"}><option value={0}>长期保留</option><option value={30}>30 天</option><option value={90}>90 天</option></select></label><div className="data-actions"><button className="secondary-button" onClick={() => void props.onBackup()} disabled={props.busy === "data-backup"}>创建备份</button><button className="secondary-button" onClick={() => void props.onCleanup()} disabled={props.busy === "data-cleanup"}>清理音频</button></div><label>恢复本地备份<select value={backup} onChange={(event) => setBackup(event.target.value)}><option value="">选择备份</option>{props.dataOverview?.backups.map((filename) => <option key={filename} value={filename}>{filename}</option>)}</select></label><button className="secondary-button full-button" onClick={() => void props.onRestore(backup)} disabled={!backup || props.busy === "data-restore"}>从所选备份恢复</button><details className="meeting-delete-list"><summary>按会议删除数据</summary>{props.meetings.map((meeting) => <button key={meeting.id} className="danger-button full-button" onClick={() => void props.onDeleteMeeting(meeting.id)} disabled={props.busy === `meeting-delete-${meeting.id}`}>{cleanText(meeting.title)}</button>)}</details><button className="danger-button full-button" onClick={() => void props.onReset()} disabled={props.busy === "data-reset"}>恢复空白数据</button><p className="settings-note">恢复、删除、清理和重置都会先显示影响确认；API Key 不包含在普通页面数据中。</p></section>
    </aside>
  </section>;
}

function MetricBaselinePanel(props: { baselines: MetricBaseline[]; meetings: Meeting[]; saving: boolean; onSave: (baseline: MetricBaseline) => Promise<void> }) {
  const analyzedMeetings = props.meetings.filter((meeting) => meeting.analysis);
  const [form, setForm] = React.useState({ meeting_id: analyzedMeetings[0]?.id ?? "", meeting_type: "项目进度同步", baseline_minutes: "", post_process_minutes: "", sample_date: new Date().toISOString().slice(0, 10), source: "现场计时", notes: "" });
  const update = (key: keyof typeof form, value: string) => setForm((current) => ({ ...current, [key]: value }));
  const baselineMinutes = Number(form.baseline_minutes);
  const postMinutes = Number(form.post_process_minutes);
  const valid = Boolean(form.meeting_id && form.meeting_type.trim() && baselineMinutes > 0 && postMinutes >= 0 && form.sample_date && form.source.trim());
  function submit() {
    if (!valid) return;
    void props.onSave({ id: `baseline_${Date.now().toString(36)}`, meeting_id: form.meeting_id, meeting_type: form.meeting_type.trim(), baseline_minutes: baselineMinutes, post_process_minutes: postMinutes, sample_date: form.sample_date, source: form.source.trim(), notes: form.notes.trim() });
  }
  function downloadReport() {
    const url = URL.createObjectURL(new Blob([buildMetricReport(props.baselines)], { type: "text/markdown;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url; link.download = `ADS减负指标-${new Date().toISOString().slice(0, 10)}.md`; link.click();
    URL.revokeObjectURL(url);
  }
  return <section className="metric-baseline-section" id="metric-baseline" tabIndex={-1}><div className="section-heading"><div><h3>减负基准与单场下钻</h3><p>只录入实际计时；系统按单场会议保存人工与系统后处理对照。</p></div><button className="secondary-button" onClick={downloadReport} disabled={!props.baselines.length}><Download size={15} />下载 Markdown 报告</button></div><div className="baseline-form"><label>关联会议<select value={form.meeting_id} onChange={(event) => update("meeting_id", event.target.value)}><option value="">选择已分析会议</option>{analyzedMeetings.map((meeting) => <option key={meeting.id} value={meeting.id}>{cleanText(meeting.title)}</option>)}</select></label><label>会议类型<select value={form.meeting_type} onChange={(event) => update("meeting_type", event.target.value)}><option>项目进度同步</option><option>技术/方案评审</option><option>跨部门协调</option><option>其他真实会议</option></select></label><div className="form-pair"><label>人工处理分钟<input type="number" min="0.1" step="0.1" value={form.baseline_minutes} onChange={(event) => update("baseline_minutes", event.target.value)} /></label><label>系统后处理分钟<input type="number" min="0" step="0.1" value={form.post_process_minutes} onChange={(event) => update("post_process_minutes", event.target.value)} /></label></div><div className="form-pair"><label>样本日期<input type="date" value={form.sample_date} onChange={(event) => update("sample_date", event.target.value)} /></label><label>计时来源<input value={form.source} onChange={(event) => update("source", event.target.value)} /></label></div><label>说明<textarea value={form.notes} onChange={(event) => update("notes", event.target.value)} placeholder="例如：同一材料分别人工处理和使用系统处理" /></label><button className="primary-button" onClick={submit} disabled={!valid || props.saving}>{props.saving ? "保存中" : "保存人工基准"}</button></div><div className="baseline-list">{props.baselines.map((baseline) => <article key={baseline.id}><div><strong>{baseline.meeting_type}</strong><span>{baseline.sample_date} · {baseline.source}</span></div><b>{savingsPercent(baseline.baseline_minutes, baseline.post_process_minutes).toFixed(1)}%</b><small>人工 {baseline.baseline_minutes.toFixed(1)} 分钟 → 系统 {baseline.post_process_minutes.toFixed(1)} 分钟</small></article>)}{!props.baselines.length && <Empty text="尚无人工基准。完成真实会议后在这里记录实际计时。" />}</div></section>;
}

function ModelEditor(props: { model: ModelConfig; aiRuntime: AiRuntimeStatus | null; saving: boolean; testing: boolean; onSave: (model: ModelConfig, apiKey?: string) => void; onTest: () => void }) {
  const [draft, setDraft] = React.useState(props.model);
  const [apiKey, setApiKey] = React.useState("");
  React.useEffect(() => setDraft(props.model), [props.model]);
  function update<K extends keyof ModelConfig>(key: K, value: ModelConfig[K]) { setDraft((item) => ({ ...item, [key]: value })); }
  const runtimeState = getModelRuntimeState(draft, props.aiRuntime);
  return <article className={`model-editor ${draft.is_default ? "default" : ""}`}><header><div><strong>{draft.provider_name}</strong><span>{draft.adapter_type === "mock" ? "本地基础能力" : draft.adapter_type === "deepseek" ? "在线模型" : "OpenAI 兼容服务"}</span></div><div className="model-statuses"><span>最近连接 <StatusBadge text={modelStatusText(draft.connection_status)} tone={draft.connection_status === "ok" || draft.connection_status === "mock" ? "green" : "orange"} /></span><span>当前运行 <StatusBadge text={runtimeState.label} tone={runtimeState.runnable ? "green" : "orange"} /></span></div></header><p className="model-runtime-reason">{runtimeState.reason}</p><div className="model-form"><label>服务地址<input value={draft.base_url} onChange={(event) => update("base_url", event.target.value)} disabled={draft.adapter_type === "mock"} /></label><label>模型名称<input value={draft.model} onChange={(event) => update("model", event.target.value)} disabled={draft.adapter_type === "mock"} /></label>{draft.adapter_type !== "mock" && <label className="api-key-field">API Key<input type="password" autoComplete="new-password" value={apiKey} placeholder={draft.api_key_masked ? "已配置，留空则保持不变" : "输入 API Key"} onChange={(event) => setApiKey(event.target.value)} /></label>}</div><footer><label className="check-control"><input type="checkbox" checked={draft.enabled} onChange={(event) => update("enabled", event.target.checked)} />启用</label><label className="check-control"><input type="radio" name="default-model" checked={draft.is_default} onChange={() => update("is_default", true)} />设为默认</label><span className="model-message">{draft.message}</span><button className="secondary-button" onClick={props.onTest} disabled={props.testing}>{props.testing ? "测试中" : "测试连接"}</button><button className="primary-button" onClick={() => props.onSave(draft, apiKey)} disabled={props.saving}>{props.saving ? "保存中" : "保存配置"}</button></footer></article>;
}

function Metric(props: { label: string; value: string; tone: "green" | "blue" | "orange" }) { return <article className={`metric ${props.tone}`}><span>{props.label}</span><strong>{props.value}</strong></article>; }
function MeetingStateSummary(props: { meeting: Meeting; compact?: boolean }) {
  const pending = props.meeting.escalation_requests.filter((item) => item.status === "pending").length;
  const agentLabel = props.meeting.participation_mode === "delegate" ? props.meeting.agent_session_state === "delegating" ? "智能体代理中" : props.meeting.agent_session_state === "paused" ? "智能体已暂停" : props.meeting.agent_session_state === "completed" ? "代理已完成" : "等待委托确认" : "本人参加";
  return <div className={props.compact ? "meeting-state-summary compact" : "meeting-state-summary"}><span className="state-pill meeting">{meetingLifecycleText(props.meeting.meeting_status)}</span><span className="state-pill outcome">{meetingOutcomeText(props.meeting.status)}</span><span className="state-pill agent">{agentLabel}</span>{pending > 0 && <span className="state-pill attention">{pending} 项待本人确认</span>}</div>;
}
function MeetingRow(props: { title: string; time: string; mode: string; status: React.ReactNode; hot?: boolean; onClick?: () => void }) { return <button className={props.hot ? "meeting-row hot" : "meeting-row"} onClick={props.onClick}><span>{props.time}</span><strong>{props.title}</strong><em>{props.mode}</em><div className="meeting-row-state">{props.status}</div></button>; }
function PanelTitle(props: { icon: React.ReactNode; title: string }) { return <div className="panel-title">{props.icon}<h2>{props.title}</h2></div>; }
function Empty(props: { text: string }) { return <p className="empty">{props.text}</p>; }
function Avatar(props: { name: string; subtitle: string; ai?: boolean }) { return <div className="person"><div className={props.ai ? "person-avatar ai" : "person-avatar"}>{props.ai ? <Bot size={18} /> : props.name.slice(0, 1)}</div><span>{props.name}</span><small>{props.subtitle}</small></div>; }
function StatusBadge(props: { text: string; tone: "green" | "blue" | "orange" }) { return <span className={`status ${props.tone}`}>{props.text}</span>; }
function formatCount(value: number) { return new Intl.NumberFormat("zh-CN").format(value); }
function statusText(meeting: Meeting | null | undefined) { if (!meeting) return "待创建"; return ({ draft: "草稿", prepared: "已生成简报", awaiting_confirmation: "待本人确认", confirmed: "待回写", rejected: "已拒绝", completed: "已闭环" } as const)[meeting.status] ?? meeting.status; }
function meetingLifecycleText(status: Meeting["meeting_status"]) { return ({ draft: "会议准备中", scheduled: "等待开始", in_progress: "会议进行中", ended: "会议已结束", closed: "会议已结束", cancelled: "已取消" } as const)[status]; }
function meetingOutcomeText(status: Meeting["status"]) { return ({ draft: "成果未生成", prepared: "成果待整理", awaiting_confirmation: "成果待本人确认", confirmed: "成果待写回", rejected: "成果已拒绝", completed: "成果已闭环" } as const)[status]; }
function agentStateText(state: Meeting["agent_session_state"]) { return ({ not_started: "未启动", preparing: "准备中", delegating: "代理中", paused: "等待本人确认", completed: "已完成", failed: "失败" } as const)[state]; }
function decisionText(status: EscalationRequest["status"]) { return ({ pending: "待处理", deferred: "暂不处理", approved: "已同意", edited: "已修改", rejected: "已拒绝", expired: "已过期" } as const)[status]; }
function formatTime(value: number) { return `${Math.floor(value / 60).toString().padStart(2, "0")}:${Math.floor(value % 60).toString().padStart(2, "0")}`; }
function formatBytes(value = 0) { if (!value) return "大小未知"; if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} KB`; return `${(value / (1024 * 1024)).toFixed(1)} MB`; }
function formatAudioDuration(value?: number | null) { return value && value > 0 ? formatTime(Math.round(value)) : "时长未知"; }
function formatMeetingTimeRange(start: string, durationMinutes: number) {
  const date = new Date(start.replace(" ", "T"));
  if (Number.isNaN(date.getTime())) return start;
  const end = new Date(date.getTime() + durationMinutes * 60_000);
  const format = (value: Date) => value.toLocaleString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).replace(/\//g, "-");
  return `${format(date)} - ${format(end)}`;
}
function audioMeta(job: SpeechJob) { return `${formatBytes(job.size_bytes)} · ${formatAudioDuration(job.duration_seconds)}`; }
function processingMeta(job: SpeechJob) { return job.processing_seconds && job.processing_seconds > 0 ? ` · 用时 ${job.processing_seconds.toFixed(1)} 秒` : ""; }
function modelStatusText(status: ModelConfig["connection_status"]) { return ({ not_configured: "未配置", untested: "待测试", ok: "连接正常", failed: "连接失败", mock: "本地可用" } as const)[status]; }
function cleanText(value: string) {
  const cleaned = String(value ?? "")
    .replace(/`n|\\n/g, "\n")
    .replace(/作品级\s*MVP/gi, "本期交付")
    .replace(/作品级\s*Demo/gi, "首个可用版本")
    .replace(/演示\s*fallback/gi, "本地规则模式")
    .replace(/比赛包/g, "应用安装目录")
    .replace(/比赛现场/g, "实际环境")
    .replace(/评审演示/g, "业务评审")
    .replace(/演示数据/g, "业务数据")
    .replace(/演示闭环/g, "业务闭环")
    .replace(/演示页面/g, "工作区")
    .replace(/fallback/gi, "本地规则模式")
    .replace(/Demo/gi, "版本")
    .replace(/演示/g, "示例")
    .replace(/比赛/g, "产品")
    .replace(/\?{4,}/g, "未命名会议")
    .trim();
  return cleaned || "暂无内容";
}
function isPresentableMeeting(meeting: Meeting) { const value = cleanText(meeting.title); return value !== "未命名会议" && !/冒烟|测试会议/.test(value); }
function formatAuditTime(value: string) { const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }); }
function formatDecisionAge(value: string) { const elapsed = Math.max(0, Date.now() - new Date(value).getTime()); const minutes = Math.floor(elapsed / 60000); return minutes < 60 ? `等待 ${Math.max(1, minutes)} 分钟` : `等待 ${Math.floor(minutes / 60)} 小时`; }

const rootElement = document.getElementById("root")!;
const root = (window as typeof window & { __adsRoot?: ReturnType<typeof createRoot> }).__adsRoot ?? createRoot(rootElement);
(window as typeof window & { __adsRoot?: ReturnType<typeof createRoot> }).__adsRoot = root;
root.render(<StrictMode><App /></StrictMode>);
