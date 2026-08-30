export type DelegationDraft = {
  participation_mode: "self" | "delegate";
  agent_identity_id: string;
  authorization_rule_ids: string[];
  auto_reply_enabled: boolean;
};

export type RecurrenceFrequency = "none" | "weekly" | "biweekly" | "monthly";

const recurrenceLabels: Record<RecurrenceFrequency, string> = {
  none: "不重复",
  weekly: "每周",
  biweekly: "每两周",
  monthly: "每月",
};

export function getRecurrenceLabel(frequency: RecurrenceFrequency): string {
  return recurrenceLabels[frequency];
}

export function getRecurrenceError(
  frequency: RecurrenceFrequency,
  startAt: string,
  endDate: string,
): string | null {
  if (frequency === "none") return null;
  if (!endDate) return "请选择循环截止日期。";
  if (!startAt) return "请先选择开始时间。";

  const start = new Date(`${startAt.slice(0, 10)}T00:00:00`);
  const end = new Date(`${endDate}T00:00:00`);
  if (!Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime())) {
    return "请输入有效的循环截止日期。";
  }
  if (end < start) return "循环截止日期不能早于首次会议。";

  const maximumEnd = new Date(start.getFullYear() + 1, start.getMonth(), start.getDate());
  if (maximumEnd.getMonth() !== start.getMonth()) {
    maximumEnd.setDate(0);
  }
  if (end > maximumEnd) return "循环跨度不能超过一年。";
  return null;
}

export function getMeetingTimeRangeError(startAt: string, endAt: string): string | null {
  if (!startAt && !endAt) return "请选择开始和结束时间。";
  if (!startAt) return "请选择开始时间。";
  if (!endAt) return "请选择结束时间。";

  const start = new Date(startAt.replace(" ", "T")).getTime();
  const end = new Date(endAt.replace(" ", "T")).getTime();
  if (!Number.isFinite(start) || !Number.isFinite(end)) return "请输入有效的开始和结束时间。";
  if (end <= start) return "结束时间必须晚于开始时间。";

  const minutes = Math.round((end - start) / 60_000);
  if (minutes < 5) return "会议时长不能少于 5 分钟。";
  if (minutes > 480) return "会议时长不能超过 8 小时。";
  return null;
}

export function calculateDurationMinutes(startAt: string, endAt: string): number | null {
  if (getMeetingTimeRangeError(startAt, endAt)) return null;

  const start = new Date(startAt.replace(" ", "T")).getTime();
  const end = new Date(endAt.replace(" ", "T")).getTime();
  return Math.round((end - start) / 60_000);
}

export function getAgendaDurationError(
  agenda: Array<{ duration_minutes: number | null }>,
  durationMinutes: number,
): string | null {
  if (!agenda.length) return null;
  const total = agenda.reduce((sum, item) => sum + (item.duration_minutes ?? 0), 0);
  return total === durationMinutes
    ? null
    : `议程分钟合计必须等于会议时长 ${durationMinutes} 分钟。`;
}

export function normalizeParticipants(value: string): string[] {
  return [...new Set(value.split(/[、，,\n]/).map((item) => item.trim()).filter(Boolean))];
}

export function validateDelegationDraft(draft: DelegationDraft): string[] {
  if (draft.participation_mode === "self") {
    return draft.auto_reply_enabled
      ? ["只有委托智能体参会时可以开启授权内自动回复。"]
      : [];
  }

  const errors: string[] = [];
  if (!draft.agent_identity_id) errors.push("委托智能体时请选择代理身份。");
  if (!draft.authorization_rule_ids.length) errors.push("委托智能体时请至少选择一条本场授权。");
  return errors;
}
