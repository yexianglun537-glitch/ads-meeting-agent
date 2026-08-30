import assert from "node:assert/strict";
import test from "node:test";

import { isOldMeeting } from "../src/meetingCleanup.ts";

const now = new Date("2026-08-22T12:00:00+08:00");

test("marks finished and elapsed meetings as old", () => {
  assert.equal(isOldMeeting({ meeting_status: "closed", scheduled_at: "2026-08-23 09:00", duration_minutes: 60 }, now), true);
  assert.equal(isOldMeeting({ meeting_status: "scheduled", scheduled_at: "2026-08-22 09:00", duration_minutes: 60 }, now), true);
});

test("keeps upcoming and in-progress meetings out of cleanup", () => {
  assert.equal(isOldMeeting({ meeting_status: "scheduled", scheduled_at: "2026-08-23 09:00", duration_minutes: 60 }, now), false);
  assert.equal(isOldMeeting({ meeting_status: "in_progress", scheduled_at: "2026-08-22 09:00", duration_minutes: 60 }, now), false);
});
