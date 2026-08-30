# ADS 核心 Prompt 与工作流说明

版本：`meeting-agent.v1`

## 1. 适用范围

本文对应本地会议工作台的会议分析链路。程序实际加载的系统 Prompt 位于：

`backend/app/prompt_templates.py`

调用入口位于：

`backend/app/ai.py::build_model_analysis`

模型输出在进入会议状态机前，使用 `backend/app/models.py` 的 Pydantic 模型校验；服务端随后覆盖可由系统记录证明的指标字段，避免模型生成生产指标。

## 2. 智能体边界

- 只能读取本次会议提交的发言和选定 ADS 工作区。
- 只能引用工作区中的人员、目标、任务、风险和授权规则。
- 信息不足、授权不清、目标冲突或命中升级条件时，生成独立的待本人确认事项。
- 超权事项不能自动回复、执行或写回；其他授权内发言仍可继续分析。
- 负责人或截止日期缺失的行动项保持不完整状态，禁止自动写回。
- 不生成或展示 API Key、会议外部平台凭据和未提供的业务事实。

## 3. 输入模板

服务端向在线模型提交以下字段：

```json
{
  "scenario": "会议",
  "title": "会议名称",
  "transcript": "发言人：会议内容",
  "ads_context": {
    "name": "工作区名称",
    "description": "工作区说明",
    "people": [],
    "objectives": [],
    "tasks": [],
    "authorization_rules": []
  }
}
```

本地规则模式使用相同的输入契约，不调用在线模型。输入中的 ADS 上下文来自当前选择的工作区，不使用界面预存的演示内容覆盖用户输入。

## 4. 输出与校验

输出契约见 `docs/workflows/meeting-analysis-output.schema.json`。重点约束如下：

1. `transcript_turns` 必须保留发言原文和关联对象 ID。
2. `decisions` 和 `action_items` 必须提供证据关系；无法确认的负责人和日期保持 `null`。
3. `agent_replies.decision` 只允许 `answer`、`confirm`、`escalate`。
4. `escalate` 会进入独立的决策中心事项，不把整场会议改成暂停状态。
5. `metrics` 只记录字符数、行动项数量、升级数量等服务端可复核值；人工基准和节省比例在没有采集材料时保持 `null`。

## 5. 工作流与人机确认点

工作流文件见 `docs/workflows/meeting-agent-workflow.yaml`。

主链路：

```text
创建会议
→ 读取 ADS 工作区
→ 生成会前简报
→ 本人参加或确认委托
→ 接收文字或本地音频转写
→ 审核并确认转写
→ 分析发言与授权
→ 授权内继续处理 / 超权事项单独升级
→ 本人同意、修改或拒绝
→ 生成纪要与行动项
→ 补全负责人和截止日期
→ 写回 ADS
→ 保存来源链和审计记录
```

人机确认点：

- 委托智能体前确认本场授权范围。
- 音频转写后确认文本再进入分析。
- 超权事项可同意、修改或拒绝，处理结果返回原会议。
- 行动项信息不完整时由本人补全，确认后才能写回。

## 6. 降级与禁止自动执行

- 在线模型未配置、连接失败或返回结构不合法时，使用本地规则模式并在运行状态中标明。
- 本地音频组件不可用时，保留文字输入入口，不伪造转写成功。
- 任意校验失败、授权校验失败或待确认事项未处理时，禁止写回 ADS。
- `prompt_version` 会写入分析结果，便于审计本次请求实际使用的 Prompt 版本。

## 7. 验证材料

- 后端工作流测试：`backend/tests/test_workflow.py`
- 输出契约：`docs/workflows/meeting-analysis-output.schema.json`
- 工作流分支：`docs/workflows/meeting-agent-workflow.yaml`
- 真实会议材料的人工基准尚未采集，因此 UI 不能展示节省百分比。
