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
  collapseChains(root);
  return root;
}

// 외길 디렉토리 체인(자식이 디렉토리 하나뿐)을 한 노드로 접는다.
// "tpot/docker/p0f/<files>"처럼 깊지만 갈라지지 않는 구조가 헤더 밴드를
// 층층이 쌓아 라벨이 겹치고 영역을 잡아먹던 문제를 줄인다. 이름은 "a/b/c"로 합침.
function collapseChains(node: TreeNode): void {
  if (!node.children) return;
  for (const child of node.children) {
    while (
      child.children &&
      child.children.length === 1 &&
      child.children[0].children && // 단일 자식이 '디렉토리'일 때만 접음
      child.children[0].file === undefined
    ) {
      const grand = child.children[0];
      child.name = `${child.name}/${grand.name}`;
      child.children = grand.children;
      child.file = grand.file;
    }
    collapseChains(child);
  }
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
