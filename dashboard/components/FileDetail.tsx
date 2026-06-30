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
        <p>Click a file in the treemap to see details here.</p>
        <p className="muted">
          Area = file size (LOC), color = complexity temperature (max CCN).
          Redder is hotter.
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
        <Metric label="Complexity (max CCN)" value={file.complexity} />
        <Metric label="Avg CCN" value={file.avgComplexity} />
        <Metric label="Functions" value={file.functionCount} />
        <Metric label="LOC" value={file.loc} />
        {file.totalCommits != null && (
          <Metric label="Commits" value={file.totalCommits} />
        )}
        {file.duplicationRatio > 0 && (
          <Metric
            label="Duplication"
            value={`${Math.round(file.duplicationRatio * 100)}%`}
          />
        )}
      </div>

      {file.risk && (
        <section className={`risk risk-${file.risk}`}>
          <div className="risk-head">
            <span className="risk-badge">{riskLabel(file.risk)}</span>
            <span>Refactor risk</span>
          </div>
          {file.reason && <p className="reason">{file.reason}</p>}
          {file.askWho && (
            <p className="ask">
              <strong>Ask if you get stuck:</strong> {file.askWho}
            </p>
          )}
          {file.askWhat && (
            <p className="ask-what">“{file.askWhat}”</p>
          )}
        </section>
      )}

      <section className="block">
        <h3>Domain knowledge (ownership)</h3>
        {file.topContributors.length === 0 ? (
          <p className="muted">No ownership data (upload ownership_report)</p>
        ) : (
          <ul className="owners">
            {file.topContributors.map((c, i) => (
              <li key={i}>
                <span className="owner-name">{c.name}</span>
                <span className="owner-meta">
                  score {c.score} · {c.commit_count} commits
                  {c.last_commit_days != null
                    ? ` · ${c.last_commit_days}d ago`
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
          <p className="muted">None</p>
        ) : (
          <ul className="todos">
            {file.todos.map((t, i) => (
              <li key={i}>
                <code>L{t.line}</code> {t.text}
                {t.age_days != null && (
                  <span className="age"> · {t.age_days}d old</span>
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
