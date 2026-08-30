export type WorkspaceObjectTab = "people" | "projects" | "objectives" | "metrics" | "risks" | "tasks" | "policies" | "historical_stances" | "authorization";

type Identified = { id: string };
type WorkspaceObjects = {
  people: Identified[]; projects: Identified[]; objectives: Identified[]; metrics: Identified[];
  risks: Identified[]; tasks: Identified[]; policies: Identified[]; historical_stances: Identified[];
  authorization_rules: Identified[];
};

const objectTabs: Array<[WorkspaceObjectTab, keyof WorkspaceObjects]> = [
  ["people", "people"], ["projects", "projects"], ["objectives", "objectives"], ["metrics", "metrics"],
  ["risks", "risks"], ["tasks", "tasks"], ["policies", "policies"], ["historical_stances", "historical_stances"],
  ["authorization", "authorization_rules"],
];

export function findWorkspaceObject(workspace: WorkspaceObjects, objectId: string) {
  for (const [tab, key] of objectTabs) {
    const index = workspace[key].findIndex((item) => item.id === objectId);
    if (index >= 0) return { tab, index };
  }
  return null;
}

type DecisionQueueItem = { status: string; reply_deadline?: string | null; created_at: string };

export function sortDecisionQueue<T extends DecisionQueueItem>(items: T[]): T[] {
  const dateValue = (value?: string | null) => value ? Date.parse(value) : Number.POSITIVE_INFINITY;
  return [...items].sort((left, right) =>
    Number(right.status === "pending") - Number(left.status === "pending")
    || dateValue(left.reply_deadline) - dateValue(right.reply_deadline)
    || dateValue(left.created_at) - dateValue(right.created_at));
}
