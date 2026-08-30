import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  buildMetricReport,
  filterDashboardMetrics,
  findMeetingOverlapIds,
  isRecordingNavigationExit,
  searchProduct,
} from "../src/productCompletion.ts";

const mainSource = readFileSync(new URL("../src/main.tsx", import.meta.url), "utf8");

test("protects active recording when navigation leaves its meeting", () => {
  assert.equal(isRecordingNavigationExit("", "dashboard"), false);
  assert.equal(isRecordingNavigationExit("meeting-a", "meeting"), false);
  assert.equal(isRecordingNavigationExit("meeting-a", "meeting", "meeting-a"), false);
  assert.equal(isRecordingNavigationExit("meeting-a", "meeting", "meeting-b"), true);
  assert.equal(isRecordingNavigationExit("meeting-a", "decisions", "meeting-a"), true);
});

test("finds only active meetings whose time ranges overlap", () => {
  const overlaps = findMeetingOverlapIds([
    { id: "a", scheduled_at: "2026-08-25 09:00", duration_minutes: 60, meeting_status: "scheduled" },
    { id: "b", scheduled_at: "2026-08-25 09:30", duration_minutes: 60, meeting_status: "in_progress" },
    { id: "cancelled", scheduled_at: "2026-08-25 09:15", duration_minutes: 60, meeting_status: "cancelled" },
    { id: "closed", scheduled_at: "2026-08-25 09:15", duration_minutes: 60, meeting_status: "closed" },
  ]);

  assert.deepEqual([...overlaps].sort(), ["a", "b"]);
});

test("does not mark meetings that only touch at the boundary", () => {
  const overlaps = findMeetingOverlapIds([
    { id: "a", scheduled_at: "2026-08-25 09:00", duration_minutes: 60, meeting_status: "scheduled" },
    { id: "b", scheduled_at: "2026-08-25 10:00", duration_minutes: 60, meeting_status: "scheduled" },
  ]);

  assert.equal(overlaps.size, 0);
});

test("searches meetings decisions and every ADS document kind", () => {
  const documents = [
    { id: "meeting", kind: "会议", title: "稳定版收口" },
    { id: "decision", kind: "决策", title: "保留本地语音" },
    ...["成员", "项目", "目标", "指标", "风险", "任务", "制度", "历史立场", "授权"].map((kind, index) => ({
      id: `ads-${index}`,
      kind,
      title: `${kind}验收对象`,
      searchText: "统一检索词",
      workspaceId: "ws-1",
    })),
  ];

  assert.deepEqual(searchProduct("本地语音", documents).map((item) => item.kind), ["决策"]);
  assert.deepEqual(searchProduct("统一检索词", documents).map((item) => item.kind), ["成员", "项目", "目标", "指标", "风险", "任务", "制度", "历史立场", "授权"]);
});

test("exports reproducible workload baselines as markdown", () => {
  const report = buildMetricReport([
    {
      id: "baseline-1",
      meeting_id: "meeting-1",
      meeting_type: "项目进度同步",
      baseline_minutes: 40,
      post_process_minutes: 10,
      sample_date: "2026-08-25",
      source: "现场计时",
      notes: "同一材料人工与系统处理",
    },
  ]);

  assert.match(report, /项目进度同步/);
  assert.match(report, /40\.0/);
  assert.match(report, /10\.0/);
  assert.match(report, /75\.0%/);
  assert.match(report, /现场计时/);
  assert.match(report, /\(人工处理分钟 - 系统后处理分钟\)/);
});

test("filters dashboard metrics by workspace and date range", () => {
  const scoped = filterDashboardMetrics(
    [
      { id: "meeting-a-august", workspace_id: "ws-a", scheduled_at: "2026-08-15 09:00" },
      { id: "meeting-b-august", workspace_id: "ws-b", scheduled_at: "2026-08-15 09:00" },
      { id: "meeting-a-july", workspace_id: "ws-a", scheduled_at: "2026-07-31 09:00" },
    ],
    [
      { id: "baseline-a-august", meeting_id: "meeting-a-august", meeting_type: "项目进度同步", baseline_minutes: 40, post_process_minutes: 10, sample_date: "2026-08-15", source: "现场计时" },
      { id: "baseline-b-august", meeting_id: "meeting-b-august", meeting_type: "项目进度同步", baseline_minutes: 30, post_process_minutes: 12, sample_date: "2026-08-15", source: "现场计时" },
      { id: "baseline-a-july", meeting_id: "meeting-a-july", meeting_type: "项目进度同步", baseline_minutes: 20, post_process_minutes: 8, sample_date: "2026-07-31", source: "现场计时" },
      { id: "baseline-a-september", meeting_id: "meeting-a-august", meeting_type: "项目进度同步", baseline_minutes: 50, post_process_minutes: 15, sample_date: "2026-09-01", source: "现场计时" },
      { id: "baseline-orphan", meeting_id: "missing", meeting_type: "项目进度同步", baseline_minutes: 10, post_process_minutes: 5, sample_date: "2026-08-20", source: "现场计时" },
    ],
    "ws-a",
    "2026-08-01",
    "2026-08-31",
  );

  assert.deepEqual(scoped.meetings.map((item) => item.id), ["meeting-a-august"]);
  assert.deepEqual(scoped.baselines.map((item) => item.id), ["baseline-a-august"]);

  const inScopeMeeting = [{ id: "meeting-a-august", workspace_id: "ws-a", scheduled_at: "2026-08-15 09:00" }];
  assert.deepEqual(filterDashboardMetrics(inScopeMeeting, [], ""), { meetings: [], baselines: [] });
  assert.deepEqual(filterDashboardMetrics(inScopeMeeting, [], "ws-a", "2026-09-01", "2026-08-01"), { meetings: [], baselines: [] });
});

test("meeting detail exposes information and agenda editing with explicit scopes", () => {
  assert.match(mainSource, /编辑会议信息/);
  assert.match(mainSource, /\/api\/meetings\/\$\{meetingId\}\?scope=\$\{scope\}/);
  assert.match(mainSource, /\/api\/meetings\/\$\{meetingId\}\/agenda/);
  assert.match(mainSource, /重新生成并覆盖/);
  assert.match(mainSource, /agenda-edit-dialog/);
});
