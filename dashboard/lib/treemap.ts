// 트리맵 계층 구성 + 복잡도 → 온도색 매핑. d3-hierarchy로 레이아웃만 계산하고
// 렌더는 React(SVG)가 맡는다(D3가 DOM을 직접 건드리지 않게).

import { hierarchy, treemap, type HierarchyRectangularNode } from "d3-hierarchy";
import type { MergedFile } from "./types";

export interface TreeNode {
  name: string;
  file?: MergedFile;
  children?: TreeNode[];
}

// 평평한 파일 목록을 경로(`/`) 기준 디렉토리 트리로 만든다.
export function buildTree(files: MergedFile[]): TreeNode {
  const root: TreeNode = { name: "root", children: [] };
  for (const f of files) {
    const parts = f.path.split("/").filter(Boolean);
    let node = root;
    parts.forEach((part, i) => {
      node.children ??= [];
      let child = node.children.find((c) => c.name === part);
      if (!child) {
        child = { name: part };
        node.children.push(child);
      }
      if (i === parts.length - 1) child.file = f;
      node = child;
    });
  }
  return root;
}

export interface LaidOutNode extends HierarchyRectangularNode<TreeNode> {}

export function layoutTreemap(
  files: MergedFile[],
  width: number,
  height: number,
): LaidOutNode {
  const root = hierarchy(buildTree(files))
    // 면적 = LOC(파일 크기). 0 LOC도 보이도록 최소 1.
    .sum((d) => (d.file ? Math.max(d.file.loc, 1) : 0))
    .sort((a, b) => (b.value ?? 0) - (a.value ?? 0));

  treemap<TreeNode>()
    .size([width, height])
    .paddingInner(2)
    .paddingTop((d) => (d.depth > 0 && d.children ? 16 : 0))
    .paddingOuter(2)
    .round(true)(root);

  return root as LaidOutNode;
}

// 복잡도 → HSL 온도색. 낮으면 초록, 높으면 빨강(가운데 노랑).
export function heatColor(complexity: number, max: number): string {
  const ceiling = Math.max(max, 10); // 작은 데이터셋이 과포화되지 않게 하한
  const t = Math.min(complexity / ceiling, 1);
  const hue = (1 - t) * 120; // 120=초록 → 0=빨강
  const light = 46 - t * 10;
  return `hsl(${hue}, 68%, ${light}%)`;
}

export function riskLabel(risk: string | null): string {
  if (risk === "high") return "높음";
  if (risk === "medium") return "보통";
  if (risk === "low") return "낮음";
  return "—";
}
