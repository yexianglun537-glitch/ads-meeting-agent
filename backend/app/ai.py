import os
import json
import re
import uuid
from datetime import datetime

import httpx
from dotenv import load_dotenv

from app.mock_data import AUTHORIZATION_RULES, OBJECTIVES, PEOPLE, TASKS
from app.prompt_templates import PROMPT_VERSION, build_system_prompt
from app.models import (
    ActionItem,
    AdsRelation,
    AdsWorkspacePayload,
    AgentReply,
    AgendaDraftRequest,
    AgendaDraftResponse,
    AgendaItem,
    AuditEvent,
    DemoMetrics,
    Decision,
    MeetingAnalysis,
    MeetingAnalysisRequest,
    ModelConfig,
    Objective,
    AuthorizationRule,
    Task,
    TranscriptTurn,
    WorkloadMetrics,
)

load_dotenv()


def _person_name(person_id: str | None, people=PEOPLE) -> str:
    if person_id is None:
        return "待确认"
    return next((person.name for person in people if person.id == person_id), person_id)


def _ads_context(payload: MeetingAnalysisRequest) -> AdsWorkspacePayload:
    current = payload.ads_context
    if current is not None:
        return current.model_copy(deep=True)
    return AdsWorkspacePayload(
        name="ADS 工作区",
        description="",
        people=PEOPLE,
        objectives=OBJECTIVES,
        tasks=TASKS,
        authorization_rules=AUTHORIZATION_RULES,
    )


def _parse_transcript(transcript: str) -> list[tuple[str, str]]:
    turns: list[tuple[str, str]] = []
    for raw_line in transcript.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = re.match(r"^([^：:]{1,12})[：:]\s*(.+)$", line)
        turns.append((match.group(1).strip(), match.group(2).strip()) if match else ("参会人", line))
    return turns or [("参会人", transcript.strip())]


def _due_date(text: str) -> str | None:
    match = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日", text)
    if match:
        return f"{datetime.now().year}-{int(match.group(1)):02d}-{int(match.group(2)):02d}"
    return None


_CHANGE_MARKERS = (
    "变更", "改变", "更改", "修改", "调整", "替换", "更换", "切换",
    "取消", "改为", "改成", "新增", "增加", "扩大", "缩小", "延期",
    "延后", "推迟", "提前", "承诺",
)
_ESCALATION_CONCEPTS = (
    ("预算", ("预算", "费用", "成本", "采购金额")),
    ("路线", ("路线", "方案", "技术栈")),
    ("范围", ("范围", "边界")),
    ("交付", ("交付", "上线", "发布")),
    ("日期", ("日期", "时间", "排期", "期限", "截止", "本周", "下周", "本月", "下月")),
    ("承诺", ("承诺", "保证", "答应")),
    ("合同", ("合同", "协议")),
)


def escalation_trigger_matches(content: str, trigger: str) -> bool:
    """Conservatively match common Chinese policy wording variants."""
    normalized_content = re.sub(r"[\s，。；、：:,.!?！？]", "", content)
    normalized_trigger = re.sub(r"[\s，。；、：:,.!?！？]", "", trigger)
    if normalized_trigger and normalized_trigger in normalized_content:
        return True
    if not any(marker in normalized_content for marker in _CHANGE_MARKERS):
        return False
    return any(
        concept in normalized_trigger and any(alias in normalized_content for alias in aliases)
        for concept, aliases in _ESCALATION_CONCEPTS
    )


def find_escalation_match(
    transcript: str, rules: list[AuthorizationRule]
) -> tuple[str, str, AuthorizationRule] | None:
    return next(
        (
            (speaker, content, rule)
            for speaker, content in _parse_transcript(transcript)
            for rule in rules
            if "本人确认" in content
            or any(escalation_trigger_matches(content, trigger) for trigger in rule.escalation_triggers)
        ),
        None,
    )


