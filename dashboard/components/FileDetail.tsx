"use client";

import { heatColor, riskLabel } from "@/lib/treemap";
import type { MergedFile } from "@/lib/types";

interface Props {
  file: MergedFile | null;
  maxComplexity: number;
}

export default function FileDetail({ file, maxComplexity }: Props) {
  if (!file) {
    return (
      <aside className="detail detail-empty">
        <p>트리맵에서 파일을 클릭하면 상세 정보가 여기 표시됩니다.</p>
        <p className="muted">
          면적 = 파일 크기(LOC), 색 = 복잡도 온도(max CCN). 빨갈수록 뜨겁다.
        </p>
      </aside>
    );
  }

  return (
    <aside className="detail">
      <header className="detail-head">
        <span
          className="heat-dot"
          style={{ background: heatColor(file.complexity, maxComplexity) }}
        />
        <h2 title={file.path}>{file.path}</h2>
      </header>

      <div className="metrics">
        <Metric label="복잡도 (max CCN)" value={file.complexity} />
        <Metric label="평균 CCN" value={file.avgComplexity} />
        <Metric label="함수 수" value={file.functionCount} />
        <Metric label="LOC" value={file.loc} />
        {file.totalCommits != null && (
          <Metric label="커밋 수" value={file.totalCommits} />
        )}
        {file.duplicationRatio > 0 && (
          <Metric
            label="중복률"
            value={`${Math.round(file.duplicationRatio * 100)}%`}
          />
        )}
      </div>

      {file.risk && (
        <section className={`risk risk-${file.risk}`}>
          <div className="risk-head">
            <span className="risk-badge">{riskLabel(file.risk)}</span>
            <span>리팩토링 위험도</span>
          </div>
          {file.reason && <p className="reason">{file.reason}</p>}
          {file.askWho && (
            <p className="ask">
              <strong>막히면 물어볼 사람:</strong> {file.askWho}
            </p>
          )}
          {file.askWhat && (
            <p className="ask-what">“{file.askWhat}”</p>
          )}
        </section>
      )}

      <section className="block">
        <h3>도메인 지식 보유자 (오너십)</h3>
        {file.topContributors.length === 0 ? (
          <p className="muted">오너십 데이터 없음 (ownership_report 업로드 필요)</p>
        ) : (
          <ul className="owners">
            {file.topContributors.map((c, i) => (
              <li key={i}>
                <span className="owner-name">{c.name}</span>
                <span className="owner-meta">
                  점수 {c.score} · {c.commit_count} commits
                  {c.last_commit_days != null
                    ? ` · ${c.last_commit_days}일 전`
                    : ""}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="block">
        <h3>TODO / FIXME ({file.todos.length})</h3>
        {file.todos.length === 0 ? (
          <p className="muted">없음</p>
        ) : (
          <ul className="todos">
            {file.todos.map((t, i) => (
              <li key={i}>
                <code>L{t.line}</code> {t.text}
                {t.age_days != null && (
                  <span className="age"> · {t.age_days}일 됨</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </aside>
  );
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="metric">
      <span className="metric-val">{value}</span>
      <span className="metric-label">{label}</span>
    </div>
  );
}
