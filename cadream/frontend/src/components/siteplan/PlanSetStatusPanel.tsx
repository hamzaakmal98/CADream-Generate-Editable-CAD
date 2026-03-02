import { useCallback, useEffect, useMemo, useState } from "react";
import type { SitePlacementExport, SldSessionState } from "../../types/cad";
import type { CadIrDrawing } from "../../types/cadIr";
import type { PlanSetManifest, PlanSetPayloadStubsResponse } from "../../types/planset";

type PlanSetStatusPanelProps = {
  cadIr: CadIrDrawing | null;
  sitePlacementPayload: SitePlacementExport;
  sldSession: SldSessionState;
};

export default function PlanSetStatusPanel({ cadIr, sitePlacementPayload, sldSession }: PlanSetStatusPanelProps) {
  const [isCollapsed, setIsCollapsed] = useState(true);
  const [manifest, setManifest] = useState<PlanSetManifest | null>(null);
  const [payloadStubs, setPayloadStubs] = useState<PlanSetPayloadStubsResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const previewPayload = useMemo(
    () => ({
      total_pages: 49,
      cad_ir: cadIr,
      site_placements: sitePlacementPayload,
      sld_session: sldSession,
    }),
    [cadIr, sitePlacementPayload, sldSession]
  );

  const refresh = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const [manifestRes, stubsRes] = await Promise.all([
        fetch("/api/planset/preview", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(previewPayload),
        }),
        fetch("/api/planset/payload-stubs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(previewPayload),
        }),
      ]);

      if (!manifestRes.ok) {
        throw new Error("Failed to fetch plan-set preview");
      }
      if (!stubsRes.ok) {
        throw new Error("Failed to fetch plan-set payload stubs");
      }

      const manifestData = (await manifestRes.json()) as PlanSetManifest;
      const stubsData = (await stubsRes.json()) as PlanSetPayloadStubsResponse;

      setManifest(manifestData);
      setPayloadStubs(stubsData);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown plan-set preview error";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, [previewPayload]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const stubSummary = useMemo(() => {
    if (!payloadStubs) {
      return { auto: 0, fixed: 0, pending: 0 };
    }

    return payloadStubs.page_payloads.reduce(
      (acc, item) => {
        if (item.status === "auto") acc.auto += 1;
        if (item.status === "fixed") acc.fixed += 1;
        if (item.status === "pending") acc.pending += 1;
        return acc;
      },
      { auto: 0, fixed: 0, pending: 0 }
    );
  }, [payloadStubs]);

  return (
    <div
      style={{
        position: "absolute",
        right: 10,
        bottom: 10,
        width: 360,
        background: "white",
        border: "1px solid #ddd",
        borderRadius: 8,
        padding: 10,
        fontSize: 12,
        zIndex: 20,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <strong>Plan-Set Orchestrator</strong>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          {!isCollapsed && (
            <button
              onClick={() => void refresh()}
              disabled={isLoading}
              style={{
                border: "1px solid #cbd5e1",
                background: "#fff",
                borderRadius: 4,
                fontSize: 11,
                padding: "2px 8px",
                cursor: isLoading ? "default" : "pointer",
              }}
            >
              {isLoading ? "Loading..." : "Refresh"}
            </button>
          )}
          <button
            onClick={() => setIsCollapsed((prev) => !prev)}
            style={{
              border: "1px solid #cbd5e1",
              background: "#fff",
              borderRadius: 4,
              fontSize: 11,
              padding: "2px 8px",
              cursor: "pointer",
            }}
          >
            {isCollapsed ? "Expand" : "Collapse"}
          </button>
        </div>
      </div>

      {isCollapsed ? null : error ? (
        <div style={{ color: "#7f1d1d", background: "#fef2f2", border: "1px solid #fecaca", padding: 8, borderRadius: 6 }}>
          {error}
        </div>
      ) : (
        <>
          <div style={{ marginBottom: 8 }}>
            {manifest
              ? `Pages → Auto: ${manifest.summary.auto_pages} | Fixed: ${manifest.summary.fixed_pages} | Pending: ${manifest.summary.pending_pages}`
              : "No manifest yet"}
          </div>

          {manifest && (
            <ul style={{ margin: "0 0 8px", paddingLeft: 16 }}>
              <li>CAD IR: {manifest.input_status.cad_ir.ready ? "ready" : "missing"}</li>
              <li>Site plan: {manifest.input_status.site_plan.ready ? "ready" : "missing"}</li>
              <li>SLD: {manifest.input_status.sld.ready ? "ready" : "missing"}</li>
            </ul>
          )}

          <div>
            Payload stubs → Auto: {stubSummary.auto} | Fixed: {stubSummary.fixed} | Pending: {stubSummary.pending}
          </div>
        </>
      )}
    </div>
  );
}
