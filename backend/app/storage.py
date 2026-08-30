import json
import os
import shutil
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from app.models import (
    AdsWorkspace,
    AdsWorkspacePayload,
    AgendaItem,
    AppSettings,
    MeetingSession,
    MeetingSummary,
    RecurrenceRule,
    MetricBaseline,
    ModelCallAudit,
    ModelConfig,
    SpeechJob,
    Task,
)


BACKEND_DIR = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("ADS_DB_PATH", BACKEND_DIR / "data" / "ads_agent.db"))
BACKUP_DIR = Path(os.getenv("ADS_BACKUP_DIR", BACKEND_DIR / "data" / "backups"))


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db() -> None:
    with closing(_connect()) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS meetings (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                scenario TEXT NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                meeting_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(meeting_id) REFERENCES meetings(id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS model_configs (
                provider_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                api_key TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS speech_jobs (
                id TEXT PRIMARY KEY,
                meeting_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(meeting_id) REFERENCES meetings(id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ads_workspaces (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS app_state (
                key TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS model_call_audits (
                id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS metric_baselines (
                id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.commit()


def create_ads_workspace(workspace_id: str, payload: AdsWorkspacePayload) -> AdsWorkspace:
    timestamp = _now()
    workspace = AdsWorkspace(
        id=workspace_id,
        created_at=timestamp,
        updated_at=timestamp,
        **payload.model_dump(),
    )
    with closing(_connect()) as connection:
        connection.execute(
            "INSERT INTO ads_workspaces VALUES (?, ?, ?, ?, ?)",
            (workspace.id, workspace.name, workspace.model_dump_json(), timestamp, timestamp),
        )
        connection.commit()
    return workspace


def save_ads_workspace(workspace_id: str, payload: AdsWorkspacePayload) -> AdsWorkspace | None:
    current = get_ads_workspace(workspace_id)
    if current is None:
        return None
    workspace = AdsWorkspace(
        id=workspace_id,
        created_at=current.created_at,
        updated_at=_now(),
        **payload.model_dump(),
    )
    with closing(_connect()) as connection:
        connection.execute(
            "UPDATE ads_workspaces SET name = ?, payload_json = ?, updated_at = ? WHERE id = ?",
            (workspace.name, workspace.model_dump_json(), workspace.updated_at, workspace.id),
        )
        connection.commit()
    return workspace


def get_ads_workspace(workspace_id: str) -> AdsWorkspace | None:
    with closing(_connect()) as connection:
        row = connection.execute(
            "SELECT payload_json FROM ads_workspaces WHERE id = ?", (workspace_id,)
        ).fetchone()
    return AdsWorkspace.model_validate_json(row["payload_json"]) if row else None


def list_ads_workspaces() -> list[AdsWorkspace]:
    with closing(_connect()) as connection:
        rows = connection.execute(
            "SELECT payload_json FROM ads_workspaces ORDER BY updated_at DESC"
        ).fetchall()
    return [AdsWorkspace.model_validate_json(row["payload_json"]) for row in rows]


def delete_ads_workspace(workspace_id: str) -> bool:
    with closing(_connect()) as connection:
        in_use = connection.execute(
            "SELECT COUNT(*) FROM meetings WHERE json_extract(payload_json, '$.workspace_id') = ?",
            (workspace_id,),
        ).fetchone()[0]
        if in_use:
            return False
        cursor = connection.execute("DELETE FROM ads_workspaces WHERE id = ?", (workspace_id,))
        connection.commit()
    return cursor.rowcount > 0


def set_ads_workspace_archived(workspace_id: str, archived: bool) -> AdsWorkspace | None:
    workspace = get_ads_workspace(workspace_id)
    if workspace is None:
        return None
    workspace.archived = archived
    workspace.updated_at = _now()
    with closing(_connect()) as connection:
        connection.execute(
            "UPDATE ads_workspaces SET payload_json = ?, updated_at = ? WHERE id = ?",
            (workspace.model_dump_json(), workspace.updated_at, workspace_id),
        )
        connection.commit()
    return workspace


def create_meeting(
    meeting_id: str,
    title: str,
    scenario: str,
    meeting_type: str,
    scheduled_at: str,
    end_at: str | None,
    duration_minutes: int,
    participants: list[str],
    objective: str,
    agenda_text: str,
    participation_mode: str,
    model_provider_id: str,
    workspace_id: str | None,
    agent_identity_id: str | None,
    authorization_rule_ids: list[str],
    auto_reply_enabled: bool,
    series_id: str | None = None,
    occurrence_index: int = 0,
    recurrence: RecurrenceRule | None = None,
    agenda: list[AgendaItem] | None = None,
) -> MeetingSession:
    timestamp = _now()
    meeting = MeetingSession(
        id=meeting_id,
        title=title,
        scenario=scenario,
        status="draft",
        meeting_status="draft",
        agent_session_state="not_started",
        meeting_type=meeting_type,
        scheduled_at=scheduled_at,
        end_at=end_at,
        duration_minutes=duration_minutes,
        participants=participants,
        objective=objective,
        agenda_text=agenda_text,
        participation_mode=participation_mode,
        model_provider_id=model_provider_id,
        workspace_id=workspace_id,
        agent_identity_id=agent_identity_id,
        authorization_rule_ids=authorization_rule_ids,
        auto_reply_enabled=auto_reply_enabled,
        series_id=series_id,
        occurrence_index=occurrence_index,
        recurrence=recurrence or RecurrenceRule(),
        agenda=agenda or [],
        created_at=timestamp,
        updated_at=timestamp,
    )
    with closing(_connect()) as connection:
        connection.execute(
            "INSERT INTO meetings VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                meeting.id,
                meeting.title,
                meeting.scenario,
                meeting.status,
                meeting.model_dump_json(),
                meeting.created_at,
                meeting.updated_at,
            ),
        )
        connection.commit()
    return meeting


def save_meeting(meeting: MeetingSession) -> MeetingSession:
    meeting.updated_at = _now()
    with closing(_connect()) as connection:
        connection.execute(
            """
            UPDATE meetings
            SET title = ?, scenario = ?, status = ?, payload_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                meeting.title,
                meeting.scenario,
                meeting.status,
                meeting.model_dump_json(),
                meeting.updated_at,
                meeting.id,
            ),
        )
        connection.commit()
    return meeting


def get_meeting(meeting_id: str) -> MeetingSession | None:
    with closing(_connect()) as connection:
        row = connection.execute(
            "SELECT payload_json FROM meetings WHERE id = ?", (meeting_id,)
        ).fetchone()
    if row is None:
        return None
    return MeetingSession.model_validate_json(row["payload_json"])


def list_meetings() -> list[MeetingSummary]:
    with closing(_connect()) as connection:
        rows = connection.execute(
            "SELECT payload_json FROM meetings ORDER BY updated_at DESC"
        ).fetchall()
    return [
        MeetingSummary.model_validate(MeetingSession.model_validate_json(row["payload_json"]).model_dump())
        for row in rows
    ]


def list_meeting_sessions() -> list[MeetingSession]:
    with closing(_connect()) as connection:
        rows = connection.execute(
            "SELECT payload_json FROM meetings ORDER BY updated_at DESC"
        ).fetchall()
    return [MeetingSession.model_validate_json(row["payload_json"]) for row in rows]


def delete_meeting(meeting_id: str) -> bool:
    with closing(_connect()) as connection:
        connection.execute("DELETE FROM speech_jobs WHERE meeting_id = ?", (meeting_id,))
        connection.execute("DELETE FROM tasks WHERE meeting_id = ?", (meeting_id,))
        cursor = connection.execute("DELETE FROM meetings WHERE id = ?", (meeting_id,))
        connection.commit()
    return cursor.rowcount > 0


def persist_tasks(meeting_id: str, tasks: list[Task]) -> None:
    timestamp = _now()
    with closing(_connect()) as connection:
        for task in tasks:
            connection.execute(
                "INSERT OR REPLACE INTO tasks VALUES (?, ?, ?, ?)",
                (task.id, meeting_id, task.model_dump_json(), timestamp),
            )
        connection.commit()


def complete_meeting_with_tasks(meeting: MeetingSession, tasks: list[Task]) -> MeetingSession:
    """Atomically persist tasks and the completed meeting snapshot."""
    timestamp = _now()
    meeting.updated_at = timestamp
    with closing(_connect()) as connection:
        try:
            for task in tasks:
                connection.execute(
                    "INSERT INTO tasks VALUES (?, ?, ?, ?)",
                    (task.id, meeting.id, task.model_dump_json(), timestamp),
                )
            connection.execute(
                """
                UPDATE meetings
                SET title = ?, scenario = ?, status = ?, payload_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    meeting.title,
                    meeting.scenario,
                    meeting.status,
                    meeting.model_dump_json(),
                    timestamp,
                    meeting.id,
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return meeting


def list_persisted_tasks() -> list[Task]:
    with closing(_connect()) as connection:
        rows = connection.execute(
            "SELECT payload_json FROM tasks ORDER BY created_at DESC"
        ).fetchall()
    return [Task.model_validate(json.loads(row["payload_json"])) for row in rows]


def upsert_model_config(config: ModelConfig, api_key: str = "") -> ModelConfig:
    timestamp = _now()
    with closing(_connect()) as connection:
        if config.is_default:
            rows = connection.execute("SELECT payload_json, api_key FROM model_configs").fetchall()
            for row in rows:
                current = ModelConfig.model_validate_json(row["payload_json"])
                if current.provider_id != config.provider_id and current.is_default:
                    current.is_default = False
                    connection.execute(
                        "UPDATE model_configs SET payload_json = ?, updated_at = ? WHERE provider_id = ?",
                        (current.model_dump_json(), timestamp, current.provider_id),
                    )
        existing = connection.execute(
            "SELECT api_key FROM model_configs WHERE provider_id = ?", (config.provider_id,)
        ).fetchone()
        stored_key = api_key if api_key else (existing["api_key"] if existing else "")
        connection.execute(
            """
            INSERT INTO model_configs (provider_id, payload_json, api_key, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(provider_id) DO UPDATE SET
                payload_json = excluded.payload_json,
                api_key = excluded.api_key,
                updated_at = excluded.updated_at
            """,
            (config.provider_id, config.model_dump_json(), stored_key, timestamp),
        )
        connection.commit()
    return config


def list_model_configs() -> list[ModelConfig]:
    with closing(_connect()) as connection:
        rows = connection.execute("SELECT payload_json FROM model_configs ORDER BY provider_id").fetchall()
    return [ModelConfig.model_validate_json(row["payload_json"]) for row in rows]


def get_model_secret(provider_id: str) -> str:
    with closing(_connect()) as connection:
        row = connection.execute(
            "SELECT api_key FROM model_configs WHERE provider_id = ?", (provider_id,)
        ).fetchone()
    return row["api_key"] if row else ""


def save_speech_job(job: SpeechJob) -> SpeechJob:
    job.updated_at = _now()
    with closing(_connect()) as connection:
        connection.execute(
            """
            INSERT INTO speech_jobs (id, meeting_id, payload_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                meeting_id = excluded.meeting_id,
                payload_json = excluded.payload_json,
                updated_at = excluded.updated_at
            """,
            (job.id, job.meeting_id, job.model_dump_json(), job.created_at, job.updated_at),
        )
        connection.commit()
    return job


def get_speech_job(job_id: str) -> SpeechJob | None:
    with closing(_connect()) as connection:
        row = connection.execute(
            "SELECT payload_json FROM speech_jobs WHERE id = ?", (job_id,)
        ).fetchone()
    return SpeechJob.model_validate_json(row["payload_json"]) if row else None


def list_speech_jobs(meeting_id: str) -> list[SpeechJob]:
    with closing(_connect()) as connection:
        rows = connection.execute(
            "SELECT payload_json FROM speech_jobs WHERE meeting_id = ? ORDER BY created_at DESC",
            (meeting_id,),
        ).fetchall()
    return [SpeechJob.model_validate_json(row["payload_json"]) for row in rows]


def list_all_speech_jobs() -> list[SpeechJob]:
    with closing(_connect()) as connection:
        rows = connection.execute(
            "SELECT payload_json FROM speech_jobs ORDER BY created_at DESC"
        ).fetchall()
    return [SpeechJob.model_validate_json(row["payload_json"]) for row in rows]


def get_app_settings() -> AppSettings:
    with closing(_connect()) as connection:
        row = connection.execute(
            "SELECT payload_json FROM app_state WHERE key = 'settings'"
        ).fetchone()
    return AppSettings.model_validate_json(row["payload_json"]) if row else AppSettings()


def has_app_settings() -> bool:
    with closing(_connect()) as connection:
        return connection.execute("SELECT 1 FROM app_state WHERE key = 'settings'").fetchone() is not None


def save_app_settings(settings: AppSettings) -> AppSettings:
    timestamp = _now()
    with closing(_connect()) as connection:
        connection.execute(
            """
            INSERT INTO app_state (key, payload_json, updated_at) VALUES ('settings', ?, ?)
            ON CONFLICT(key) DO UPDATE SET payload_json = excluded.payload_json, updated_at = excluded.updated_at
            """,
            (settings.model_dump_json(), timestamp),
        )
        connection.commit()
    return settings


def get_microphone_owner() -> str | None:
    with closing(_connect()) as connection:
        row = connection.execute(
            "SELECT payload_json FROM app_state WHERE key = 'microphone_owner'"
        ).fetchone()
    if not row:
        return None
    return json.loads(row["payload_json"]).get("meeting_id")


def set_microphone_owner(meeting_id: str | None) -> str | None:
    timestamp = _now()
    with closing(_connect()) as connection:
        if meeting_id is None:
            connection.execute("DELETE FROM app_state WHERE key = 'microphone_owner'")
        else:
            connection.execute(
                """
                INSERT INTO app_state (key, payload_json, updated_at) VALUES ('microphone_owner', ?, ?)
                ON CONFLICT(key) DO UPDATE SET payload_json = excluded.payload_json, updated_at = excluded.updated_at
                """,
                (json.dumps({"meeting_id": meeting_id}, ensure_ascii=False), timestamp),
            )
        connection.commit()
    return meeting_id


def save_model_call_audit(audit: ModelCallAudit) -> ModelCallAudit:
    with closing(_connect()) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO model_call_audits VALUES (?, ?, ?)",
            (audit.id, audit.model_dump_json(), audit.created_at),
        )
        connection.commit()
    return audit


def list_model_call_audits(limit: int = 100) -> list[ModelCallAudit]:
    with closing(_connect()) as connection:
        rows = connection.execute(
            "SELECT payload_json FROM model_call_audits ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [ModelCallAudit.model_validate_json(row["payload_json"]) for row in rows]


def save_metric_baseline(baseline: MetricBaseline) -> MetricBaseline:
    with closing(_connect()) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO metric_baselines VALUES (?, ?, ?)",
            (baseline.id, baseline.model_dump_json(), _now()),
        )
        connection.commit()
    return baseline


def list_metric_baselines() -> list[MetricBaseline]:
    with closing(_connect()) as connection:
        rows = connection.execute(
            "SELECT payload_json FROM metric_baselines ORDER BY created_at DESC"
        ).fetchall()
    return [MetricBaseline.model_validate_json(row["payload_json"]) for row in rows]


def data_counts() -> dict[str, int]:
    with closing(_connect()) as connection:
        return {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("meetings", "ads_workspaces", "speech_jobs")
        }


def create_backup() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    target = BACKUP_DIR / f"ads-backup-{timestamp}.db"
    with closing(_connect()) as source, closing(sqlite3.connect(target)) as destination:
        source.backup(destination)
    return target


def list_backups() -> list[Path]:
    if not BACKUP_DIR.exists():
        return []
    return sorted(BACKUP_DIR.glob("ads-backup-*.db"), key=lambda item: item.stat().st_mtime, reverse=True)


def restore_backup(filename: str) -> None:
    source = (BACKUP_DIR / filename).resolve()
    backup_root = BACKUP_DIR.resolve()
    if source.parent != backup_root or not source.is_file():
        raise FileNotFoundError(filename)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    restore_temp = DB_PATH.with_suffix(".restore.tmp")
    shutil.copy2(source, restore_temp)
    os.replace(restore_temp, DB_PATH)


def reset_product_data() -> None:
    with closing(_connect()) as connection:
        for table in (
            "speech_jobs",
            "tasks",
            "meetings",
            "ads_workspaces",
            "model_call_audits",
            "metric_baselines",
            "app_state",
        ):
            connection.execute(f"DELETE FROM {table}")
        connection.commit()


def delete_speech_job(job_id: str) -> bool:
    with closing(_connect()) as connection:
        cursor = connection.execute("DELETE FROM speech_jobs WHERE id = ?", (job_id,))
        connection.commit()
    return cursor.rowcount > 0
