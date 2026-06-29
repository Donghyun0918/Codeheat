// CodeHeat CLI가 내보내는 JSON 리포트 3종의 타입 + 화면용 병합 타입.
// (codeheat/models.py 의 to_dict 출력과 1:1 대응한다.)

export type Risk = "high" | "medium" | "low";

export interface Todo {
  line: number;
  text: string;
  age_days: number | null;
}

export interface SmellFile {
  file: string;
  complexity: number;
  avg_complexity: number;
  function_count: number;
  loc: number;
  todos: Todo[];
  duplication_ratio: number;
  oldest_todo_days: number | null;
}

export interface SmellReport {
  repo_path?: string;
  file_count?: number;
  files: SmellFile[];
}

export interface Contributor {
  name: string;
  score: number;
  commit_count: number;
  last_commit_days: number | null;
}

export interface OwnershipFile {
  file: string;
  total_commits: number;
  top_contributors: Contributor[];
}

export interface OwnershipReport {
  repo_path?: string;
  weighting?: string;
  files: OwnershipFile[];
}

export interface Insight {
  file: string;
  risk: Risk;
  reason: string;
  ask_who: string;
  ask_what: string;
}

export interface InsightsReport {
  backend?: string;
  model?: string;
  summary?: string;
  insights: Insight[];
}

export interface Reports {
  smell: SmellReport | null;
  ownership: OwnershipReport | null;
  insights: InsightsReport | null;
}

// 트리맵/디테일이 쓰는 파일 단위 병합 결과.
export interface MergedFile {
  path: string;
  complexity: number;
  avgComplexity: number;
  functionCount: number;
  loc: number;
  todos: Todo[];
  oldestTodoDays: number | null;
  duplicationRatio: number;
  topContributors: Contributor[];
  totalCommits: number | null;
  risk: Risk | null;
  reason: string | null;
  askWho: string | null;
  askWhat: string | null;
}
