// CodeHeat CLI 리포트(JSON) 로드 + 파일 기준 병합.
// codeheat/insights.py 의 load_and_merge 와 같은 규칙(경로→basename 폴백)을 따른다.

import * as fs from "fs";
import * as path from "path";

export type Risk = "high" | "medium" | "low";

export interface Todo {
  line: number;
  text: string;
  age_days: number | null;
}

export interface MergedFile {
  /** 리포트에 기록된 원본 경로 (절대 또는 상대). */
  path: string;
  /** 워크스페이스 루트 기준 상대경로(매칭/열기용으로 정규화). */
  rel: string;
  complexity: number;
  avgComplexity: number;
  functionCount: number;
  loc: number;
  todos: Todo[];
  oldestTodoDays: number | null;
  topContributors: { name: string; score: number; commit_count: number; last_commit_days: number | null }[];
  totalCommits: number | null;
  risk: Risk | null;
  reason: string | null;
  askWho: string | null;
  askWhat: string | null;
}

function readJson(p: string): any | null {
  try {
    if (!fs.existsSync(p)) return null;
    return JSON.parse(fs.readFileSync(p, "utf-8"));
  } catch {
    return null;
  }
}

function resolvePath(root: string, configured: string): string {
  return path.isAbsolute(configured) ? configured : path.join(root, configured);
}

function basename(p: string): string {
  return p.split(/[\\/]/).pop() || p;
}

function makeLookup<T>(items: T[], keyOf: (t: T) => string) {
  const byFull = new Map<string, T>();
  const byBase = new Map<string, T>();
  for (const it of items) {
    const k = keyOf(it);
    byFull.set(k, it);
    if (!byBase.has(basename(k))) byBase.set(basename(k), it);
  }
  return (p: string): T | undefined => byFull.get(p) ?? byBase.get(basename(p));
}

export interface LoadResult {
  files: MergedFile[];
  loaded: { smell: boolean; ownership: boolean; insights: boolean };
}

export function loadReports(
  root: string,
  cfg: { smell: string; ownership: string; insights: string },
): LoadResult {
  const smell = readJson(resolvePath(root, cfg.smell));
  const ownership = readJson(resolvePath(root, cfg.ownership));
  const insights = readJson(resolvePath(root, cfg.insights));

  const loaded = {
    smell: !!smell,
    ownership: !!ownership,
    insights: !!insights,
  };
  if (!smell || !Array.isArray(smell.files)) return { files: [], loaded };

  const ownLookup = makeLookup<any>(ownership?.files ?? [], (f) => f.file);
  const insLookup = makeLookup<any>(insights?.insights ?? [], (i) => i.file);

  const files: MergedFile[] = smell.files.map((f: any) => {
    const own = ownLookup(f.file);
    const ins = insLookup(f.file);
    const rel = path.isAbsolute(f.file)
      ? path.relative(root, f.file)
      : f.file;
    return {
      path: f.file,
      rel: rel.split(path.sep).join("/"),
      complexity: f.complexity ?? 0,
      avgComplexity: f.avg_complexity ?? 0,
      functionCount: f.function_count ?? 0,
      loc: f.loc ?? 0,
      todos: f.todos ?? [],
      oldestTodoDays: f.oldest_todo_days ?? null,
      topContributors: own?.top_contributors ?? [],
      totalCommits: own?.total_commits ?? null,
      risk: ins?.risk ?? null,
      reason: ins?.reason ?? null,
      askWho: ins?.ask_who ?? null,
      askWhat: ins?.ask_what ?? null,
    };
  });

  // 복잡도(온도) 내림차순 — 가장 뜨거운 파일이 위로.
  files.sort((a, b) => b.complexity - a.complexity);
  return { files, loaded };
}
