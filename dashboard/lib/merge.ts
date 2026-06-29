// smell(필수) + ownership/insights(선택)를 파일 경로 기준으로 병합한다.
// codeheat/insights.py 의 load_and_merge 와 같은 규칙: smell의 복잡도 내림차순
// 순서를 보존하고, 경로가 안 맞으면 basename으로 폴백 매칭한다.

import type {
  InsightsReport,
  MergedFile,
  OwnershipReport,
  Reports,
  SmellReport,
} from "./types";

function basename(path: string): string {
  const parts = path.split("/");
  return parts[parts.length - 1] || path;
}

// 경로 정확매칭 우선, 없으면 basename 폴백으로 찾는 인덱스.
function makeLookup<T>(items: T[], keyOf: (t: T) => string) {
  const byFull = new Map<string, T>();
  const byBase = new Map<string, T>();
  for (const it of items) {
    const k = keyOf(it);
    byFull.set(k, it);
    // 같은 basename이 여럿이면 첫 항목만(모호하면 폴백 안 함이 안전하나 단순화).
    if (!byBase.has(basename(k))) byBase.set(basename(k), it);
  }
  return (path: string): T | undefined =>
    byFull.get(path) ?? byBase.get(basename(path));
}

export function mergeReports(
  smell: SmellReport,
  ownership: OwnershipReport | null,
  insights: InsightsReport | null,
): MergedFile[] {
  const ownLookup = makeLookup(ownership?.files ?? [], (f) => f.file);
  const insLookup = makeLookup(insights?.insights ?? [], (i) => i.file);

  return smell.files.map((f) => {
    const own = ownLookup(f.file);
    const ins = insLookup(f.file);
    return {
      path: f.file,
      complexity: f.complexity,
      avgComplexity: f.avg_complexity,
      functionCount: f.function_count,
      loc: f.loc,
      todos: f.todos ?? [],
      oldestTodoDays: f.oldest_todo_days,
      duplicationRatio: f.duplication_ratio ?? 0,
      topContributors: own?.top_contributors ?? [],
      totalCommits: own?.total_commits ?? null,
      risk: ins?.risk ?? null,
      reason: ins?.reason ?? null,
      askWho: ins?.ask_who ?? null,
      askWhat: ins?.ask_what ?? null,
    };
  });
}

export function mergeFromReports(reports: Reports): MergedFile[] {
  if (!reports.smell) return [];
  return mergeReports(reports.smell, reports.ownership, reports.insights);
}

// 업로드된 임의 JSON이 어떤 리포트인지 모양으로 판별한다.
export type ReportKind = "smell" | "ownership" | "insights" | "unknown";

export function classifyReport(obj: unknown): ReportKind {
  if (!obj || typeof obj !== "object") return "unknown";
  const o = obj as Record<string, unknown>;
  if (Array.isArray(o.insights)) return "insights";
  if ("weighting" in o) return "ownership";
  if (Array.isArray(o.files)) {
    const first = (o.files as unknown[])[0] as Record<string, unknown> | undefined;
    if (first && "top_contributors" in first) return "ownership";
    if (first && "complexity" in first) return "smell";
    // 빈 files: file_count가 있으면 smell로 본다.
    if ("file_count" in o) return "smell";
  }
  return "unknown";
}
