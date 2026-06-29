"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { heatColor, layoutTreemap } from "@/lib/treemap";
import type { MergedFile } from "@/lib/types";

interface Props {
  files: MergedFile[];
  selectedPath: string | null;
  onSelect: (file: MergedFile) => void;
  height?: number;
}

export default function Treemap({
  files,
  selectedPath,
  onSelect,
  height = 560,
}: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);

  // 컨테이너 너비를 측정해 반응형으로 레이아웃.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      setWidth(entries[0].contentRect.width);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const maxCx = useMemo(
    () => files.reduce((m, f) => Math.max(m, f.complexity), 0),
    [files],
  );

  const root = useMemo(() => {
    if (width <= 0 || files.length === 0) return null;
    return layoutTreemap(files, width, height);
  }, [files, width, height]);

  return (
    <div ref={ref} className="treemap-wrap">
      {root && (
        <svg width={width} height={height} role="img" aria-label="복잡도 히트맵 트리맵">
          {/* 디렉토리 라벨 (leaf가 아닌 내부 노드) */}
          {root
            .descendants()
            .filter((n) => n.depth > 0 && n.children)
            .map((n, i) => (
              <text
                key={`dir-${i}`}
                x={n.x0 + 4}
                y={n.y0 + 11}
                className="dir-label"
              >
                {n.data.name}
              </text>
            ))}

          {/* 파일 leaf */}
          {root.leaves().map((n, i) => {
            const f = n.data.file;
            if (!f) return null;
            const w = n.x1 - n.x0;
            const h = n.y1 - n.y0;
            const selected = f.path === selectedPath;
            return (
              <g
                key={`leaf-${i}`}
                transform={`translate(${n.x0},${n.y0})`}
                className="leaf"
                onClick={() => onSelect(f)}
              >
                <rect
                  width={Math.max(w, 0)}
                  height={Math.max(h, 0)}
                  fill={heatColor(f.complexity, maxCx)}
                  stroke={selected ? "#fff" : "rgba(0,0,0,0.35)"}
                  strokeWidth={selected ? 2.5 : 0.5}
                  rx={2}
                />
                <title>
                  {f.path} · 복잡도 {f.complexity} · {f.loc} LOC
                  {f.askWho ? ` · 물어볼 사람: ${f.askWho}` : ""}
                </title>
                {w > 46 && h > 18 && (
                  <text x={4} y={14} className="leaf-label">
                    {f.path.split("/").pop()}
                  </text>
                )}
                {w > 46 && h > 32 && (
                  <text x={4} y={28} className="leaf-sub">
                    CCN {f.complexity}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      )}
      {!root && <p className="empty">표시할 파일이 없습니다.</p>}
    </div>
  );
}
