"use client";

import { useMemo, useState } from "react";
import FileDetail from "@/components/FileDetail";
import Treemap from "@/components/Treemap";
import UploadDropzone from "@/components/UploadDropzone";
import { mergeFromReports } from "@/lib/merge";
import type { MergedFile, Reports } from "@/lib/types";
import sampleSmell from "./sample-data/smell_report.json";
import sampleOwnership from "./sample-data/ownership_report.json";

// 번들 샘플: 이 레포(codeheat)를 scan + own 한 결과. 열자마자 무언가 보이게.
const SAMPLE: Reports = {
  smell: sampleSmell as unknown as Reports["smell"],
  ownership: sampleOwnership as unknown as Reports["ownership"],
  insights: null,
};

export default function Home() {
  const [reports, setReports] = useState<Reports>(SAMPLE);
  const [selected, setSelected] = useState<MergedFile | null>(null);
  const [usingSample, setUsingSample] = useState(true);

  const files = useMemo(() => mergeFromReports(reports), [reports]);
  const maxComplexity = useMemo(
    () => files.reduce((m, f) => Math.max(m, f.complexity), 0),
    [files],
  );

  const selectedFresh = useMemo(
    () => files.find((f) => f.path === selected?.path) ?? null,
    [files, selected],
  );

  function applyPatch(patch: Partial<Reports>) {
    // 첫 업로드면 샘플을 비우고 업로드분으로 시작(샘플과 섞이지 않게).
    setReports((prev) => {
      const base: Reports = usingSample
        ? { smell: null, ownership: null, insights: null }
        : prev;
      return { ...base, ...patch };
    });
    setUsingSample(false);
    setSelected(null);
  }

  const loaded = {
    smell: !!reports.smell,
    ownership: !!reports.ownership,
    insights: !!reports.insights,
  };

  return (
    <main className="page">
      <header className="masthead">
        <div>
          <h1>CodeHeat 🔥</h1>
          <p className="tagline">
            복잡도 히트맵 · 면적=크기(LOC), 색=온도(복잡도). “누가 쌌나”가 아니라
            “누가 해결할 수 있나”.
          </p>
        </div>
        <div className="stat-row">
          <Stat label="파일" value={files.length} />
          <Stat label="최고 온도" value={maxComplexity} />
          <Stat
            label="데이터"
            value={usingSample ? "샘플" : "업로드"}
            small
          />
        </div>
      </header>

      {reports.insights?.summary && (
        <p className="summary">💡 {reports.insights.summary}</p>
      )}

      <UploadDropzone onReports={applyPatch} loaded={loaded} />

      <Legend max={maxComplexity} />

      <section className="board">
        <div className="treemap-col">
          {files.length > 0 ? (
            <Treemap
              files={files}
              selectedPath={selectedFresh?.path ?? null}
              onSelect={setSelected}
            />
          ) : (
            <p className="empty">
              smell_report.json을 업로드하면 트리맵이 나타납니다.
            </p>
          )}
        </div>
        <FileDetail file={selectedFresh} maxComplexity={maxComplexity} />
      </section>

      <footer className="foot">
        CodeHeat 4단계 출력 레이어 · 정적 대시보드 (백엔드 없음, 데이터는
        브라우저에서만 처리)
      </footer>
    </main>
  );
}

function Stat({
  label,
  value,
  small,
}: {
  label: string;
  value: number | string;
  small?: boolean;
}) {
  return (
    <div className="stat">
      <span className={`stat-val${small ? " stat-val-sm" : ""}`}>{value}</span>
      <span className="stat-label">{label}</span>
    </div>
  );
}

function Legend({ max }: { max: number }) {
  return (
    <div className="legend">
      <span className="legend-label">차가움 (CCN 0)</span>
      <span className="legend-bar" />
      <span className="legend-label">뜨거움 (CCN {Math.max(max, 10)}+)</span>
    </div>
  );
}
