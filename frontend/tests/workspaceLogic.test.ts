import assert from "node:assert/strict";
import test from "node:test";

import { findWorkspaceObject, sortDecisionQueue } from "../src/workspaceLogic.ts";

test("finds an ADS object by id without falling back to unrelated data", () => {
  const workspace = {
    people: [{ id: "person_1", name: "张伟" }],
    projects: [{ id: "project_1", name: "桌面产品" }],
    objectives: [], metrics: [], risks: [], tasks: [], policies: [], historical_stances: [], authorization_rules: [],
  };
  assert.deepEqual(findWorkspaceObject(workspace, "project_1"), { tab: "projects", index: 0 });
  assert.equal(findWorkspaceObject(workspace, "missing"), null);
});

test("sorts decisions by pending state, deadline, then creation time", () => {
  const decisions = [
    { status: "deferred", reply_deadline: "2026-08-22T08:00:00+08:00", created_at: "2026-08-22T07:00:00+08:00" },
    { status: "pending", reply_deadline: null, created_at: "2026-08-22T06:00:00+08:00" },
    { status: "pending", reply_deadline: "2026-08-22T09:00:00+08:00", created_at: "2026-08-22T05:00:00+08:00" },
    { status: "pending", reply_deadline: "2026-08-22T08:00:00+08:00", created_at: "2026-08-22T07:30:00+08:00" },
  ];
  const sorted = sortDecisionQueue(decisions);
  assert.deepEqual(sorted.map((item) => item.reply_deadline), [
    "2026-08-22T08:00:00+08:00",
    "2026-08-22T09:00:00+08:00",
    null,
    "2026-08-22T08:00:00+08:00",
  ]);
});