def build_mock_analysis(payload: MeetingAnalysisRequest) -> MeetingAnalysis:
    meeting_id = f"mtg_{uuid.uuid4().hex[:8]}"
    decision_id = f"dec_{uuid.uuid4().hex[:8]}"
    action_id = f"act_{uuid.uuid4().hex[:8]}"

    context = _ads_context(payload)
    people = context.people
    objectives = context.objectives
    tasks = context.tasks
    rules = context.authorization_rules
    primary_objective = objectives[0] if objectives else Objective(
        id="context_missing_objective",
        title="尚未配置业务目标",
        progress=0,
        metric="尚未配置衡量指标",
        risk="工作区缺少业务目标",
    )
    primary_rule = rules[0] if rules else AuthorizationRule(
        id="context_missing_authorization",
        person_id="",
        scope="尚未配置代理授权，涉及执行或承诺的事项需要本人确认",
        allowed_actions=[],
        escalation_triggers=[],
    )
    effective_rules = rules or [primary_rule]
    primary_task_id = tasks[0].id if tasks else primary_objective.id
    parsed_turns = _parse_transcript(payload.transcript)
    person_ids = {person.name: person.id for person in people}
    escalation_match = find_escalation_match(payload.transcript, effective_rules)
    decision_candidate = next(
        ((speaker, content) for speaker, content in parsed_turns if any(word in content for word in ["确认", "决定", "先做", "先完成", "先交付"])),
        None,
    )
    action_candidate = next(
        ((speaker, content) for speaker, content in parsed_turns if any(word in content for word in ["负责", "完成", "实现", "交付"])),
        None,
    )
    information_only = decision_candidate is None and action_candidate is None and escalation_match is None
    decision_source = decision_candidate or parsed_turns[0]
    action_source = action_candidate or decision_source
    escalation_source = escalation_match[:2] if escalation_match else None
    escalation_rule = escalation_match[2] if escalation_match else primary_rule
    owner_id = person_ids.get(action_source[0])
    due_date = _due_date(action_source[1])
    grounded_reply, grounded_evidence = _local_question_answer(decision_source[1], context)
    authorized_reply = (
        grounded_reply
        if information_only else
        "可以确认。该事项属于既定范围内的进度或任务确认。"
    )
    authorized_evidence = list(dict.fromkeys([
        primary_rule.id,
        *grounded_evidence,
        primary_task_id,
    ]))

    decision = Decision(
        id=decision_id,
        topic="本期交付范围确认",
        content=decision_source[1],
        owner_id=person_ids.get(decision_source[0], owner_id),
        due_date=due_date,
        evidence=f"原始发言：{decision_source[0]}：{decision_source[1]}",
    )
    action_item = ActionItem(
        id=action_id,
        title=action_source[1],
        owner_id=owner_id,
        due_date=due_date,
        linked_decision_id=decision.id,
    )
    writeback_task = (
        Task(
            id=f"task_{uuid.uuid4().hex[:8]}",
            title=action_item.title,
            owner_id=action_item.owner_id,
            due_date=action_item.due_date,
            status="待确认",
            source_meeting_id=meeting_id,
            source_decision_id=decision.id,
        )
        if not information_only and action_item.owner_id and action_item.due_date
        else None
    )

    brief = (
        f"{payload.scenario}围绕“{payload.title}”展开。当前 ADS 目标中，"
        f"“{primary_objective.title}”进度 {primary_objective.progress}%，主要风险是：{primary_objective.risk}。"
        f"建议本次会议聚焦交付范围、接口边界、数据依据和本人确认事项。"
    )
    minutes = (
        f"本次会议共识别 {len(parsed_turns)} 条发言，内容为信息询问，未形成新决策或行动项。"
        if information_only else
        f"本次会议共识别 {len(parsed_turns)} 条发言。主要决策：{decision_source[1]}。"
        f"主要行动项：{action_source[1]}。负责人为 {_person_name(owner_id, people)}，截止时间为 {due_date or '待确认'}。"
    )
    transcript_turns = []
    for speaker, content in parsed_turns:
        if escalation_source and content == escalation_source[1]:
            action = "触发授权升级"
            links = [escalation_rule.id, decision_id]
        elif any(word in content for word in ["负责", "完成", "实现", "交付"]):
            action = "识别为行动项"
            links = [action_id, person_ids.get(speaker, primary_objective.id)]
        elif any(word in content for word in ["确认", "决定", "先做"]):
            action = "记录为决策依据"
            links = [decision_id, primary_objective.id]
        else:
            action = "记录为会议上下文"
            links = [primary_objective.id]
        transcript_turns.append(TranscriptTurn(speaker=speaker, content=content, agent_action=action, linked_object_ids=links))
    ads_relations = ([] if information_only else [
        AdsRelation(
            source_id=meeting_id,
            source_label=payload.title,
            relation="产生决策",
            target_id=decision.id,
            target_label=decision.topic,
        ),
        AdsRelation(
            source_id=decision.id,
            source_label=decision.topic,
            relation="生成行动项",
            target_id=writeback_task.id if writeback_task else action_item.id,
            target_label=action_item.title,
        ),
        AdsRelation(
            source_id=writeback_task.id if writeback_task else action_item.id,
            source_label=action_item.title,
            relation="服务目标",
            target_id=primary_objective.id,
            target_label=primary_objective.title,
        ),
    ]) + [AdsRelation(
        source_id=escalation_rule.id,
        source_label=f"{_person_name(escalation_rule.person_id, people)}的会议授权",
        relation="约束代理",
        target_id=meeting_id,
        target_label=payload.title,
    )]
    audit_events = [
        AuditEvent(time="会前", actor="ADS 会议智能体", action="生成简报", detail="读取目标进度、风险和待办，形成会议议程。"),
        AuditEvent(time="会中", actor="ADS 会议智能体", action="授权内确认", detail=f"依据“{primary_rule.scope}”处理既定信息。"),
        AuditEvent(time="会中", actor="ADS 会议智能体", action="升级本人", detail=(f"命中升级条件：{escalation_source[1]}" if escalation_source else "本次会议未命中升级条件。")),
        AuditEvent(
            time="会后",
            actor="ADS 会议智能体",
            action="任务草案",
            detail=(
                "本轮未识别行动项。" if information_only else
                f"生成待回写任务 {writeback_task.id}。" if writeback_task else
                "任务缺少负责人或截止日期，等待本人补全。"
            ),
        ),
    ]
    decision_markdown = (
        f"- {decision.content} 负责人：{_person_name(decision.owner_id, people)}，截止：{decision.due_date or '待确认'}"
        if not information_only else "- 无"
    )
    action_markdown = (
        f"- {action_item.title} 负责人：{_person_name(action_item.owner_id, people)}，截止：{action_item.due_date or '待确认'}"
        if not information_only else "- 无"
    )
    export_markdown = (
        f"# {payload.title}\n\n"
        f"## 会前简报\n{brief}\n\n"
        f"## 结构化纪要\n{minutes}\n\n"
        "## 决策\n"
        f"{decision_markdown}\n\n"
        "## 行动项\n"
        f"{action_markdown}\n\n"
        "## 代理判断\n"
        f"- 授权范围：{primary_rule.scope}\n"
        f"- 升级条件：{'、'.join(primary_rule.escalation_triggers)}\n"
    )

    return MeetingAnalysis(
        meeting_id=meeting_id,
        prompt_version=PROMPT_VERSION,
        pre_meeting_brief=brief,
        agenda=[
            AgendaItem(
                topic="目标与范围",
                context=f"{primary_objective.title}，当前进度 {primary_objective.progress}%。",
                suggested_question="当前交付范围是否满足业务目标？",
            ),
            AgendaItem(
                topic="输入适配",
                context=f"当前工作区有 {len(tasks)} 条任务需要跟踪。",
                suggested_question="负责人、截止时间和验收标准是否明确？",
            ),
            AgendaItem(
                topic="授权升级",
                context=primary_rule.scope,
                suggested_question="哪些事项必须升级给本人确认？",
            ),
        ],
        transcript_turns=transcript_turns,
        structured_minutes=minutes,
        decisions=[] if information_only else [decision],
        action_items=[] if information_only else [action_item],
        agent_replies=([
            AgentReply(
                question=decision_source[1],
                decision="confirm",
                reply=authorized_reply,
                reason=f"符合授权范围：{primary_rule.scope}",
                evidence_object_ids=authorized_evidence,
            ),
        ] if not escalation_source or decision_source[1] != escalation_source[1] else []) + ([AgentReply(
            question=escalation_source[1],
            decision="escalate",
            reply="该事项超出当前代理授权，需要本人确认后再继续执行。",
            reason="原始发言命中本人确认要求或授权升级条件。",
            evidence_object_ids=[escalation_rule.id, primary_objective.id],
        )] if escalation_source else []),
        writeback_tasks=[writeback_task] if writeback_task and not information_only else [],
        ads_relations=ads_relations,
        audit_events=audit_events,
        demo_metrics=DemoMetrics(
            tasks_created=1 if writeback_task and not information_only else 0,
            escalations=1 if escalation_source else 0,
        ),
        metrics=WorkloadMetrics(
            measurement_status="partial",
            transcript_characters=len(payload.transcript),
            minutes_generated_characters=len(minutes),
            action_items_created=0 if information_only else 1,
            escalations=1 if escalation_source else 0,
        ),
        export_markdown=export_markdown,
    )


