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
        <svg width={width} height={height} role="img" aria-label="Complexity heatmap treemap">
          {/* 디렉토리 라벨 (leaf가 아닌 내부 노드). 너무 좁은 칸은 생략하고,
              긴 이름이 칸을 넘지 않게 헤더 밴드로 클리핑한다. */}
          {root
            .descendants()
            .filter((n) => n.depth > 0 && n.children)
            .map((n, i) => {
              const dw = n.x1 - n.x0;
              if (dw < 28) return null; // 라벨이 의미 없을 만큼 좁으면 숨김
              return (
                <g key={`dir-${i}`}>
                  <clipPath id={`dirclip-${i}`}>
                    <rect x={n.x0} y={n.y0} width={dw} height={14} />
                  </clipPath>
                  <text
                    x={n.x0 + 4}
                    y={n.y0 + 11}
                    className="dir-label"
                    clipPath={`url(#dirclip-${i})`}
                  >
                    {n.data.name}
                  </text>
                </g>
              );
            })}

          {/* 파일 leaf */}
          {root.leaves().map((n, i) => {
            const f = n.data.file;
            if (!f) return null;
            const w = n.x1 - n.x0;
            const h = n.y1 - n.y0;
            const selected = f.path === selectedPath;
            const showLabel = w > 46 && h > 18;
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
                  {f.path} · CCN {f.complexity} · {f.loc} LOC
                  {f.askWho ? ` · ask: ${f.askWho}` : ""}
                </title>
                {showLabel && (
                  <>
                    {/* 라벨이 칸 밖으로 새지 않게 셀 경계로 클리핑 */}
                    <clipPath id={`leafclip-${i}`}>
                      <rect width={Math.max(w - 2, 0)} height={Math.max(h, 0)} />
                    </clipPath>
                    <text
                      x={4}
                      y={14}
                      className="leaf-label"
                      clipPath={`url(#leafclip-${i})`}
                    >
                      {f.path.split("/").pop()}
                    </text>
                    {h > 32 && (
                      <text
                        x={4}
                        y={28}
                        className="leaf-sub"
                        clipPath={`url(#leafclip-${i})`}
                      >
                        CCN {f.complexity}
                      </text>
                    )}
                  </>
                )}
              </g>
            );
          })}
        </svg>
      )}
      {!root && <p className="empty">No files to display.</p>}
    </div>
  );
}
