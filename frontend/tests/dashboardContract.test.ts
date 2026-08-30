import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("../src/main.tsx", import.meta.url), "utf8");

function block(startText: string, endText: string) {
  const start = source.indexOf(startText);
  const end = source.indexOf(endText, start + startText.length);
  return start >= 0 && end > start ? source.slice(start, end) : "";
}

test("top bar no longer exposes model selection", () => {
  const topbar = block("function Topbar(", "function Dashboard(");
  assert.doesNotMatch(topbar, /model-switch/);
  assert.doesNotMatch(topbar, /当前模型/);
  assert.doesNotMatch(topbar, /props\.models|props\.defaultModel|props\.onSelectModel/);
});

test("dashboard uses the approved copy and no longer contains workload metrics", () => {
  const dashboard = block("function Dashboard(", "function DataDashboard(");
  assert.match(dashboard, /开始你的会议/);
  assert.match(dashboard, /已完成会议/);
  assert.doesNotMatch(dashboard, /WorkloadImpactPanel/);
});

test("workload metrics live in a dedicated data dashboard", () => {
  const dataDashboard = block("function DataDashboard(", "function WorkloadImpactPanel(");
  assert.match(source, /type View = [^;]*"metrics"/);
  assert.match(source, /\["metrics", <Gauge[^\]]*"数据看板"\]/);
  assert.match(source, /view === "metrics" && <DataDashboard/);
  assert.match(dataDashboard, /WorkloadImpactPanel/);
});

test("dashboard scope is explicit and links to metric baseline entry", () => {
  const dataDashboard = block("function DataDashboard(", "function WorkloadImpactPanel(");
  const workloadPanel = block("function WorkloadImpactPanel(", "function CalendarView(");
  assert.match(dataDashboard, /filterDashboardMetrics/);
  assert.match(dataDashboard, /业务工作区/);
  assert.match(dataDashboard, /开始日期/);
  assert.match(dataDashboard, /结束日期/);
  assert.match(dataDashboard, /指标口径/);
  assert.match(dataDashboard, /录入人工基准/);
  assert.doesNotMatch(workloadPanel, /统计周期：当前工作区/);
  assert.match(source, /id="metric-baseline"/);
});
