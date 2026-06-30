"use client";

import { useCallback, useState } from "react";
import { classifyReport, type ReportKind } from "@/lib/merge";
import type {
  InsightsReport,
  OwnershipReport,
  Reports,
  SmellReport,
} from "@/lib/types";

interface Props {
  onReports: (patch: Partial<Reports>) => void;
  loaded: { smell: boolean; ownership: boolean; insights: boolean };
}

export default function UploadDropzone({ onReports, loaded }: Props) {
  const [dragging, setDragging] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const handleFiles = useCallback(
    async (files: FileList | File[]) => {
      const patch: Partial<Reports> = {};
      const notes: string[] = [];
      for (const file of Array.from(files)) {
        try {
          const obj = JSON.parse(await file.text());
          const kind: ReportKind = classifyReport(obj);
          if (kind === "smell") patch.smell = obj as SmellReport;
          else if (kind === "ownership") patch.ownership = obj as OwnershipReport;
          else if (kind === "insights") patch.insights = obj as InsightsReport;
          else {
            notes.push(`${file.name}: unknown report format`);
            continue;
          }
          notes.push(`${file.name} → ${kind}`);
        } catch {
          notes.push(`${file.name}: JSON parse failed`);
        }
      }
      if (Object.keys(patch).length) onReports(patch);
      setMsg(notes.join(" · "));
    },
    [onReports],
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      if (e.dataTransfer.files.length) handleFiles(e.dataTransfer.files);
    },
    [handleFiles],
  );

  return (
    <div
      className={`dropzone${dragging ? " dragging" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
    >
      <p className="dz-title">Drop report JSON here</p>
      <p className="dz-sub">
        smell_report · ownership_report · insights_report (multiple at once)
      </p>
      <label className="dz-btn">
        Choose file
        <input
          type="file"
          accept=".json,application/json"
          multiple
          hidden
          onChange={(e) => e.target.files && handleFiles(e.target.files)}
        />
      </label>
      <div className="dz-status">
        <Chip on={loaded.smell}>smell</Chip>
        <Chip on={loaded.ownership}>ownership</Chip>
        <Chip on={loaded.insights}>insights</Chip>
      </div>
      {msg && <p className="dz-msg">{msg}</p>}
    </div>
  );
}

function Chip({ on, children }: { on: boolean; children: React.ReactNode }) {
  return <span className={`chip${on ? " chip-on" : ""}`}>{children}</span>;
}
