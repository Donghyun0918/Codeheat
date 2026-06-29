import * as path from "path";
import * as vscode from "vscode";
import { HeatProvider } from "./heatProvider";

// 활성 파일의 온도(복잡도)와 오너를 상태바에 표시. 리포트에 없으면 숨긴다.
export class StatusBar {
  private item: vscode.StatusBarItem;

  constructor(private provider: HeatProvider) {
    this.item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
    this.item.command = "codeheat.heatmap.focus";
  }

  update(): void {
    const editor = vscode.window.activeTextEditor;
    const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
    if (!editor || !root) {
      this.item.hide();
      return;
    }
    const rel = path.relative(root, editor.document.uri.fsPath);
    const f = this.provider.lookup(rel);
    if (!f) {
      this.item.hide();
      return;
    }

    const owner = f.askWho || f.topContributors[0]?.name;
    this.item.text = `$(flame) CCN ${f.complexity}${owner ? ` · ${owner}` : ""}`;
    this.item.tooltip = owner
      ? `CodeHeat: 복잡도 ${f.complexity} · 막히면 ${owner}에게 물어보세요`
      : `CodeHeat: 복잡도 ${f.complexity}`;
    this.item.show();
  }

  dispose(): void {
    this.item.dispose();
  }
}
