import * as vscode from "vscode";
import { HeatProvider } from "./heatProvider";
import { runScan } from "./scan";
import { StatusBar } from "./status";

export function activate(context: vscode.ExtensionContext): void {
  const provider = new HeatProvider();
  const tree = vscode.window.createTreeView("codeheat.heatmap", {
    treeDataProvider: provider,
  });
  const status = new StatusBar(provider);

  provider.load();
  status.update();

  context.subscriptions.push(
    tree,
    status,
    vscode.commands.registerCommand("codeheat.refresh", () => provider.load()),
    vscode.commands.registerCommand("codeheat.runScan", () => runScan(provider)),
    vscode.window.onDidChangeActiveTextEditor(() => status.update()),
    // 리포트 갱신 시 상태바도 다시 그린다.
    provider.onDidChangeTreeData(() => status.update()),
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration("codeheat")) provider.load();
    }),
  );
}

export function deactivate(): void {
  // subscriptions가 정리를 담당한다.
}