def default_model_configs() -> list[ModelConfig]:
    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "")
    compatible_key = os.getenv("OPENAI_COMPATIBLE_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
    return [
        ModelConfig(
            provider_id="deepseek",
            provider_name="DeepSeek",
            adapter_type="deepseek",
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            enabled=True,
            is_default=True,
            configured=bool(deepseek_key),
            connection_status="untested" if deepseek_key else "not_configured",
            message="在线模型。未配置 API Key 时可切换到本地规则模式。",
            api_key_masked="已配置" if deepseek_key else "",
            vendor_id="deepseek",
        ),
        ModelConfig(
            provider_id="openai-compatible",
            provider_name="OpenAI-compatible",
            adapter_type="openai_compatible",
            base_url=os.getenv("OPENAI_COMPATIBLE_BASE_URL", os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")),
            model=os.getenv("OPENAI_COMPATIBLE_MODEL", os.getenv("OPENAI_MODEL", "gpt-4.1-mini")),
            enabled=True,
            is_default=False,
            configured=bool(compatible_key),
            connection_status="untested" if compatible_key else "not_configured",
            message="预留通用 Base URL + API Key + Model 配置，可接 Qwen、GLM 等兼容服务。",
            api_key_masked="已配置" if compatible_key else "",
            vendor_id="generic",
        ),
        ModelConfig(
            provider_id="mock",
            provider_name="本地规则模式",
            adapter_type="mock",
            base_url="local://mock",
            model="rules-and-mock-data",
            enabled=True,
            is_default=False,
            configured=True,
            connection_status="mock",
            message="无需网络，提供基础结构化处理和授权规则判断，不调用在线大模型。",
            vendor_id="local-rules",
            capabilities=["chat", "structured_output", "offline"],
        ),
    ]


def _provider_runtime(provider_id: str) -> tuple[str, str, str]:
    from app.storage import get_model_secret, list_model_configs

    configured = next((item for item in list_model_configs() if item.provider_id == provider_id), None)
    if configured is not None and configured.adapter_type != "mock":
        api_key = get_model_secret(provider_id)
        if api_key:
            return api_key, configured.base_url.rstrip("/"), configured.model
    if provider_id == "deepseek":
        return (
            os.getenv("DEEPSEEK_API_KEY", ""),
            os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1").rstrip("/"),
            os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        )
    if provider_id == "openai-compatible":
        return (
            os.getenv("OPENAI_COMPATIBLE_API_KEY", os.getenv("OPENAI_API_KEY", "")),
            os.getenv("OPENAI_COMPATIBLE_BASE_URL", os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/"),
            os.getenv("OPENAI_COMPATIBLE_MODEL", os.getenv("OPENAI_MODEL", "gpt-4.1-mini")),
        )
    return "", "", ""


def mock_ai_enabled() -> bool:
    return os.getenv("USE_MOCK_AI", "true").lower() == "true"


def provider_ready(provider_id: str) -> bool:
    if mock_ai_enabled() or provider_id == "mock":
        return False
    api_key, base_url, model = _provider_runtime(provider_id)
    return bool(api_key and base_url and model)


def _agenda_text(agenda: list[AgendaItem]) -> str:
    return "\n".join(f"{item.duration_minutes} 分钟｜{item.topic}" for item in agenda)


def _allocate_minutes(total: int, count: int) -> list[int]:
    base = total // count
    values = [base] * count
    values[-1] += total - sum(values)
    return values


def build_local_agenda_draft(payload: AgendaDraftRequest) -> AgendaDraftResponse:
    topics: list[str] = []
    for raw in re.split(r"[\n；;。]+", payload.content):
        topic = re.sub(r"^[\s\d.、-]+", "", raw).strip()
        if topic and topic not in topics:
            topics.append(topic)
        if len(topics) == 5:
            break

    if payload.duration_minutes < 30:
        topics = topics[:3] or ["明确会议目标"]
        for fallback in ("确认重点事项", "明确结论与行动项"):
            if len(topics) >= 2:
                break
            if fallback not in topics:
                topics.append(fallback)
        minutes = _allocate_minutes(payload.duration_minutes, len(topics))
        agenda = [
            AgendaItem(
                topic=topic,
                context=f"围绕“{topic}”形成明确结论。",
                suggested_question=f"关于“{topic}”，本次需要确认什么？",
                duration_minutes=minutes[index],
            )
            for index, topic in enumerate(topics)
        ]
    else:
        topics = topics or ["确认重点事项"]
        boundary_minutes = min(10, max(5, payload.duration_minutes // 6))
        middle_minutes = _allocate_minutes(
            payload.duration_minutes - boundary_minutes * 2,
            len(topics),
        )
        agenda = [
            AgendaItem(
                topic="开场与目标确认",
                context="确认本次会议目标、范围和预期产出。",
                suggested_question="会议结束前必须形成哪些结论？",
                duration_minutes=boundary_minutes,
            ),
            *[
                AgendaItem(
                    topic=topic,
                    context=f"围绕“{topic}”讨论事实、分歧和决策条件。",
                    suggested_question=f"关于“{topic}”，需要确认什么结论？",
                    duration_minutes=middle_minutes[index],
                )
                for index, topic in enumerate(topics)
            ],
            AgendaItem(
                topic="结论与行动项",
                context="汇总决策、负责人、截止日期和待升级事项。",
                suggested_question="行动项的负责人和完成时间是否明确？",
                duration_minutes=boundary_minutes,
            ),
        ]
    return AgendaDraftResponse(agenda_text=_agenda_text(agenda), agenda=agenda, mode="local_rules")


async def build_agenda_draft(
    payload: AgendaDraftRequest,
    context: AdsWorkspacePayload,
) -> tuple[AgendaDraftResponse, str, str]:
    local = build_local_agenda_draft(payload)
    api_key, base_url, model = _provider_runtime(payload.model_provider_id)
    if not provider_ready(payload.model_provider_id):
        return local, model or "rules", ""
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {
                            "role": "system",
                            "content": "你是会议议程规划助手。只返回 JSON，议程分钟数之和必须等于会议总时长。",
                        },
                        {
                            "role": "user",
                            "content": json.dumps(
                                {
                                    "content": payload.content,
                                    "duration_minutes": payload.duration_minutes,
                                    "workspace": context.model_dump(),
                                    "schema": {
                                        "agenda_text": "string",
                                        "agenda": [
                                            {
                                                "topic": "string",
                                                "context": "string",
                                                "suggested_question": "string",
                                                "duration_minutes": "integer",
                                            }
                                        ],
                                    },
                                },
                                ensure_ascii=False,
                            ),
                        },
                    ],
                },
            )
            response.raise_for_status()
            data = json.loads(response.json()["choices"][0]["message"]["content"])
        data["mode"] = "live"
        draft = AgendaDraftResponse.model_validate(data)
        if not draft.agenda or any(item.duration_minutes is None for item in draft.agenda):
            raise ValueError("在线议程缺少分钟分配")
        if sum(item.duration_minutes or 0 for item in draft.agenda) != payload.duration_minutes:
            raise ValueError("在线议程分钟合计与会议时长不一致")
        return draft, model, ""
    except Exception as exc:
        return local, model or payload.model_provider_id, str(exc)[:500]


def _local_question_answer(question: str, context: AdsWorkspacePayload) -> tuple[str, list[str]]:
    normalized = question.strip()
    if context.objectives and any(word in normalized for word in ("目标", "进度", "指标")):
        item = context.objectives[0]
        return f"当前目标“{item.title}”进度为 {item.progress}%。衡量指标：{item.metric}。当前风险：{item.risk}。", [item.id]
    if context.tasks and any(word in normalized for word in ("任务", "负责人", "截止")):
        item = context.tasks[0]
        return f"当前优先任务是“{item.title}”，负责人为 {item.owner_id}，截止日期 {item.due_date}，状态为{item.status}。", [item.id]
    if context.risks and "风险" in normalized:
        item = context.risks[0]
        return f"当前风险“{item.title}”，影响为：{item.impact or '尚未补充'}，状态为{item.status}。", [item.id]
    return "当前资料不足以直接回答。请补充对应项目、目标、任务、风险或制度后再询问。", []


async def answer_agent_question(
    provider_id: str, question: str, context: AdsWorkspacePayload
) -> tuple[str, list[str], str, str]:
    api_key, base_url, model = _provider_runtime(provider_id)
    if mock_ai_enabled() or not api_key or provider_id == "mock":
        answer, evidence = _local_question_answer(question, context)
        return answer, evidence, "local_rules", model or "rules"

    payload = {
        "workspace": context.model_dump(),
        "question": question,
        "instruction": "仅依据 workspace 回答。信息不足时明确说明，不得编造。返回简洁中文。",
    }
    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "你是 ADS 会议智能体，只能依据给定业务对象回答。"},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
            },
        )
        response.raise_for_status()
        answer = response.json()["choices"][0]["message"]["content"].strip()
    evidence = [
        item.id
        for collection in (
            context.projects,
            context.objectives,
            context.metrics,
            context.risks,
            context.tasks,
            context.policies,
        )
        for item in collection
        if getattr(item, "name", getattr(item, "title", "")) in answer
    ]
    return answer, evidence, "live", model


