export type MeetingSchedule = {
  id: string;
  scheduled_at: string;
  duration_minutes: number;
  meeting_status: string;
  status?: string;
};

export type ProductSearchDocument = {
  id: string;
  kind: string;
  title: string;
  searchText?: string;
  workspaceId?: string;
  meetingId?: string;
};

export type MetricBaselineRecord = {
  id: string;
  meeting_id: string;
  meeting_type: string;
  baseline_minutes: number;
  post_process_minutes: number;
  sample_date: string;
  source: string;
  notes?: string;
};

export type DashboardMetricMeeting = {
  id: string;
  workspace_id?: string | null;
  scheduled_at: string;
};

export function isRecordingNavigationExit(recordingMeetingId: string, nextView: string, nextMeetingId?: string): boolean {
  return Boolean(recordingMeetingId && (nextView !== "meeting" || Boolean(nextMeetingId && nextMeetingId !== recordingMeetingId)));
}

export function findMeetingOverlapIds(meetings: MeetingSchedule[]): Set<string> {
  const active = meetings
    .filter((meeting) => !["ended", "closed", "cancelled"].includes(meeting.meeting_status) && meeting.status !== "completed")
    .map((meeting) => {
      const start = Date.parse(meeting.scheduled_at.replace(" ", "T"));
      return { ...meeting, start, end: start + meeting.duration_minutes * 60_000 };
    })
    .filter((meeting) => Number.isFinite(meeting.start) && meeting.duration_minutes > 0);
  const overlaps = new Set<string>();
  for (let left = 0; left < active.length; left += 1) {
    for (let right = left + 1; right < active.length; right += 1) {
      if (active[left].start < active[right].end && active[right].start < active[left].end) {
        overlaps.add(active[left].id);
        overlaps.add(active[right].id);
      }
    }
  }
  return overlaps;
}

export function searchProduct(query: string, documents: ProductSearchDocument[], limit = 20): ProductSearchDocument[] {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return [];
  return documents
    .filter((document) => `${document.title} ${document.searchText ?? ""}`.toLowerCase().includes(normalized))
    .slice(0, limit);
}

export function savingsPercent(baselineMinutes: number, postProcessMinutes: number): number {
  return Math.round(((baselineMinutes - postProcessMinutes) / baselineMinutes) * 1000) / 10;
}

export function filterDashboardMetrics<T extends DashboardMetricMeeting>(
  meetings: T[],
  baselines: MetricBaselineRecord[],
  workspaceId: string,
  startDate = "",
  endDate = "",
) {
  if (!workspaceId || (startDate && endDate && startDate > endDate)) return { meetings: [], baselines: [] };
  const inRange = (value: string) => (
    (!startDate || value.slice(0, 10) >= startDate)
    && (!endDate || value.slice(0, 10) <= endDate)
  );
  const scopedMeetings = meetings.filter((meeting) => meeting.workspace_id === workspaceId && inRange(meeting.scheduled_at));
  const meetingIds = new Set(scopedMeetings.map((meeting) => meeting.id));
  return {
    meetings: scopedMeetings,
    baselines: baselines.filter((baseline) => meetingIds.has(baseline.meeting_id) && inRange(baseline.sample_date)),
  };
}

export function buildMetricReport(baselines: MetricBaselineRecord[]): string {
  const rows = baselines.map((item) =>
    `| ${item.sample_date} | ${item.meeting_type} | ${item.meeting_id} | ${item.baseline_minutes.toFixed(1)} | ${item.post_process_minutes.toFixed(1)} | ${savingsPercent(item.baseline_minutes, item.post_process_minutes).toFixed(1)}% | ${item.source} | ${item.notes ?? ""} |`,
  );
  return [
    "# ADS 会议智能体减负指标报告",
    "",
    `样本数：${baselines.length}`,
    "",
    "| 日期 | 会议类型 | 会议 ID | 人工处理分钟 | 系统后处理分钟 | 节省比例 | 来源 | 说明 |",
    "| --- | --- | --- | ---: | ---: | ---: | --- | --- |",
    ...(rows.length ? rows : ["| — | — | — | — | — | — | — | 暂无人工基准 |"]),
    "",
    "计算公式：节省比例 = (人工处理分钟 - 系统后处理分钟) / 人工处理分钟 × 100%。",
    "",
    "人工基准必须来自实际计时，不根据字符数或主观感觉推算。",
  ].join("\n");
}
