import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  calculateDurationMinutes,
  getMeetingTimeRangeError,
  getAgendaDurationError,
  getRecurrenceError,
  getRecurrenceLabel,
  normalizeParticipants,
  validateDelegationDraft,
} from "../src/meetingDraft.ts";

const mainSource = readFileSync(new URL("../src/main.tsx", import.meta.url), "utf8");

test("calculates meeting duration from the selected start and end times", () => {
  assert.equal(calculateDurationMinutes("2026-08-20 14:00", "2026-08-20 14:45"), 45);
});

test("rejects missing, reversed, and out-of-range meeting times", () => {
  assert.equal(calculateDurationMinutes("", "2026-08-20 14:45"), null);
  assert.equal(calculateDurationMinutes("2026-08-20 15:00", "2026-08-20 14:45"), null);
  assert.equal(calculateDurationMinutes("2026-08-20 14:00", "2026-08-21 14:00"), null);
});

test("explains why a meeting time range cannot be submitted", () => {
  assert.equal(getMeetingTimeRangeError("", ""), "请选择开始和结束时间。");
  assert.equal(getMeetingTimeRangeError("2026-08-23 10:00", ""), "请选择结束时间。");
  assert.equal(
    getMeetingTimeRangeError("2026-08-23 10:00", "2026-08-23 09:30"),
    "结束时间必须晚于开始时间。",
  );
  assert.equal(
    getMeetingTimeRangeError("2026-08-23 10:00", "2026-08-23 10:03"),
    "会议时长不能少于 5 分钟。",
  );
  assert.equal(
    getMeetingTimeRangeError("2026-08-23 10:00", "2026-08-23 18:01"),
    "会议时长不能超过 8 小时。",
  );
  assert.equal(getMeetingTimeRangeError("2026-08-23 10:00", "2026-08-23 10:30"), null);
});

test("normalizes participant separators, duplicates, and blank values", () => {
  assert.deepEqual(
    normalizeParticipants(" 张伟、李娜，王强, 张伟\n\n陈敏 "),
    ["张伟", "李娜", "王强", "陈敏"],
  );
});

test("requires explicit identity and authorization for delegated meetings", () => {
  assert.deepEqual(
    validateDelegationDraft({
      participation_mode: "delegate",
      agent_identity_id: "",
      authorization_rule_ids: [],
      auto_reply_enabled: false,
    }),
    ["委托智能体时请选择代理身份。", "委托智能体时请至少选择一条本场授权。"],
  );
  assert.deepEqual(
    validateDelegationDraft({
      participation_mode: "delegate",
      agent_identity_id: "p_zhang",
      authorization_rule_ids: ["auth_default"],
      auto_reply_enabled: true,
    }),
    [],
  );
});

test("self attendance does not require delegation and cannot auto reply", () => {
  assert.deepEqual(
    validateDelegationDraft({
      participation_mode: "self",
      agent_identity_id: "",
      authorization_rule_ids: [],
      auto_reply_enabled: false,
    }),
    [],
  );
  assert.deepEqual(
    validateDelegationDraft({
      participation_mode: "self",
      agent_identity_id: "p_zhang",
      authorization_rule_ids: ["auth_default"],
      auto_reply_enabled: true,
    }),
    ["只有委托智能体参会时可以开启授权内自动回复。"],
  );
});

test("recurring meeting requires a valid end date within one year", () => {
  assert.equal(getRecurrenceError("none", "2026-09-01 09:00", ""), null);
  assert.equal(getRecurrenceError("weekly", "2026-09-01 09:00", ""), "请选择循环截止日期。");
  assert.equal(
    getRecurrenceError("weekly", "2026-09-01 09:00", "2026-08-31"),
    "循环截止日期不能早于首次会议。",
  );
  assert.equal(
    getRecurrenceError("monthly", "2026-09-01 09:00", "2027-09-02"),
    "循环跨度不能超过一年。",
  );
});

test("uses stable Chinese labels for recurrence frequencies", () => {
  assert.equal(getRecurrenceLabel("none"), "不重复");
  assert.equal(getRecurrenceLabel("weekly"), "每周");
  assert.equal(getRecurrenceLabel("biweekly"), "每两周");
  assert.equal(getRecurrenceLabel("monthly"), "每月");
});

test("meeting UI submits recurrence and offers explicit series deletion scopes", () => {
  assert.match(mainSource, /recurrence_frequency/);
  assert.match(mainSource, /recurrence_end_date/);
  assert.match(mainSource, /recurrence:\s*\{/);
  assert.match(mainSource, />仅本次</);
  assert.match(mainSource, /本次及后续/);
  assert.match(mainSource, /scope=\$\{scope\}/);
});

test("meeting creation uses one content field and an editable AI agenda preview", () => {
  assert.match(mainSource, />会议内容</);
  assert.match(mainSource, /AI 自动整理/);
  assert.match(mainSource, /agenda-draft-preview/);
  assert.match(mainSource, /\/api\/agenda\/draft/);
  assert.doesNotMatch(mainSource, /<label>会议目标/);
  assert.doesNotMatch(mainSource, /<label>议程/);
});

test("successful meeting creation clears the previous meeting draft", () => {
  assert.match(mainSource, /setDraft\(\{\s*\.\.\.initialDraft,\s*workspace_id:/);
});

test("editable agenda must still match the meeting duration", () => {
  assert.equal(getAgendaDurationError([{ duration_minutes: 20 }, { duration_minutes: 25 }], 45), null);
  assert.equal(
    getAgendaDurationError([{ duration_minutes: 20 }, { duration_minutes: 20 }], 45),
    "议程分钟合计必须等于会议时长 45 分钟。",
  );
});
