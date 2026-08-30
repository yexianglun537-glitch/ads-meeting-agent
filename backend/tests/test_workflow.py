import os
import shutil
import tempfile
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient


TEST_DB_PATH = tempfile.mktemp(suffix=".db")
TEST_AUDIO_DIR = tempfile.mkdtemp(prefix="ads-audio-tests-")
os.environ["ADS_DB_PATH"] = TEST_DB_PATH
os.environ["ADS_AUDIO_DIR"] = TEST_AUDIO_DIR

from app.main import app, _process_speech_job, cleanup_expired_audio_assets, expand_occurrence_starts, recover_interrupted_speech_jobs  # noqa: E402
from app.diarization import SpeakerTurn  # noqa: E402
from app.models import MeetingSession, RecurrenceRule, SpeechJob  # noqa: E402
from app.storage import get_speech_job, save_speech_job  # noqa: E402


class WorkflowTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()
        cls.initial_setup = cls.client.get("/api/setup").json()
        cls.initial_workspaces = cls.client.get("/api/workspaces").json()
        onboarded = cls.client.post(
            "/api/onboarding",
            json={
                "identity": {"id": "p_zhang", "name": "张伟", "role": "项目负责人"},
                "workspace_name": "测试工作区",
                "workspace_description": "自动化测试使用的真实空白起点",
            },
        ).json()
        cls.onboarded = onboarded
        cls.workspace_id = onboarded["workspace"]["id"]
        cls.client.put(
            f"/api/workspaces/{cls.workspace_id}",
            json={
                "name": "测试工作区",
                "description": "自动化测试使用的业务数据",
                "people": [
                    {"id": "p_zhang", "name": "张伟", "role": "项目负责人"},
                    {"id": "p_li", "name": "李娜", "role": "前端负责人"},
                    {"id": "p_wang", "name": "王强", "role": "后端负责人"},
                    {"id": "p_chen", "name": "陈敏", "role": "测试负责人"},
                ],
                "objectives": [{"id": "obj_product", "title": "交付产品版本", "progress": 60, "metric": "闭环率 100%", "risk": "交付时间"}],
                "tasks": [],
                "authorization_rules": [{"id": "auth_default", "person_id": "p_zhang", "scope": "允许说明既有进度", "allowed_actions": ["provide_info"], "escalation_triggers": ["变更范围"]}],
            },
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_context.__exit__(None, None, None)
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)
        shutil.rmtree(TEST_AUDIO_DIR, ignore_errors=True)

    def create_prepared_meeting(self, title: str, auto_reply_enabled: bool = False) -> dict:
        meeting = self.client.post(
            "/api/meetings",
            json={
                "title": title,
                "scenario": "项目周例会",
                "participation_mode": "delegate",
                "workspace_id": self.workspace_id,
                "agent_identity_id": "p_zhang",
                "authorization_rule_ids": ["auth_default"],
                "auto_reply_enabled": auto_reply_enabled,
            },
        ).json()
        response = self.client.post(f"/api/meetings/{meeting['id']}/prepare")
        self.assertEqual(response.status_code, 200)
        started = self.client.post(
            f"/api/meetings/{meeting['id']}/agent/control",
            json={"action": "start"},
        )
        self.assertEqual(started.status_code, 200)
        return started.json()

    def test_fresh_install_requires_onboarding_without_business_seed(self) -> None:
        self.assertTrue(self.initial_setup["requires_onboarding"])
        self.assertEqual(self.initial_workspaces, [])
        identity = next(item for item in self.onboarded["settings"]["identities"] if item["id"] == "p_zhang")
        self.assertIn("项目负责人", identity["description"])
        self.assertIn("自动化测试使用的真实空白起点", identity["description"])
        self.assertEqual([item["id"] for item in self.onboarded["workspace"]["people"]], ["p_zhang"])

    def test_full_ads_objects_round_trip(self) -> None:
        created = self.client.post(
            "/api/workspaces",
            json={
                "name": "全量对象工作区",
                "projects": [{"id": "prj_1", "name": "桌面产品", "owner_id": "p_zhang"}],
                "metrics": [{"id": "met_1", "name": "闭环率", "current_value": 80, "target_value": 100, "unit": "%"}],
                "risks": [{"id": "risk_1", "title": "交付延期", "impact": "影响发布"}],
                "policies": [{"id": "pol_1", "title": "变更制度", "content": "范围变更必须升级本人"}],
                "historical_stances": [{"id": "stance_1", "person_id": "p_zhang", "topic": "发布范围", "stance": "优先稳定性"}],
            },
        )
        self.assertEqual(created.status_code, 200)
        payload = created.json()
        self.assertEqual(payload["projects"][0]["name"], "桌面产品")
        self.assertEqual(payload["policies"][0]["title"], "变更制度")

        payload["projects"][0]["status"] = "已完成"
        saved = self.client.put(
            f"/api/workspaces/{payload['id']}",
            json={key: payload[key] for key in [
                "name", "description", "people", "projects", "objectives", "metrics",
                "risks", "tasks", "policies", "historical_stances", "authorization_rules",
            ]},
        )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["projects"][0]["status"], "已完成")

    def test_app_settings_persist_audio_retention(self) -> None:
        current = self.client.get("/api/settings")
        self.assertEqual(current.status_code, 200)
        self.assertEqual(current.json()["audio_retention_days"], 0)

        saved = self.client.put("/api/settings", json={"audio_retention_days": 30})
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["audio_retention_days"], 30)
        self.assertEqual(self.client.get("/api/settings").json()["audio_retention_days"], 30)

        invalid = self.client.put("/api/settings", json={"audio_retention_days": 7})
        self.assertEqual(invalid.status_code, 422)

    def test_app_settings_create_and_switch_identity_in_active_workspace(self) -> None:
        created = self.client.put(
            "/api/settings",
            json={
                "identity": {"id": "p_new_identity", "name": "赵敏", "role": "运营负责人"},
                "active_identity_id": "p_new_identity",
            },
        )
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["active_identity_id"], "p_new_identity")
        self.assertTrue(any(item["id"] == "p_new_identity" for item in created.json()["identities"]))

        workspace = self.client.get(f"/api/workspaces/{self.workspace_id}").json()
        self.assertTrue(any(item["id"] == "p_new_identity" for item in workspace["people"]))

        switched = self.client.put("/api/settings", json={"active_identity_id": "p_zhang"})
        self.assertEqual(switched.status_code, 200)
        self.assertEqual(switched.json()["active_identity_id"], "p_zhang")

        unknown = self.client.put("/api/settings", json={"active_identity_id": "p_missing"})
        self.assertEqual(unknown.status_code, 422)

    def test_provider_registry_and_installation(self) -> None:
        registry = self.client.get("/api/providers").json()
        vendor_ids = {item["vendor_id"] for item in registry}
        self.assertTrue({"deepseek", "qwen", "doubao", "moonshot", "zhipu", "hunyuan", "spark", "qianfan", "minimax", "stepfun", "baichuan", "yi"}.issubset(vendor_ids))
        installed = self.client.post("/api/providers/qwen/install")
        self.assertEqual(installed.status_code, 200)
        self.assertEqual(installed.json()["vendor_id"], "qwen")

    def test_delegate_meeting_requires_explicit_identity_and_authorization(self) -> None:
        base = {
            "title": "明确代理授权测试",
            "participation_mode": "delegate",
            "workspace_id": self.workspace_id,
            "participants": ["张伟", "李娜"],
        }
        missing_identity = self.client.post(
            "/api/meetings",
            json={**base, "authorization_rule_ids": ["auth_default"]},
        )
        self.assertEqual(missing_identity.status_code, 422)

        missing_authorization = self.client.post(
            "/api/meetings",
            json={**base, "agent_identity_id": "p_zhang"},
        )
        self.assertEqual(missing_authorization.status_code, 422)

        invalid_identity = self.client.post(
            "/api/meetings",
            json={
                **base,
                "agent_identity_id": "unknown_person",
                "authorization_rule_ids": ["auth_default"],
            },
        )
        self.assertEqual(invalid_identity.status_code, 422)

        invalid_authorization = self.client.post(
            "/api/meetings",
            json={
                **base,
                "agent_identity_id": "p_zhang",
                "authorization_rule_ids": ["unknown_rule"],
            },
        )
        self.assertEqual(invalid_authorization.status_code, 422)

        created = self.client.post(
            "/api/meetings",
            json={
                **base,
                "agent_identity_id": "p_zhang",
                "authorization_rule_ids": ["auth_default"],
                "auto_reply_enabled": True,
            },
        )
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["agent_identity_id"], "p_zhang")
        self.assertEqual(created.json()["authorization_rule_ids"], ["auth_default"])
        self.assertTrue(created.json()["auto_reply_enabled"])
        self.assertEqual(created.json()["participants"], ["张伟", "李娜"])

        participants_must_be_a_list = self.client.post(
            "/api/meetings",
            json={**base, "participants": "张伟、李娜"},
        )
        self.assertEqual(participants_must_be_a_list.status_code, 422)

    def test_biweekly_recurrence_stops_at_end_date(self) -> None:
        created = self.client.post(
            "/api/meetings",
            json={
                "title": "双周产品会",
                "scheduled_at": "2026-09-01 09:00",
                "end_at": "2026-09-01 10:00",
                "workspace_id": self.workspace_id,
                "recurrence": {"frequency": "biweekly", "end_date": "2026-10-01"},
            },
        )
        self.assertEqual(created.status_code, 200)
        series_id = created.json()["series_id"]
        occurrences = [
            item for item in self.client.get("/api/meetings").json()
            if item["series_id"] == series_id
        ]
        self.assertEqual(
            sorted(item["scheduled_at"] for item in occurrences),
            ["2026-09-01 09:00", "2026-09-15 09:00", "2026-09-29 09:00"],
        )
        self.assertEqual(sorted(item["occurrence_index"] for item in occurrences), [0, 1, 2])

    def test_monthly_recurrence_preserves_original_day_anchor(self) -> None:
        created = self.client.post(
            "/api/meetings",
            json={
                "title": "月末复盘会",
                "scheduled_at": "2026-01-31 09:00",
                "end_at": "2026-01-31 10:00",
                "workspace_id": self.workspace_id,
                "recurrence": {"frequency": "monthly", "end_date": "2026-03-31"},
            },
        )
        self.assertEqual(created.status_code, 200)
        series_id = created.json()["series_id"]
        occurrences = [
            item for item in self.client.get("/api/meetings").json()
            if item["series_id"] == series_id
        ]
        self.assertEqual(
            sorted(item["scheduled_at"] for item in occurrences),
            ["2026-01-31 09:00", "2026-02-28 09:00", "2026-03-31 09:00"],
        )

    def test_recurrence_requires_a_valid_end_date_within_one_year(self) -> None:
        base = {
            "title": "循环规则校验",
            "scheduled_at": "2026-09-01 09:00",
            "workspace_id": self.workspace_id,
        }
        missing_end = self.client.post(
            "/api/meetings",
            json={**base, "recurrence": {"frequency": "weekly"}},
        )
        before_start = self.client.post(
            "/api/meetings",
            json={**base, "recurrence": {"frequency": "weekly", "end_date": "2026-08-31"}},
        )
        over_one_year = self.client.post(
            "/api/meetings",
            json={**base, "recurrence": {"frequency": "weekly", "end_date": "2027-09-02"}},
        )
        self.assertEqual(missing_end.status_code, 422)
        self.assertEqual(before_start.status_code, 422)
        self.assertEqual(over_one_year.status_code, 422)

    def test_recurrence_expansion_enforces_occurrence_limit(self) -> None:
        with self.assertRaisesRegex(HTTPException, "最多生成 2 场会议"):
            expand_occurrence_starts(
                "2026-09-01 09:00",
                RecurrenceRule(frequency="weekly", end_date="2026-09-30"),
                limit=2,
            )

    def test_old_meeting_payload_defaults_to_non_recurring(self) -> None:
        created = self.client.post(
            "/api/meetings",
            json={"title": "旧会议兼容", "workspace_id": self.workspace_id},
        ).json()
        created.pop("series_id")
        created.pop("occurrence_index")
        created.pop("recurrence")
        restored = MeetingSession.model_validate(created)
        self.assertIsNone(restored.series_id)
        self.assertEqual(restored.occurrence_index, 0)
        self.assertEqual(restored.recurrence.frequency, "none")

    def test_agenda_draft_uses_duration_and_falls_back_locally(self) -> None:
        response = self.client.post(
            "/api/agenda/draft",
            json={
                "content": "确认需求范围；评估开发风险；明确负责人",
                "duration_minutes": 60,
                "workspace_id": self.workspace_id,
                "model_provider_id": "mock",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["mode"], "local_rules")
        self.assertEqual(sum(item["duration_minutes"] for item in payload["agenda"]), 60)
        self.assertIn("确认需求范围", payload["agenda_text"])
        audits = self.client.get("/api/model-audits").json()
        self.assertTrue(any(item["operation"] == "agenda_draft" and item["status"] == "fallback" for item in audits))

    def test_agenda_draft_bad_online_response_falls_back_without_failing(self) -> None:
        online_response = Mock()
        online_response.json.return_value = {"choices": [{"message": {"content": "not-json"}}]}
        with (
            patch.dict(os.environ, {"USE_MOCK_AI": "false"}),
            patch("app.ai._provider_runtime", return_value=("configured-key", "https://example.invalid/v1", "configured-model")),
            patch("app.ai.httpx.AsyncClient.post", new_callable=AsyncMock, return_value=online_response),
        ):
            response = self.client.post(
                "/api/agenda/draft",
                json={
                    "content": "确认接口；评估风险",
                    "duration_minutes": 45,
                    "workspace_id": self.workspace_id,
                    "model_provider_id": "deepseek",
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mode"], "local_rules")
        self.assertEqual(sum(item["duration_minutes"] for item in response.json()["agenda"]), 45)

    def test_agenda_draft_uses_valid_online_structured_response(self) -> None:
        online_response = Mock()
        online_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": "{\"agenda_text\":\"确认接口\\n评估风险\",\"agenda\":[{\"topic\":\"确认接口\",\"context\":\"核对清单\",\"suggested_question\":\"是否完整？\",\"duration_minutes\":20},{\"topic\":\"评估风险\",\"context\":\"识别阻塞\",\"suggested_question\":\"如何处理？\",\"duration_minutes\":25}]}"
                }
            }]
        }
        with (
            patch.dict(os.environ, {"USE_MOCK_AI": "false"}),
            patch("app.ai._provider_runtime", return_value=("configured-key", "https://example.invalid/v1", "configured-model")),
            patch("app.ai.httpx.AsyncClient.post", new_callable=AsyncMock, return_value=online_response),
        ):
            response = self.client.post(
                "/api/agenda/draft",
                json={
                    "content": "确认接口；评估风险",
                    "duration_minutes": 45,
                    "workspace_id": self.workspace_id,
                    "model_provider_id": "deepseek",
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mode"], "live")
        audits = self.client.get("/api/model-audits").json()
        self.assertTrue(any(item["operation"] == "agenda_draft" and item["status"] == "success" for item in audits))

    def test_prepare_meeting_preserves_confirmed_structured_agenda(self) -> None:
        agenda = [
            {"topic": "确认范围", "context": "核对需求边界", "suggested_question": "范围是否一致？", "duration_minutes": 20},
            {"topic": "评估风险", "context": "识别阻塞项", "suggested_question": "最大风险是什么？", "duration_minutes": 25},
        ]
        created = self.client.post(
            "/api/meetings",
            json={
                "title": "结构化议程复用",
                "workspace_id": self.workspace_id,
                "objective": "确认需求范围并评估开发风险",
                "agenda_text": "确认范围\n评估风险",
                "agenda": agenda,
            },
        )
        self.assertEqual(created.status_code, 200)
        prepared = self.client.post(f"/api/meetings/{created.json()['id']}/prepare")
        self.assertEqual(prepared.status_code, 200)
        self.assertEqual(prepared.json()["agenda"], agenda)
        self.assertIn("确认需求范围并评估开发风险", prepared.json()["pre_meeting_brief"])

    def test_meeting_update_rejects_started_time_change_but_keeps_content_data(self) -> None:
        meeting = self.create_prepared_meeting("编辑边界")
        from app.storage import get_meeting, save_meeting

        current = get_meeting(meeting["id"])
        self.assertIsNotNone(current)
        current.transcript = "已保存的会议转写"
        save_meeting(current)

        rejected = self.client.patch(
            f"/api/meetings/{meeting['id']}",
            json={"scheduled_at": "2026-10-01 09:00"},
        )
        updated = self.client.patch(
            f"/api/meetings/{meeting['id']}",
            json={"objective": "更新后的会议内容"},
        )
        self.assertEqual(rejected.status_code, 409)
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["objective"], "更新后的会议内容")
        self.assertEqual(updated.json()["transcript"], "已保存的会议转写")

    def test_manual_agenda_is_not_replaced_without_confirmation(self) -> None:
        meeting = self.client.post(
            "/api/meetings",
            json={"title": "人工议程保护", "workspace_id": self.workspace_id},
        ).json()
        self.client.post(f"/api/meetings/{meeting['id']}/prepare")
        agenda = [{
            "topic": "人工议题",
            "context": "保留",
            "suggested_question": "是否确认？",
            "duration_minutes": 45,
        }]
        saved = self.client.patch(f"/api/meetings/{meeting['id']}/agenda", json={"agenda": agenda})
        self.assertEqual(saved.status_code, 200)
        self.assertTrue(saved.json()["agenda_edited"])

        blocked = self.client.post(f"/api/meetings/{meeting['id']}/prepare")
        self.assertEqual(blocked.status_code, 409)
        replaced = self.client.post(f"/api/meetings/{meeting['id']}/prepare?replace_manual=true")
        self.assertEqual(replaced.status_code, 200)
        self.assertFalse(replaced.json()["agenda_edited"])
        self.assertNotEqual(replaced.json()["agenda"][0]["topic"], "人工议题")

    def test_meeting_update_future_scope_changes_only_current_and_later_occurrences(self) -> None:
        created = self.client.post(
            "/api/meetings",
            json={
                "title": "系列编辑",
                "scheduled_at": "2026-09-01 09:00",
                "end_at": "2026-09-01 10:00",
                "workspace_id": self.workspace_id,
                "recurrence": {"frequency": "weekly", "end_date": "2026-09-22"},
            },
        ).json()
        series = sorted(
            (
                item for item in self.client.get("/api/meetings").json()
                if item["series_id"] == created["series_id"]
            ),
            key=lambda item: item["occurrence_index"],
        )
        updated = self.client.patch(
            f"/api/meetings/{series[1]['id']}?scope=future",
            json={"objective": "系列后续统一内容"},
        )
        self.assertEqual(updated.status_code, 200)
        details = [self.client.get(f"/api/meetings/{item['id']}").json() for item in series]
        self.assertNotEqual(details[0]["objective"], "系列后续统一内容")
        self.assertTrue(all(item["objective"] == "系列后续统一内容" for item in details[1:]))

    def test_delete_future_removes_current_and_later_occurrences_only(self) -> None:
        created = self.client.post(
            "/api/meetings",
            json={
                "title": "产品周会",
                "scheduled_at": "2026-09-01 09:00",
                "end_at": "2026-09-01 10:00",
                "workspace_id": self.workspace_id,
                "recurrence": {"frequency": "weekly", "end_date": "2026-09-22"},
            },
        )
        self.assertEqual(created.status_code, 200)
        series_id = created.json()["series_id"]
        occurrences = sorted(
            (
                item for item in self.client.get("/api/meetings").json()
                if item["series_id"] == series_id
            ),
            key=lambda item: item["occurrence_index"],
        )
        self.assertEqual(len(occurrences), 4)

        deleted_single = self.client.delete(f"/api/meetings/{occurrences[2]['id']}?scope=single")
        self.assertEqual(deleted_single.status_code, 200)
        after_single = {item["id"] for item in self.client.get("/api/meetings").json()}
        self.assertNotIn(occurrences[2]["id"], after_single)
        self.assertTrue(all(occurrences[index]["id"] in after_single for index in (0, 1, 3)))

        deleted = self.client.delete(f"/api/meetings/{occurrences[1]['id']}?scope=future")
        self.assertEqual(deleted.status_code, 200)
        remaining_ids = {item["id"] for item in self.client.get("/api/meetings").json()}
        self.assertIn(occurrences[0]["id"], remaining_ids)
        self.assertTrue(all(item["id"] not in remaining_ids for item in occurrences[1:]))

    def test_microphone_has_single_meeting_owner(self) -> None:
        first = self.create_prepared_meeting("麦克风会议 A")
        second = self.create_prepared_meeting("麦克风会议 B")
        acquired = self.client.post(f"/api/meetings/{first['id']}/microphone", json={"action": "acquire"})
        self.assertEqual(acquired.status_code, 200)
        blocked = self.client.post(f"/api/meetings/{second['id']}/microphone", json={"action": "acquire"})
        self.assertEqual(blocked.status_code, 409)
        self.client.post(f"/api/meetings/{first['id']}/microphone", json={"action": "release"})
        acquired_second = self.client.post(f"/api/meetings/{second['id']}/microphone", json={"action": "acquire"})
        self.assertEqual(acquired_second.status_code, 200)
        self.client.post(f"/api/meetings/{second['id']}/microphone", json={"action": "release"})

    def test_agent_question_uses_backend_and_creates_audit(self) -> None:
        meeting = self.create_prepared_meeting("智能体问答测试")
        online_response = Mock()
        online_response.json.return_value = {
            "choices": [{"message": {"content": "不应调用的在线回答"}}]
        }
        with (
            patch.dict(os.environ, {"USE_MOCK_AI": "true"}),
            patch(
                "app.ai._provider_runtime",
                return_value=("configured-key", "https://example.invalid/v1", "configured-model"),
            ),
            patch(
                "app.ai.httpx.AsyncClient.post",
                new_callable=AsyncMock,
                return_value=online_response,
            ) as online_post,
        ):
            response = self.client.post(
                f"/api/meetings/{meeting['id']}/agent/ask",
                json={"question": "当前目标进度是多少？"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn("交付产品版本", response.json()["answer"])
        self.assertEqual(response.json()["mode"], "local_rules")
        online_post.assert_not_awaited()
        audits = self.client.get("/api/model-audits").json()
        self.assertTrue(any(item["operation"] == "agent_question" for item in audits))

    def test_auto_reply_records_sent_state_and_authorization(self) -> None:
        meeting = self.client.post(
            "/api/meetings",
            json={
                "title": "自动回复测试",
                "participation_mode": "delegate",
                "workspace_id": self.workspace_id,
                "agent_identity_id": "p_zhang",
                "authorization_rule_ids": ["auth_default"],
                "auto_reply_enabled": True,
            },
        ).json()
        self.client.post(f"/api/meetings/{meeting['id']}/prepare")
        self.client.post(f"/api/meetings/{meeting['id']}/agent/control", json={"action": "start"})
        analyzed = self.client.post(
            f"/api/meetings/{meeting['id']}/analyze",
            json={"transcript": "李娜：请说明当前目标进度。"},
        ).json()
        self.assertTrue(any(item["decision"] == "sent" for item in analyzed["sent_agent_replies"]))
        self.assertEqual(analyzed["sent_agent_replies"][0]["authorization_rule_ids"], ["auth_default"])

    def test_information_question_does_not_create_decision_or_action_item(self) -> None:
        meeting = self.create_prepared_meeting("信息询问不产生成果", auto_reply_enabled=True)
        analyzed = self.client.post(
            f"/api/meetings/{meeting['id']}/analyze",
            json={"transcript": "李娜：请说明当前产品目标进度和已经登记的风险。"},
        )

        self.assertEqual(analyzed.status_code, 200)
        result = analyzed.json()
        self.assertEqual(result["analysis"]["decisions"], [])
        self.assertEqual(result["analysis"]["action_items"], [])

    def test_information_question_reply_uses_ads_progress_and_risk(self) -> None:
        meeting = self.create_prepared_meeting("信息询问引用 ADS", auto_reply_enabled=True)
        analyzed = self.client.post(
            f"/api/meetings/{meeting['id']}/analyze",
            json={"transcript": "李娜：请说明当前产品目标进度和已经登记的风险。"},
        )

        self.assertEqual(analyzed.status_code, 200)
        replies = analyzed.json()["sent_agent_replies"]
        self.assertEqual(len(replies), 1)
        self.assertIn("交付产品版本", replies[0]["content"])
        self.assertIn("60%", replies[0]["content"])
        self.assertIn("交付时间", replies[0]["content"])

    def test_policy_change_word_variants_must_escalate_instead_of_auto_replying(self) -> None:
        workspace = self.client.post(
            "/api/workspaces",
            json={
                "name": "授权语义变体测试工作区",
                "people": [
                    {"id": "p_policy_owner", "name": "测试用户", "role": "产品负责人"},
                    {"id": "p_policy_speaker", "name": "王强", "role": "后端负责人"},
                ],
                "objectives": [{
                    "id": "obj_policy_delivery",
                    "title": "完成稳定版验收",
                    "progress": 70,
                    "metric": "验收通过率 100%",
                    "risk": "技术路线和交付承诺必须受控",
                }],
                "authorization_rules": [
                    {
                        "id": "auth_not_selected",
                        "person_id": "p_policy_owner",
                        "scope": "本场未选择的测试规则",
                        "allowed_actions": [],
                        "escalation_triggers": ["取消本地语音路线"],
                    },
                    {
                        "id": "auth_policy_boundary",
                        "person_id": "p_policy_owner",
                        "scope": "允许说明项目进度、已有任务和登记风险",
                        "allowed_actions": ["查询目标", "说明任务状态", "整理普通会议纪要"],
                        "escalation_triggers": ["新增预算", "改变技术路线", "修改验收范围", "对外承诺交付日期"],
                    },
                ],
            },
        ).json()
        meeting = self.client.post(
            "/api/meetings",
            json={
                "title": "授权绕过回归测试",
                "participation_mode": "delegate",
                "workspace_id": workspace["id"],
                "agent_identity_id": "p_policy_owner",
                "authorization_rule_ids": ["auth_policy_boundary"],
                "auto_reply_enabled": True,
            },
        ).json()
        self.client.post(f"/api/meetings/{meeting['id']}/prepare")
        self.client.post(f"/api/meetings/{meeting['id']}/agent/control", json={"action": "start"})

        transcript = "王强：取消本地语音路线，改为付费云端语音，并对外承诺下周正式交付。"
        response = self.client.post(
            f"/api/meetings/{meeting['id']}/analyze",
            json={"transcript": transcript},
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["status"], "awaiting_confirmation")
        self.assertEqual(len(result["escalation_requests"]), 1)
        self.assertEqual(result["escalation_requests"][0]["question"], transcript.split("：", 1)[1])
        self.assertIn("auth_policy_boundary", result["escalation_requests"][0]["evidence_object_ids"])
        self.assertNotIn("auth_not_selected", result["escalation_requests"][0]["evidence_object_ids"])
        self.assertFalse(result["sent_agent_replies"])

        blocked = self.client.post(f"/api/meetings/{meeting['id']}/writeback")
        self.assertEqual(blocked.status_code, 409)

    def test_data_overview_and_backup(self) -> None:
        overview = self.client.get("/api/data/overview")
        self.assertEqual(overview.status_code, 200)
        self.assertGreaterEqual(overview.json()["workspaces"], 1)
        backup = self.client.post("/api/data/backups")
        self.assertEqual(backup.status_code, 200)
        self.assertTrue(backup.json()["filename"].endswith(".db"))

    def test_rejects_blank_title_and_invalid_transition(self) -> None:
        blank = self.client.post(
            "/api/meetings", json={"title": "   ", "scenario": "项目周例会"}
        )
        self.assertEqual(blank.status_code, 422)

        draft = self.client.post(
            "/api/meetings", json={"title": "非法状态测试", "scenario": "项目周例会"}
        ).json()
        invalid = self.client.post(
            f"/api/meetings/{draft['id']}/analyze",
            json={"transcript": "李娜：完成前端页面并提交验收。"},
        )
        self.assertEqual(invalid.status_code, 409)

    def test_delegate_requires_confirmation_and_supports_pause_resume(self) -> None:
        meeting = self.client.post(
            "/api/meetings",
            json={
                "title": "代理控制测试",
                "scenario": "项目周例会",
                "participation_mode": "delegate",
                "workspace_id": self.workspace_id,
                "agent_identity_id": "p_zhang",
                "authorization_rule_ids": ["auth_default"],
            },
        ).json()
        prepared = self.client.post(f"/api/meetings/{meeting['id']}/prepare")
        self.assertEqual(prepared.status_code, 200)

        blocked = self.client.post(
            f"/api/meetings/{meeting['id']}/analyze",
            json={"transcript": "李娜：确认本周完成界面联调。"},
        )
        self.assertEqual(blocked.status_code, 409)

        started = self.client.post(
            f"/api/meetings/{meeting['id']}/agent/control",
            json={"action": "start"},
        )
        self.assertEqual(started.status_code, 200)
        self.assertEqual(started.json()["agent_session_state"], "delegating")
        self.assertEqual(started.json()["meeting_status"], "in_progress")
        self.assertTrue(any(event["action"] == "确认委托参会" for event in started.json()["audit_events"]))

        paused = self.client.post(
            f"/api/meetings/{meeting['id']}/agent/control",
            json={"action": "pause"},
        )
        self.assertEqual(paused.status_code, 200)
        self.assertEqual(paused.json()["agent_session_state"], "paused")

        blocked_while_paused = self.client.post(
            f"/api/meetings/{meeting['id']}/analyze",
            json={"transcript": "王强：继续推进联调。"},
        )
        self.assertEqual(blocked_while_paused.status_code, 409)

        resumed = self.client.post(
            f"/api/meetings/{meeting['id']}/agent/control",
            json={"action": "resume"},
        )
        self.assertEqual(resumed.status_code, 200)
        self.assertEqual(resumed.json()["agent_session_state"], "delegating")

    def test_meeting_lifecycle_requires_start_and_supports_end_reopen(self) -> None:
        meeting = self.client.post(
            "/api/meetings",
            json={
                "title": "会议生命周期测试",
                "participation_mode": "self",
                "workspace_id": self.workspace_id,
            },
        ).json()
        prepared = self.client.post(f"/api/meetings/{meeting['id']}/prepare").json()
        self.assertEqual(prepared["meeting_status"], "scheduled")

        blocked_before_start = self.client.post(
            f"/api/meetings/{meeting['id']}/analyze",
            json={"transcript": "李娜：确认继续推进当前任务。"},
        )
        self.assertEqual(blocked_before_start.status_code, 409)

        started = self.client.post(
            f"/api/meetings/{meeting['id']}/lifecycle",
            json={"action": "start"},
        )
        self.assertEqual(started.status_code, 200)
        self.assertEqual(started.json()["meeting_status"], "in_progress")

        analyzed = self.client.post(
            f"/api/meetings/{meeting['id']}/analyze",
            json={"transcript": "李娜：确认继续推进当前任务。"},
        )
        self.assertEqual(analyzed.status_code, 200)
        self.client.post(f"/api/meetings/{meeting['id']}/microphone", json={"action": "acquire"})

        ended = self.client.post(
            f"/api/meetings/{meeting['id']}/lifecycle",
            json={"action": "end"},
        )
        self.assertEqual(ended.status_code, 200)
        self.assertEqual(ended.json()["meeting_status"], "ended")
        self.assertEqual(ended.json()["agent_session_state"], "completed")
        self.assertIsNone(self.client.get("/api/microphone").json()["meeting_id"])

        blocked_after_end = self.client.post(
            f"/api/meetings/{meeting['id']}/analyze",
            json={"transcript": "李娜：会议结束后不应继续追加发言。"},
        )
        self.assertEqual(blocked_after_end.status_code, 409)

        reopened = self.client.post(
            f"/api/meetings/{meeting['id']}/lifecycle",
            json={"action": "reopen"},
        )
        self.assertEqual(reopened.status_code, 200)
        self.assertEqual(reopened.json()["meeting_status"], "in_progress")
        self.assertEqual(reopened.json()["agent_session_state"], "delegating")

    def test_action_writeback_does_not_control_meeting_lifecycle(self) -> None:
        meeting = self.create_prepared_meeting("写回与会议结束解耦测试")
        analyzed = self.client.post(
            f"/api/meetings/{meeting['id']}/analyze",
            json={"transcript": "李娜：确认本周完成前端页面并在8月25日交付。"},
        ).json()
        action_item = analyzed["analysis"]["action_items"][0]
        if not action_item["owner_id"] or not action_item["due_date"]:
            completed = self.client.patch(
                f"/api/meetings/{meeting['id']}/action-items/{action_item['id']}",
                json={"owner_id": "p_li", "due_date": "2026-08-25"},
            )
            self.assertEqual(completed.status_code, 200)

        ended = self.client.post(
            f"/api/meetings/{meeting['id']}/lifecycle",
            json={"action": "end"},
        )
        self.assertEqual(ended.status_code, 200)
        self.assertEqual(ended.json()["meeting_status"], "ended")

        written_back = self.client.post(f"/api/meetings/{meeting['id']}/writeback")
        self.assertEqual(written_back.status_code, 200)
        self.assertEqual(written_back.json()["status"], "completed")
        self.assertEqual(written_back.json()["meeting_status"], "ended")
        self.assertEqual(written_back.json()["agent_session_state"], "completed")

        reopened = self.client.post(
            f"/api/meetings/{meeting['id']}/lifecycle",
            json={"action": "reopen"},
        ).json()
        self.assertEqual(reopened["status"], "confirmed")
        self.assertEqual(reopened["meeting_status"], "in_progress")

    def test_incomplete_action_item_must_be_completed_before_writeback(self) -> None:
        meeting = self.create_prepared_meeting("任务完整性测试")
        analyzed = self.client.post(
            f"/api/meetings/{meeting['id']}/analyze",
            json={"transcript": "陌生人：完成全新任务。"},
        ).json()
        action_item = analyzed["analysis"]["action_items"][0]
        self.assertIsNone(action_item["owner_id"])
        self.assertIsNone(action_item["due_date"])

        blocked = self.client.post(f"/api/meetings/{meeting['id']}/writeback")
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.json()["detail"]["code"], "incomplete_action_items")

        invalid_owner = self.client.patch(
            f"/api/meetings/{meeting['id']}/action-items/{action_item['id']}",
            json={"owner_id": "missing-person", "due_date": "2026-08-20"},
        )
        self.assertEqual(invalid_owner.status_code, 422)

        completed_item = self.client.patch(
            f"/api/meetings/{meeting['id']}/action-items/{action_item['id']}",
            json={"owner_id": "p_li", "due_date": "2026-08-20"},
        )
        self.assertEqual(completed_item.status_code, 200)

        completed = self.client.post(f"/api/meetings/{meeting['id']}/writeback")
        self.assertEqual(completed.status_code, 200)
        result = completed.json()
        self.assertEqual(result["status"], "completed")
        task_id = result["analysis"]["writeback_tasks"][0]["id"]
        self.assertIn(task_id, result["analysis"]["export_markdown"])
        self.assertNotIn("Zoom/Teams bot", result["analysis"]["export_markdown"])

        duplicate = self.client.post(f"/api/meetings/{meeting['id']}/writeback")
        self.assertEqual(duplicate.status_code, 409)

    def test_analysis_metrics_only_report_traceable_values(self) -> None:
        meeting = self.create_prepared_meeting("指标采集测试")
        transcript = "李娜：确认本周完成界面联调并在8月25日交付。"
        response = self.client.post(
            f"/api/meetings/{meeting['id']}/analyze",
            json={"transcript": transcript},
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()["analysis"]
        metrics = result["metrics"]
        self.assertEqual(metrics["transcript_characters"], len(transcript))
        self.assertGreater(metrics["minutes_generated_characters"], 0)
        self.assertEqual(metrics["baseline_status"], "pending")
        self.assertIsNone(metrics["savings_percent"])
        self.assertIsNone(result["demo_metrics"]["attention_saved"])

    def test_metric_baseline_updates_the_linked_meeting(self) -> None:
        meeting = self.create_prepared_meeting("减负基准测试")
        analyzed = self.client.post(
            f"/api/meetings/{meeting['id']}/analyze",
            json={"transcript": "李娜：本次会议形成一条可以复核的行动项。"},
        )
        self.assertEqual(analyzed.status_code, 200)

        baseline = self.client.post(
            "/api/metrics/baselines",
            json={
                "id": "baseline_linked_meeting",
                "meeting_id": meeting["id"],
                "meeting_type": "项目进度同步",
                "baseline_minutes": 40,
                "post_process_minutes": 10,
                "sample_date": "2026-08-25",
                "source": "现场计时",
                "notes": "同一会议材料",
            },
        )
        self.assertEqual(baseline.status_code, 200)

        updated = self.client.get(f"/api/meetings/{meeting['id']}").json()
        metrics = updated["analysis"]["metrics"]
        self.assertEqual(metrics["baseline_status"], "available")
        self.assertEqual(metrics["baseline_minutes"], 40)
        self.assertEqual(metrics["post_process_minutes"], 10)
        self.assertEqual(metrics["savings_percent"], 75.0)
        self.assertTrue(any(event["action"] == "记录减负基准" for event in updated["audit_events"]))

        missing = self.client.post(
            "/api/metrics/baselines",
            json={
                "id": "baseline_missing_meeting",
                "meeting_id": "missing",
                "meeting_type": "项目进度同步",
                "baseline_minutes": 20,
                "post_process_minutes": 5,
                "sample_date": "2026-08-25",
                "source": "现场计时",
            },
        )
        self.assertEqual(missing.status_code, 404)

    def test_rejecting_escalation_does_not_stop_meeting(self) -> None:
        meeting = self.create_prepared_meeting("逐条拒绝测试")
        analyzed = self.client.post(
            f"/api/meetings/{meeting['id']}/analyze",
            json={"transcript": "张伟：更换技术路线需要本人确认。"},
        ).json()
        self.assertEqual(analyzed["status"], "awaiting_confirmation")

        escalation_id = analyzed["escalation_requests"][0]["id"]
        rejected = self.client.post(
            f"/api/meetings/{meeting['id']}/escalations/{escalation_id}/resolve",
            json={"action": "reject", "reply": "不同意扩大本周范围。"},
        )
        self.assertEqual(rejected.status_code, 200)
        result = rejected.json()
        self.assertEqual(result["status"], "confirmed")
        self.assertEqual(result["agent_session_state"], "delegating")
        self.assertEqual(result["escalation_requests"][0]["status"], "rejected")
        self.assertTrue(any(event["action"] == "回复会议" for event in result["audit_events"]))
        minutes = result["analysis"]["structured_minutes"]
        export = result["analysis"]["export_markdown"]
        self.assertNotIn("更换技术路线需要本人确认", minutes)
        self.assertNotIn("更换技术路线需要本人确认", export)
        self.assertIn("更换技术路线需要本人确认", result["transcript"])
        self.assertTrue(any(item["status"] == "rejected" for item in result["escalation_requests"]))

        continued = self.client.post(
            f"/api/meetings/{meeting['id']}/analyze",
            json={"transcript": "李娜：继续按既定计划完成界面联调。"},
        )
        self.assertEqual(continued.status_code, 200)
        self.assertEqual(continued.json()["meeting_status"], "in_progress")

    def test_editing_escalation_removes_original_action_item(self) -> None:
        meeting = self.create_prepared_meeting("修改后确认清理原行动项")
        analyzed = self.client.post(
            f"/api/meetings/{meeting['id']}/analyze",
            json={"transcript": "张伟：更换技术路线需要本人确认。"},
        ).json()
        self.assertEqual(analyzed["status"], "awaiting_confirmation")
        original_action_ids = {item["id"] for item in analyzed["analysis"]["action_items"]}
        self.assertTrue(original_action_ids)

        escalation_id = analyzed["escalation_requests"][0]["id"]
        resolved = self.client.post(
            f"/api/meetings/{meeting['id']}/escalations/{escalation_id}/resolve",
            json={"action": "edit", "reply": "不同意更换技术路线，继续原路线。"},
        )

        self.assertEqual(resolved.status_code, 200)
        result = resolved.json()
        remaining_action_ids = {item["id"] for item in result["analysis"]["action_items"]}
        self.assertTrue(original_action_ids.isdisjoint(remaining_action_ids))
        self.assertIn("继续原路线", result["analysis"]["structured_minutes"])
        self.assertIn("继续原路线", result["analysis"]["export_markdown"])
        self.assertTrue(any("继续原路线" in item["content"] for item in result["analysis"]["decisions"]))
        self.assertFalse(any("更换技术路线需要本人确认" in item["content"] for item in result["analysis"]["decisions"]))
        self.assertNotIn("更换技术路线需要本人确认", result["analysis"]["export_markdown"])
        self.assertIn("更换技术路线需要本人确认", result["escalation_requests"][0]["question"])

    def test_pending_escalation_does_not_block_next_transcript(self) -> None:
        meeting = self.create_prepared_meeting("待确认期间继续会议")
        first = self.client.post(
            f"/api/meetings/{meeting['id']}/analyze",
            json={"transcript": "张伟：更换技术路线需要本人确认。"},
        ).json()
        self.assertEqual(first["status"], "awaiting_confirmation")
        self.assertEqual(first["meeting_status"], "in_progress")
        self.assertEqual(first["agent_session_state"], "delegating")

        continued = self.client.post(
            f"/api/meetings/{meeting['id']}/analyze",
            json={"transcript": "李娜：在原技术路线下继续完成本周联调。"},
        )

        self.assertEqual(continued.status_code, 200)
        result = continued.json()
        self.assertEqual(result["status"], "awaiting_confirmation")
        self.assertEqual(result["meeting_status"], "in_progress")
        self.assertIn("在原技术路线下继续完成本周联调", result["transcript"])

    def test_authorized_followup_does_not_repeat_existing_escalation_audit(self) -> None:
        meeting = self.create_prepared_meeting("待确认期间审计不重复")
        first = self.client.post(
            f"/api/meetings/{meeting['id']}/analyze",
            json={"transcript": "张伟：更换技术路线需要本人确认。"},
        ).json()
        first_upgrade_count = sum(event["action"] == "升级本人" for event in first["audit_events"])

        continued = self.client.post(
            f"/api/meetings/{meeting['id']}/analyze",
            json={"transcript": "李娜：请说明当前产品目标进度和风险。"},
        ).json()
        continued_upgrade_count = sum(event["action"] == "升级本人" for event in continued["audit_events"])

        self.assertEqual(continued_upgrade_count, first_upgrade_count)

    def test_analysis_audit_counts_only_current_turn_results(self) -> None:
        meeting = self.create_prepared_meeting("审计按本轮计数")
        self.client.post(
            f"/api/meetings/{meeting['id']}/analyze",
            json={"transcript": "李娜：负责在2026-08-30完成界面联调。"},
        )
        second = self.client.post(
            f"/api/meetings/{meeting['id']}/analyze",
            json={"transcript": "王强：负责在2026-08-31完成接口回归。"},
        ).json()
        analysis_events = [event for event in second["audit_events"] if event["action"] == "分析会议"]

        self.assertEqual(analysis_events[-1]["detail"], "识别 1 条决策和 1 条行动项。")

    def test_overlapping_meetings_keep_transcripts_and_decisions_isolated(self) -> None:
        meeting_a = self.create_prepared_meeting("并行会议 A")
        meeting_b = self.create_prepared_meeting("并行会议 B")
        a_result = self.client.post(
            f"/api/meetings/{meeting_a['id']}/analyze",
            json={"transcript": "张伟：A 会继续按既定计划推进。"},
        ).json()
        b_first = self.client.post(
            f"/api/meetings/{meeting_b['id']}/analyze",
            json={"transcript": "李娜：B 会需要变更范围。"},
        ).json()
        self.assertTrue(any(item["status"] == "pending" for item in b_first["escalation_requests"]))
        b_next = self.client.post(
            f"/api/meetings/{meeting_b['id']}/analyze",
            json={"transcript": "王强：B 会其他授权内工作继续。"},
        ).json()
        self.assertIn("B 会其他授权内工作继续", b_next["transcript"])
        a_after = self.client.get(f"/api/meetings/{meeting_a['id']}").json()
        self.assertEqual(a_after["transcript"], a_result["transcript"])
        self.assertFalse(a_after["escalation_requests"])

    def test_escalation_can_be_deferred_without_losing_item(self) -> None:
        meeting = self.create_prepared_meeting("暂不处理决策测试")
        analyzed = self.client.post(
            f"/api/meetings/{meeting['id']}/analyze",
            json={"transcript": "李娜：请变更范围，把本次交付扩大到移动端。"},
        ).json()
        escalation = analyzed["escalation_requests"][0]
        deferred = self.client.post(
            f"/api/meetings/{meeting['id']}/escalations/{escalation['id']}/resolve",
            json={"action": "defer", "reply": "明天上午再确认"},
        )
        self.assertEqual(deferred.status_code, 200)
        item = next(value for value in deferred.json()["escalation_requests"] if value["id"] == escalation["id"])
        self.assertEqual(item["status"], "deferred")
        self.assertEqual(item["user_reply"], "明天上午再确认")
        self.assertEqual(deferred.json()["meeting_status"], "in_progress")

    def test_repeated_analysis_appends_meeting_history(self) -> None:
        meeting = self.create_prepared_meeting("多轮会议记录测试")
        first_transcript = (
            "李娜：确认在8月20日完成界面联调。\n"
            "张伟：更换技术路线需要本人确认。"
        )
        first = self.client.post(
            f"/api/meetings/{meeting['id']}/analyze",
            json={"transcript": first_transcript},
        ).json()
        first_escalation_id = first["escalation_requests"][0]["id"]
        first_decision_id = first["analysis"]["decisions"][0]["id"]
        first_action_id = first["analysis"]["action_items"][0]["id"]

        resolved = self.client.post(
            f"/api/meetings/{meeting['id']}/escalations/{first_escalation_id}/resolve",
            json={"action": "approve", "reply": "同意评估技术路线，但暂不变更交付日期。"},
        )
        self.assertEqual(resolved.status_code, 200)

        second_transcript = "王强：新增预算需要本人确认，并由我负责在8月22日提交测算。"
        continued = self.client.post(
            f"/api/meetings/{meeting['id']}/analyze",
            json={"transcript": second_transcript},
        )
        self.assertEqual(continued.status_code, 200)
        result = continued.json()

        self.assertIn(first_transcript, result["transcript"])
        self.assertIn(second_transcript, result["transcript"])
        self.assertEqual(len(result["analysis"]["transcript_turns"]), 3)
        self.assertTrue(any(item["id"] == first_decision_id for item in result["analysis"]["decisions"]))
        self.assertTrue(any(item["id"] == first_action_id for item in result["analysis"]["action_items"]))
        self.assertGreaterEqual(len(result["analysis"]["ads_relations"]), 8)
        self.assertEqual(len(result["escalation_requests"]), 2)
        self.assertEqual(result["escalation_requests"][0]["status"], "approved")
        self.assertEqual(result["escalation_requests"][1]["status"], "pending")
        self.assertEqual(result["status"], "awaiting_confirmation")
        minutes = result["analysis"]["structured_minutes"]
        self.assertNotIn("补充记录", minutes)
        self.assertNotIn("。。", minutes)
        self.assertIn("界面联调", minutes)
        self.assertIn("提交测算", minutes)

    def test_stub_speech_review_flow_is_idempotent(self) -> None:
        meeting = self.create_prepared_meeting("语音审核测试")
        job = self.client.post(
            "/api/speech/jobs",
            json={
                "meeting_id": meeting["id"],
                "source_type": "text_stub",
                "original_name": "demo.txt",
                "stub_text": "李娜：完成前端会议工作台。\n王强：完成后端音频接口。",
            },
        )
        self.assertEqual(job.status_code, 200)
        job_id = job.json()["id"]
        segment_id = job.json()["segments"][0]["id"]

        edited = self.client.patch(
            f"/api/speech/jobs/{job_id}/segments/{segment_id}",
            json={"speaker_label": "李娜", "revised_text": "完成新的会议工作台 UI。"},
        )
        self.assertEqual(edited.status_code, 200)
        self.assertIn("新的会议工作台", edited.json()["full_text"])

        full_text = self.client.patch(
            f"/api/speech/jobs/{job_id}/transcript",
            json={"full_text": "李娜：确认完整总稿内容。\n王强：继续推进音频审核。"},
        )
        self.assertEqual(full_text.status_code, 200)
        self.assertIn("完整总稿内容", full_text.json()["full_text"])

        second_segment_id = full_text.json()["segments"][1]["id"]
        segment_after_full_text = self.client.patch(
            f"/api/speech/jobs/{job_id}/segments/{second_segment_id}",
            json={"speaker_label": "王强", "revised_text": "继续推进并完成音频审核。"},
        )
        self.assertEqual(segment_after_full_text.status_code, 200)
        self.assertIn("确认完整总稿内容", segment_after_full_text.json()["full_text"])
        self.assertIn("继续推进并完成音频审核", segment_after_full_text.json()["full_text"])

        confirmed = self.client.post(f"/api/speech/jobs/{job_id}/confirm")
        self.assertEqual(confirmed.status_code, 200)
        again = self.client.post(f"/api/speech/jobs/{job_id}/confirm")
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json()["job"]["status"], "confirmed")

    def test_audio_queue_supports_upload_cancel_retry_and_delete(self) -> None:
        meeting = self.create_prepared_meeting("音频队列测试")

        with patch("app.main._process_speech_job"):
            uploaded = self.client.post(
                "/api/speech/transcriptions",
                files={"file": ("queue.webm", b"not-a-real-audio-file", "audio/webm")},
                data={"meeting_id": meeting["id"], "source_type": "upload", "language": "zh"},
            )
        self.assertEqual(uploaded.status_code, 200)
        job = uploaded.json()
        self.assertEqual(job["status"], "uploaded")
        self.assertEqual(job["progress"], 5)
        self.assertEqual(job["size_bytes"], len(b"not-a-real-audio-file"))
        self.assertEqual(job["mime_type"], "audio/webm")

        cancelled = self.client.post(f"/api/speech/jobs/{job['id']}/cancel")
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.json()["status"], "cancelled")

        with patch("app.main._process_speech_job"):
            retried = self.client.post(f"/api/speech/jobs/{job['id']}/retry")
        self.assertEqual(retried.status_code, 200)
        self.assertEqual(retried.json()["status"], "uploaded")

        cancelled_again = self.client.post(f"/api/speech/jobs/{job['id']}/cancel")
        self.assertEqual(cancelled_again.status_code, 200)
        deleted = self.client.delete(f"/api/speech/jobs/{job['id']}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.client.get(f"/api/speech/jobs/{job['id']}").status_code, 404)

    def test_audio_longer_than_four_hours_is_rejected_and_source_removed(self) -> None:
        meeting = self.create_prepared_meeting("超长音频测试")
        with patch("app.main.probe_duration", return_value=14_401):
            response = self.client.post(
                "/api/speech/transcriptions",
                files={"file": ("too-long.wav", b"audio", "audio/wav")},
                data={"meeting_id": meeting["id"], "source_type": "upload", "language": "zh"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "failed")
        self.assertEqual(response.json()["error_code"], "audio_too_long")
        self.assertIn("4 小时", response.json()["error_message"])
        from app.speech import source_for_job
        self.assertIsNone(source_for_job(response.json()["id"]))

    def test_four_hour_audio_passes_duration_validation(self) -> None:
        meeting = self.create_prepared_meeting("四小时音频边界测试")
        with (
            patch("app.main.probe_duration", return_value=14_400),
            patch("app.main._process_speech_job"),
        ):
            response = self.client.post(
                "/api/speech/transcriptions",
                files={"file": ("four-hours.wav", b"audio", "audio/wav")},
                data={"meeting_id": meeting["id"], "source_type": "upload", "language": "zh"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "uploaded")
        self.client.post(f"/api/speech/jobs/{response.json()['id']}/cancel")
        self.client.delete(f"/api/speech/jobs/{response.json()['id']}")

    def test_audio_retention_only_removes_expired_terminal_sources(self) -> None:
        meeting = self.create_prepared_meeting("音频保留期测试")
        jobs = []
        with patch("app.main._process_speech_job"):
            for name in ("old.wav", "new.wav"):
                response = self.client.post(
                    "/api/speech/transcriptions",
                    files={"file": (name, b"audio", "audio/wav")},
                    data={"meeting_id": meeting["id"], "source_type": "upload", "language": "zh"},
                ).json()
                self.client.post(f"/api/speech/jobs/{response['id']}/cancel")
                jobs.append(response)
        from app.speech import source_for_job
        old_source = source_for_job(jobs[0]["id"])
        new_source = source_for_job(jobs[1]["id"])
        self.assertIsNotNone(old_source)
        self.assertIsNotNone(new_source)
        old_timestamp = datetime.now().timestamp() - 31 * 24 * 60 * 60
        os.utime(old_source, (old_timestamp, old_timestamp))
        self.client.put("/api/settings", json={"audio_retention_days": 30})
        self.assertEqual(cleanup_expired_audio_assets(), 1)
        self.assertIsNone(source_for_job(jobs[0]["id"]))
        self.assertIsNotNone(source_for_job(jobs[1]["id"]))
        self.client.put("/api/settings", json={"audio_retention_days": 0})
        for job in jobs:
            self.client.delete(f"/api/speech/jobs/{job['id']}")

    def test_backup_restore_recovers_workspace_and_settings(self) -> None:
        self.client.put("/api/settings", json={"audio_retention_days": 90})
        backup = self.client.post("/api/data/backups").json()["filename"]
        temporary = self.client.post("/api/workspaces", json={"name": "恢复后应消失"}).json()
        self.client.put("/api/settings", json={"audio_retention_days": 30})
        restored = self.client.post("/api/data/restore", json={"filename": backup})
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(self.client.get("/api/settings").json()["audio_retention_days"], 90)
        self.assertNotIn(temporary["id"], {item["id"] for item in self.client.get("/api/workspaces").json()})
        self.client.put("/api/settings", json={"audio_retention_days": 0})

    def test_empty_audio_returns_recoverable_error(self) -> None:
        meeting = self.create_prepared_meeting("空音频测试")
        response = self.client.post(
            "/api/speech/transcriptions",
            files={"file": ("empty.wav", b"", "audio/wav")},
            data={"meeting_id": meeting["id"], "source_type": "upload", "language": "zh"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "failed")
        self.assertEqual(response.json()["error_code"], "empty_audio")

    def test_failed_or_cancelled_job_without_audio_cannot_retry(self) -> None:
        meeting = self.create_prepared_meeting("音频恢复边界测试")
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        job = SpeechJob(
            id="stt_missing_source",
            meeting_id=meeting["id"],
            source_type="upload",
            original_name="missing.wav",
            status="failed",
            progress=55,
            language="zh",
            model_name="faster-whisper-small",
            device="cpu",
            compute_type="int8",
            full_text="",
            error_code="ffmpeg_failed",
            error_message="音频预处理失败，请更换文件后重试。",
            created_at=now,
            updated_at=now,
        )
        save_speech_job(job)
        response = self.client.post(f"/api/speech/jobs/{job.id}/retry")
        self.assertEqual(response.status_code, 409)

    def test_service_restart_marks_interrupted_audio_as_retryable(self) -> None:
        meeting = self.create_prepared_meeting("服务重启恢复测试")
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        job = SpeechJob(
            id="stt_interrupted_on_restart",
            meeting_id=meeting["id"],
            source_type="upload",
            original_name="interrupted.webm",
            status="transcribing",
            progress=63,
            language="zh",
            model_name="faster-whisper-small",
            device="cpu",
            compute_type="int8",
            full_text="",
            created_at=now,
            updated_at=now,
        )
        save_speech_job(job)

        recover_interrupted_speech_jobs()

        recovered = self.client.get(f"/api/speech/jobs/{job.id}").json()
        self.assertEqual(recovered["status"], "failed")
        self.assertEqual(recovered["error_code"], "service_restarted")
        self.assertIn("重新转写", recovered["error_message"])
        response = self.client.post(f"/api/speech/jobs/{job.id}/retry")
        self.assertEqual(response.status_code, 409)
        self.assertIn("原始音频已不存在", response.json()["detail"])

    def test_old_audio_attempt_cannot_overwrite_retried_job(self) -> None:
        meeting = self.create_prepared_meeting("音频重试代次测试")
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        job = SpeechJob(
            id="stt_attempt_guard",
            meeting_id=meeting["id"],
            source_type="upload",
            original_name="attempt.wav",
            status="uploaded",
            progress=5,
            language="zh",
            model_name="faster-whisper-small",
            device="cpu",
            compute_type="int8",
            full_text="",
            attempt=2,
            created_at=now,
            updated_at=now,
        )
        save_speech_job(job)

        with patch("app.main.transcribe") as transcribe_mock:
            _process_speech_job(job.id, "unused.wav", "zh", 1)

        transcribe_mock.assert_not_called()
        current = get_speech_job(job.id)
        self.assertIsNotNone(current)
        self.assertEqual(current.attempt, 2)
        self.assertEqual(current.status, "uploaded")

    def test_diarization_assigns_anonymous_speakers_after_transcription(self) -> None:
        meeting = self.create_prepared_meeting("匿名说话人分离测试")
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        job = SpeechJob(
            id="stt_diarization_success",
            meeting_id=meeting["id"],
            source_type="upload",
            original_name="two-speakers.wav",
            status="uploaded",
            progress=5,
            language="zh",
            model_name="faster-whisper-small",
            device="cpu",
            compute_type="int8",
            full_text="",
            diarization_enabled=True,
            requested_speaker_count=2,
            created_at=now,
            updated_at=now,
        )
        save_speech_job(job)
        raw_segments = [
            {
                "start": 0.0,
                "end": 2.0,
                "text": "你好收到",
                "words": [
                    {"start": 0.0, "end": 0.8, "text": "你好"},
                    {"start": 1.0, "end": 1.8, "text": "收到"},
                ],
            }
        ]

        with (
            patch("app.main.transcribe", return_value=raw_segments) as transcribe_mock,
            patch(
                "app.main.diarize",
                return_value=[SpeakerTurn(0.0, 0.9, 4), SpeakerTurn(0.9, 2.0, 8)],
            ) as diarize_mock,
        ):
            _process_speech_job(job.id, "unused.wav", "zh", job.attempt)

        saved = get_speech_job(job.id)
        self.assertIsNotNone(saved)
        self.assertEqual(saved.status, "awaiting_review")
        self.assertEqual([item.speaker_label for item in saved.segments], ["发言人 1", "发言人 2"])
        self.assertEqual(saved.detected_speaker_count, 2)
        self.assertIsNone(saved.diarization_warning)
        self.assertTrue(transcribe_mock.call_args.kwargs["word_timestamps"])
        self.assertEqual(diarize_mock.call_args.kwargs["speaker_count"], 2)

    def test_diarization_failure_preserves_transcript_for_review(self) -> None:
        meeting = self.create_prepared_meeting("说话人分离回退测试")
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        job = SpeechJob(
            id="stt_diarization_fallback",
            meeting_id=meeting["id"],
            source_type="upload",
            original_name="fallback.wav",
            status="uploaded",
            progress=5,
            language="zh",
            model_name="faster-whisper-small",
            device="cpu",
            compute_type="int8",
            full_text="",
            diarization_enabled=True,
            created_at=now,
            updated_at=now,
        )
        save_speech_job(job)

        with (
            patch(
                "app.main.transcribe",
                return_value=[{"start": 0.0, "end": 1.0, "text": "保留这段转写", "words": []}],
            ),
            patch("app.main.diarize", side_effect=RuntimeError("diarization_model_missing")),
        ):
            _process_speech_job(job.id, "unused.wav", "zh", job.attempt)

        saved = get_speech_job(job.id)
        self.assertIsNotNone(saved)
        self.assertEqual(saved.status, "awaiting_review")
        self.assertEqual(saved.segments[0].speaker_label, "发言人 1")
        self.assertIn("说话人分离", saved.diarization_warning)
        self.assertIsNone(saved.error_code)

    def test_upload_records_diarization_options_before_audio_validation(self) -> None:
        meeting = self.create_prepared_meeting("说话人分离参数测试")
        response = self.client.post(
            "/api/speech/transcriptions",
            files={"file": ("empty.wav", b"", "audio/wav")},
            data={
                "meeting_id": meeting["id"],
                "source_type": "upload",
                "language": "zh",
                "diarization_enabled": "false",
                "speaker_count": "3",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["diarization_enabled"])
        self.assertEqual(response.json()["requested_speaker_count"], 3)

    def test_upload_rejects_speaker_count_outside_two_to_ten(self) -> None:
        meeting = self.create_prepared_meeting("说话人数范围测试")
        response = self.client.post(
            "/api/speech/transcriptions",
            files={"file": ("empty.wav", b"", "audio/wav")},
            data={"meeting_id": meeting["id"], "speaker_count": "1"},
        )

        self.assertEqual(response.status_code, 422)

    def test_speech_health_contract(self) -> None:
        response = self.client.get("/api/speech/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn(payload["status"], {"ready", "degraded", "not_configured"})
        self.assertIn("ffmpeg_available", payload)

    def test_ai_status_reports_effective_runtime(self) -> None:
        response = self.client.get("/api/ai/status")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn(payload["mode"], {"mock", "live"})
        self.assertTrue(payload["label"])
        self.assertTrue(payload["message"])

    def test_meeting_model_can_switch_without_losing_state(self) -> None:
        meeting = self.create_prepared_meeting("模型切换测试")
        response = self.client.patch(
            f"/api/meetings/{meeting['id']}/model",
            json={"model_provider_id": "mock"},
        )
        self.assertEqual(response.status_code, 200)
        switched = response.json()
        self.assertEqual(switched["model_provider_id"], "mock")
        self.assertEqual(switched["status"], "prepared")
        self.assertTrue(any(event["action"] == "切换会议模型" for event in switched["audit_events"]))

    def test_saving_existing_model_without_key_preserves_tested_status(self) -> None:
        models = self.client.get("/api/models").json()
        model = next(item for item in models if item["provider_id"] == "deepseek")
        payload = {
            "provider_id": model["provider_id"],
            "provider_name": model["provider_name"],
            "adapter_type": model["adapter_type"],
            "base_url": model["base_url"],
            "model": model["model"],
            "enabled": True,
            "is_default": False,
            "api_key": "local-test-key",
        }
        self.assertEqual(self.client.put("/api/models/deepseek", json=payload).status_code, 200)
        with patch("app.main.test_chat_completion", return_value=(True, "连接正常")):
            tested = self.client.post("/api/models/deepseek/test")
        self.assertEqual(tested.status_code, 200)
        self.assertEqual(tested.json()["connection_status"], "ok")

        payload["api_key"] = ""
        payload["is_default"] = True
        saved = self.client.put("/api/models/deepseek", json=payload)
        self.assertEqual(saved.status_code, 200)
        self.assertTrue(saved.json()["configured"])
        self.assertEqual(saved.json()["connection_status"], "ok")

    def test_ads_workspace_persists_and_is_used_by_meeting(self) -> None:
        created = self.client.post(
            "/api/workspaces",
            json={
                "name": "客户交付工作区",
                "description": "验证可编辑业务上下文",
                "people": [{"id": "p_owner", "name": "负责人", "role": "交付经理"}],
                "objectives": [{
                    "id": "obj_delivery", "title": "按期完成客户交付", "progress": 35,
                    "metric": "验收项全部通过", "risk": "关键接口仍待确认",
                }],
                "tasks": [{
                    "id": "task_contract", "title": "确认接口清单", "owner_id": "p_owner",
                    "due_date": "2026-08-25", "status": "进行中",
                }],
                "authorization_rules": [{
                    "id": "auth_delivery", "person_id": "p_owner",
                    "scope": "允许说明既定交付计划", "allowed_actions": ["提供信息"],
                    "escalation_triggers": ["变更合同范围"],
                }],
            },
        )
        self.assertEqual(created.status_code, 200)
        workspace = created.json()

        workspace["description"] = "刷新后仍应保留"
        saved = self.client.put(
            f"/api/workspaces/{workspace['id']}",
            json={key: workspace[key] for key in ["name", "description", "people", "objectives", "tasks", "authorization_rules"]},
        )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(self.client.get(f"/api/workspaces/{workspace['id']}").json()["description"], "刷新后仍应保留")

        meeting = self.client.post(
            "/api/meetings",
            json={"title": "客户交付评审", "workspace_id": workspace["id"]},
        ).json()
        self.assertEqual(meeting["workspace_id"], workspace["id"])
        prepared = self.client.post(f"/api/meetings/{meeting['id']}/prepare").json()
        self.assertIn("按期完成客户交付", prepared["pre_meeting_brief"])
        self.assertIn("允许说明既定交付计划", prepared["agenda"][2]["context"])
        started = self.client.post(f"/api/meetings/{meeting['id']}/lifecycle", json={"action": "start"})
        self.assertEqual(started.status_code, 200)

        analyzed = self.client.post(
            f"/api/meetings/{meeting['id']}/analyze",
            json={"transcript": "负责人：需要变更合同范围，并由我负责在8月25日完成。"},
        )
        self.assertEqual(analyzed.status_code, 200)
        result = analyzed.json()
        self.assertEqual(result["status"], "awaiting_confirmation")
        self.assertIn("auth_delivery", result["escalation_requests"][0]["evidence_object_ids"])
        self.assertTrue(
            any(link["target_id"] == "obj_delivery" for link in result["analysis"]["ads_relations"])
        )

        escalation_id = result["escalation_requests"][0]["id"]
        resolved = self.client.post(
            f"/api/meetings/{meeting['id']}/escalations/{escalation_id}/resolve",
            json={"action": "approve", "reply": "同意按确认后的范围继续。"},
        )
        self.assertEqual(resolved.status_code, 200)
        action_item = resolved.json()["analysis"]["action_items"][0]
        completed = self.client.patch(
            f"/api/meetings/{meeting['id']}/action-items/{action_item['id']}",
            json={"owner_id": "p_owner", "due_date": "2026-08-25"},
        )
        self.assertEqual(completed.status_code, 200)
        written_back = self.client.post(f"/api/meetings/{meeting['id']}/writeback")
        self.assertEqual(written_back.status_code, 200)
        self.assertIn("负责人", written_back.json()["analysis"]["export_markdown"])

    def test_empty_workspace_does_not_receive_preloaded_business_context(self) -> None:
        workspace = self.client.post(
            "/api/workspaces",
            json={
                "name": "空白工作区",
                "description": "由用户从空白状态开始配置",
                "people": [],
                "objectives": [],
                "tasks": [],
                "authorization_rules": [],
            },
        )
        self.assertEqual(workspace.status_code, 200)
        meeting = self.client.post(
            "/api/meetings",
            json={"title": "空白上下文会议", "workspace_id": workspace.json()["id"]},
        ).json()
        prepared = self.client.post(f"/api/meetings/{meeting['id']}/prepare")
        self.assertEqual(prepared.status_code, 200)
        self.assertIn("尚未配置业务目标", prepared.json()["pre_meeting_brief"])
        self.assertNotIn("完成 ADS 会议智能体首个可用版本", prepared.json()["pre_meeting_brief"])
        started = self.client.post(f"/api/meetings/{meeting['id']}/lifecycle", json={"action": "start"})
        self.assertEqual(started.status_code, 200)

        analyzed = self.client.post(
            f"/api/meetings/{meeting['id']}/analyze",
            json={"transcript": "主持人：确认今天记录需求，后续再补充负责人。"},
        )
        self.assertEqual(analyzed.status_code, 200)
        serialized = analyzed.text
        self.assertNotIn("完成 ADS 会议智能体首个可用版本", serialized)
        self.assertNotIn("项目周例会中，允许确认既定排期", serialized)


if __name__ == "__main__":
    unittest.main()
