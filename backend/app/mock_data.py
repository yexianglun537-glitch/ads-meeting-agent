from app.models import AuthorizationRule, Objective, Person, Task


PEOPLE = [
    Person(id="p_zhang", name="张伟", role="项目负责人"),
    Person(id="p_li", name="李娜", role="前端负责人"),
    Person(id="p_wang", name="王强", role="后端负责人"),
    Person(id="p_chen", name="陈敏", role="测试负责人"),
]

OBJECTIVES = [
    Objective(
        id="obj_demo",
        title="完成 ADS 会议智能体首个可用版本",
        progress=62,
        metric="会议任务闭环完成率达到 100%",
        risk="会议输入和 ADS 回写之间的数据结构需要稳定",
    ),
    Objective(
        id="obj_quality",
        title="保证系统稳定性和决策可追溯性",
        progress=48,
        metric="核心流程可复现，关键决策有来源",
        risk="模型输出不稳定时需要本地规则和人工确认",
    ),
]

TASKS = [
    Task(
        id="task_data_model",
        title="确认 Meeting/Topic/Decision/Task 的 ADS 字段",
        owner_id="p_zhang",
        due_date="2026-08-12",
        status="进行中",
    ),
    Task(
        id="task_ui",
        title="完成项目周例会工作区",
        owner_id="p_li",
        due_date="2026-08-14",
        status="未开始",
    ),
    Task(
        id="task_backend",
        title="实现会议分析 API 和模型适配层",
        owner_id="p_wang",
        due_date="2026-08-13",
        status="进行中",
    ),
]

AUTHORIZATION_RULES = [
    AuthorizationRule(
        id="auth_zhang_weekly",
        person_id="p_zhang",
        scope="项目周例会中，允许确认既定排期、解释已有任务状态、要求补充风险信息",
        allowed_actions=["provide_info", "confirm_existing_plan", "request_risk_update"],
        escalation_triggers=["新增预算", "延期超过 3 天", "变更验收范围", "替换技术路线"],
    )
]
