import * as path from "path";
import * as vscode from "vscode";
import { loadReports, type MergedFile } from "./reports";

// 복잡도 비율 → 온도 색(VS Code 내장 chart 색). 빨갈수록 뜨겁다.
function heatColor(complexity: number, max: number): vscode.ThemeColor {
  const t = Math.min(complexity / Math.max(max, 10), 1);
  if (t >= 0.66) return new vscode.ThemeColor("charts.red");
  if (t >= 0.33) return new vscode.ThemeColor("charts.orange");
  if (t > 0) return new vscode.ThemeColor("charts.yellow");
  return new vscode.ThemeColor("charts.green");
}

function riskLabel(risk: string | null): string {
  return risk === "high" ? "높음" : risk === "medium" ? "보통" : risk === "low" ? "낮음" : "—";
}

export class HeatProvider implements vscode.TreeDataProvider<MergedFile> {
  private _onDidChange = new vscode.EventEmitter<void>();
  readonly onDidChangeTreeData = this._onDidChange.event;

  private files: MergedFile[] = [];
  private byRel = new Map<string, MergedFile>();
  private maxCx = 0;
  loaded = { smell: false, ownership: false, insights: false };

  get max(): number {
    return this.maxCx;
  }

  private root(): string | undefined {
    return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  }

  load(): void {
    const root = this.root();
    if (!root) {
      this.files = [];
    } else {
      const cfg = vscode.workspace.getConfiguration("codeheat");
      const result = loadReports(root, {
        smell: cfg.get<string>("smellReportPath", "smell_report.json"),
        ownership: cfg.get<string>("ownershipReportPath", "ownership_report.json"),
        insights: cfg.get<string>("insightsReportPath", "insights_report.json"),
      });
      this.files = result.files;
      this.loaded = result.loaded;
    }
    this.maxCx = this.files.reduce((m, f) => Math.max(m, f.complexity), 0);
    this.byRel = new Map(this.files.map((f) => [f.rel, f]));
    vscode.commands.executeCommand("setContext", "codeheat.hasData", this.files.length > 0);
    this._onDidChange.fire();
  }

  /** 워크스페이스 상대경로(슬래시)로 파일 메타 조회. basename 폴백 포함. */
  lookup(rel: string): MergedFile | undefined {
    const norm = rel.split(path.sep).join("/");
    if (this.byRel.has(norm)) return this.byRel.get(norm);
    const base = norm.split("/").pop();
    return this.files.find((f) => f.rel.split("/").pop() === base);
  }

  getChildren(): MergedFile[] {
    return this.files;
  }

  getParent(): null {
    return null;
  }

  getTreeItem(f: MergedFile): vscode.TreeItem {
    const item = new vscode.TreeItem(
      f.rel.split("/").pop() ?? f.rel,
      vscode.TreeItemCollapsibleState.None,
    );

    const owner = f.askWho || f.topContributors[0]?.name;
    item.description = `CCN ${f.complexity}${owner ? ` · ${owner}` : ""}`;
    item.iconPath = new vscode.ThemeIcon("flame", heatColor(f.complexity, this.maxCx));
    item.tooltip = this.tooltip(f);

    const root = this.root();
    if (root) {
      const target = path.isAbsolute(f.path) ? f.path : path.join(root, f.rel);
      item.command = {
        command: "vscode.open",
        title: "파일 열기",
        arguments: [vscode.Uri.file(target)],
      };
      item.resourceUri = vscode.Uri.file(target);
    }
    return item;
  }

  private tooltip(f: MergedFile): vscode.MarkdownString {
    const md = new vscode.MarkdownString();
    md.appendMarkdown(`**${f.rel}**\n\n`);
    md.appendMarkdown(
      `🔥 복잡도(max CCN): **${f.complexity}** · 평균 ${f.avgComplexity} · 함수 ${f.functionCount} · ${f.loc} LOC\n\n`,
    );
    if (f.topContributors.length) {
      const c = f.topContributors[0];
      md.appendMarkdown(`👤 막히면 물어볼 사람: **${c.name}** (점수 ${c.score}, ${c.commit_count} commits)\n\n`);
    }
    if (f.risk) {
      md.appendMarkdown(`⚠️ 위험도: **${riskLabel(f.risk)}**`);
      if (f.reason) md.appendMarkdown(` — ${f.reason}`);
      md.appendMarkdown("\n\n");
      if (f.askWhat) md.appendMarkdown(`❓ _“${f.askWhat}”_\n\n`);
    }
    if (f.todos.length) {
      md.appendMarkdown(`📝 TODO/FIXME ${f.todos.length}건`);
      if (f.oldestTodoDays != null) md.appendMarkdown(` (가장 오래된 것 ${f.oldestTodoDays}일)`);
    }
    return md;
  }
}
