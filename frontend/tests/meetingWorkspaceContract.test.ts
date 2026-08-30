import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("../src/main.tsx", import.meta.url), "utf8");
const styles = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");

function block(startText: string, endText: string) {
  const start = source.indexOf(startText);
  const end = source.indexOf(endText, start + startText.length);
  return start >= 0 && end > start ? source.slice(start, end) : "";
}

test("meeting workspace renders only the main meeting surface", () => {
  const workspace = block("function MeetingWorkspace(", "function ViewHeading(");
  assert.doesNotMatch(workspace, /<AgentPanel/);
  assert.doesNotMatch(workspace, /models: ModelConfig|aiRuntime:|onSelectModel:|onAskAgent:/);
});

test("meeting content uses the full released width", () => {
  assert.match(styles, /\.meeting-stage\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1fr\)/s);
  assert.match(styles, /\.meeting-surface\s*\{[^}]*width:\s*100%/s);
  assert.doesNotMatch(styles, /\.agent-panel\s*\{/);
});

test("pending escalation disables every action-item writeback path", () => {
  const results = block("function Results(", "function WorkloadMetricsCard(");
  assert.match(results, /const awaitingDecision = props\.meeting\.status !== "confirmed"/);
  assert.match(results, /awaitingDecision \? "待本人确认"/);
  assert.match(results, /disabled=\{awaitingDecision \|\| writtenBack \|\| incomplete/);
});

test("missing action-item fields stay empty instead of showing invented defaults", () => {
  const results = block("function Results(", "function WorkloadMetricsCard(");
  assert.doesNotMatch(results, /defaultOwner|2026-08-23/);
  assert.match(results, /defaultValue=\{item\.owner_id \?\? ""\}/);
  assert.match(results, /defaultValue=\{item\.due_date \?\? ""\}/);
});

test("incomplete action items disable bulk writeback", () => {
  const results = block("function Results(", "function WorkloadMetricsCard(");
  assert.match(results, /const hasIncompleteItems = analysis\.action_items\.some\(\(item\) => item\.status === "incomplete"\)/);
  assert.match(results, /disabled=\{awaitingDecision \|\| hasIncompleteItems \|\| props\.busy === "writeback"\}/);
});
