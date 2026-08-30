import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("../src/main.tsx", import.meta.url), "utf8");

test("meeting workspace exposes explicit lifecycle controls", () => {
  assert.match(source, /\/api\/meetings\/\$\{activeMeeting\.id\}\/lifecycle/);
  assert.match(source, />开始会议</);
  assert.match(source, />结束会议</);
  assert.match(source, />重新打开会议</);
});

test("meeting progress and outcome labels are separate", () => {
  assert.match(source, /meetingLifecycleText/);
  assert.match(source, /meetingOutcomeText/);
  assert.match(source, />会议进程</);
  assert.match(source, />成果\/写回</);
});

test("live input requires an explicitly active meeting", () => {
  assert.match(source, /meetingActive = props\.meeting\.meeting_status === "in_progress"/);
  assert.match(source, /meetingActive && workflowReady/);
  assert.match(source, /如需继续记录，请先重新打开会议/);
});