async def test_chat_completion(base_url: str, api_key: str, model: str) -> tuple[bool, str]:
    if not api_key:
        return False, "未配置 API Key"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "只回复 ok。"},
                        {"role": "user", "content": "连接测试"},
                    ],
                    "max_tokens": 8,
                },
            )
            response.raise_for_status()
        return True, "连接可用"
    except Exception as exc:
        return False, f"连接失败：{exc}"


async def build_model_analysis(payload: MeetingAnalysisRequest) -> MeetingAnalysis:
    if mock_ai_enabled() or payload.model_provider_id == "mock":
        return build_mock_analysis(payload)

    api_key, base_url, model = _provider_runtime(payload.model_provider_id)
    if not api_key:
        return build_mock_analysis(payload)

    system_prompt = build_system_prompt()
    context = _ads_context(payload)
    user_prompt = {
        "scenario": payload.scenario,
        "title": payload.title,
        "transcript": payload.transcript,
        "ads_context": {
            "name": context.name,
            "description": context.description,
            "people": [person.model_dump() for person in context.people],
            "objectives": [objective.model_dump() for objective in context.objectives],
            "tasks": [task.model_dump() for task in context.tasks],
            "projects": [item.model_dump() for item in context.projects],
            "metrics": [item.model_dump() for item in context.metrics],
            "risks": [item.model_dump() for item in context.risks],
            "policies": [item.model_dump() for item in context.policies],
            "historical_stances": [item.model_dump() for item in context.historical_stances],
            "authorization_rules": [rule.model_dump() for rule in context.authorization_rules],
        },
    }

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": str(user_prompt)},
                ],
            },
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        analysis = MeetingAnalysis.model_validate_json(content)
        analysis.prompt_version = PROMPT_VERSION
        return analysis
