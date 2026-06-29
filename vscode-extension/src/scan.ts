import { exec } from "child_process";
import * as vscode from "vscode";
import { HeatProvider } from "./heatProvider";

function run(cmd: string, cwd: string): Promise<void> {
  return new Promise((resolve, reject) => {
    exec(cmd, { cwd, maxBuffer: 1024 * 1024 * 16 }, (err, _stdout, stderr) => {
      if (err) reject(new Error(stderr || err.message));
      else resolve();
    });
  });
}

// `codeheat scan` + `codeheat own`을 워크스페이스 루트에서 실행해 리포트를 생성/갱신.
export async function runScan(provider: HeatProvider): Promise<void> {
  const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  if (!root) {
    vscode.window.showWarningMessage("CodeHeat: 워크스페이스 폴더를 먼저 여세요.");
    return;
  }
  const cfg = vscode.workspace.getConfiguration("codeheat");
  const cli = cfg.get<string>("cliCommand", "codeheat");
  const smell = cfg.get<string>("smellReportPath", "smell_report.json");
  const own = cfg.get<string>("ownershipReportPath", "ownership_report.json");

  await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: "CodeHeat 스캔 중…", cancellable: false },
    async (progress) => {
      try {
        progress.report({ message: "복잡도/TODO 분석 (scan)" });
        await run(`${cli} scan "${root}" --output "${smell}"`, root);
        progress.report({ message: "오너십 분석 (own)" });
        await run(`${cli} own "${root}" --from-report "${smell}" --output "${own}"`, root);
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        vscode.window.showErrorMessage(
          `CodeHeat CLI 실행 실패: ${msg}\ncodeheat가 설치돼 있는지(pip install -e .) 또는 설정 'codeheat.cliCommand'를 확인하세요.`,
        );
        return;
      }
      provider.load();
      vscode.window.showInformationMessage("CodeHeat 리포트를 갱신했습니다.");
    },
  );
}
