type MeetingForCleanup = {
  meeting_status: string;
  scheduled_at: string;
  duration_minutes: number;
};

export function isOldMeeting(meeting: MeetingForCleanup, now = new Date()): boolean {
  if (["ended", "closed", "cancelled"].includes(meeting.meeting_status)) return true;
  if (meeting.meeting_status === "in_progress") return false;
  const startsAt = Date.parse(meeting.scheduled_at.replace(" ", "T"));
  return Number.isFinite(startsAt) && startsAt + meeting.duration_minutes * 60_000 <= now.getTime();
}
