import { useState } from "react";
import type {
  BessPlacement,
  CablePath,
  PointOfInterconnection,
  RenderDoc,
  SitePlacementExport,
  ToolMode,
  SldSessionState,
} from "../types/cad";
import type { CadIrDrawing } from "../types/cadIr";
import { attachSitePlanToCadIr, buildCadIrFromRenderDoc } from "../utils/cadIrBuilder";
import { createProjectSessionV2, loadProjectFromAnySession } from "../utils/projectSession";

export type CadIrValidationState = {
  level: "error" | "warning" | "success";
  title: string;
  messages: string[];
} | null;

type UseProjectActionsArgs = {
  doc: RenderDoc | null;
  setDoc: (value: RenderDoc | null) => void;
  sourceDxfName: string | null;
  setSourceDxfName: (value: string | null) => void;
  cadIr: CadIrDrawing | null;
  setCadIr: (value: CadIrDrawing | null) => void;
  bessPlacements: BessPlacement[];
  poi: PointOfInterconnection | null;
  cablePaths: CablePath[];
  toolMode: ToolMode;
  bessSizeFactor: number;
  hiddenLayers: Record<string, boolean>;
  scale: number;
  pos: { x: number; y: number };
  sitePlacementPayload: SitePlacementExport;
  sldSession: SldSessionState;
  sldLoadSession: (session: SldSessionState) => void;
  loadBessPlacements: (items: BessPlacement[]) => void;
  loadCablePaths: (items: CablePath[]) => void;
  setPoi: (value: PointOfInterconnection | null) => void;
  setToolMode: (value: ToolMode) => void;
  setBessSizeFactor: (value: number) => void;
  setHiddenLayers: (value: Record<string, boolean>) => void;
  setScale: (value: number) => void;
  setPos: (value: { x: number; y: number }) => void;
  setSelectedBessId: (value: number | null) => void;
  setSelectedCableId: (value: number | null) => void;
  getBestFitBounds: (data: RenderDoc) => { min: number[]; max: number[] } | null;
  fitToBounds: (bounds: { min: number[]; max: number[] }) => void;
};

export function useProjectActions({
  doc,
  setDoc,
  sourceDxfName,
  setSourceDxfName,
  cadIr,
  setCadIr,
  bessPlacements,
  poi,
  cablePaths,
  toolMode,
  bessSizeFactor,
  hiddenLayers,
  scale,
  pos,
  sitePlacementPayload,
  sldSession,
  sldLoadSession,
  loadBessPlacements,
  loadCablePaths,
  setPoi,
  setToolMode,
  setBessSizeFactor,
  setHiddenLayers,
  setScale,
  setPos,
  setSelectedBessId,
  setSelectedCableId,
  getBestFitBounds,
  fitToBounds,
}: UseProjectActionsArgs) {
  const [cadIrValidationState, setCadIrValidationState] = useState<CadIrValidationState>(null);

  function buildCurrentCadIr() {
    const baseCadIr = doc
      ? buildCadIrFromRenderDoc({
          doc,
          sourceFileName: sourceDxfName,
        })
      : cadIr;

    if (!baseCadIr) return null;

    return attachSitePlanToCadIr(baseCadIr, {
      bessPlacements,
      poi,
      cablePaths,
    });
  }

  async function validateCadIrOrAlert(cadIrToValidate: NonNullable<ReturnType<typeof buildCurrentCadIr>>) {
    let res: Response;
    try {
      res = await fetch("/api/cad-ir/validate", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ cad_ir: cadIrToValidate }),
      });
    } catch {
      setCadIrValidationState({
        level: "error",
        title: "CAD IR Validation Service Unavailable",
        messages: ["Could not validate CAD IR. Please ensure backend is running and try again."],
      });
      return false;
    }

    if (!res.ok) {
      setCadIrValidationState({
        level: "error",
        title: "CAD IR Validation Service Unavailable",
        messages: ["Could not validate CAD IR. Please ensure backend is running and try again."],
      });
      return false;
    }

    const result = (await res.json()) as {
      valid: boolean;
      errors?: string[];
      warnings?: string[];
    };

    if (!result.valid) {
      setCadIrValidationState({
        level: "error",
        title: "CAD IR Validation Failed",
        messages: (result.errors ?? []).slice(0, 6),
      });
      return false;
    }

    if ((result.warnings?.length ?? 0) > 0) {
      setCadIrValidationState({
        level: "warning",
        title: "CAD IR Validation Warnings",
        messages: (result.warnings ?? []).slice(0, 6),
      });
      return true;
    }

    setCadIrValidationState({
      level: "success",
      title: "CAD IR Validation Passed",
      messages: ["No errors found."],
    });

    return true;
  }

  async function onSaveProject() {
    const currentCadIr = buildCurrentCadIr();
    if (currentCadIr) {
      const valid = await validateCadIrOrAlert(currentCadIr);
      if (!valid) return;
    }

    const session = createProjectSessionV2({
      sourceDxfName,
      cadIr: currentCadIr,
      bessPlacements,
      poi,
      cablePaths,
      toolMode,
      bessSizeFactor,
      hiddenLayers,
      scale,
      pos,
      sldSession,
    });

    const blob = new Blob([JSON.stringify(session, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    const fileBase = sourceDxfName ? sourceDxfName.replace(/\.[^.]+$/, "") : "cadream-project";
    anchor.href = url;
    anchor.download = `${fileBase}.project.json`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  async function onExportDxf() {
    if (!doc?.source_token) {
      setCadIrValidationState({
        level: "error",
        title: "Export Unavailable",
        messages: ["Please upload the source DXF in this session before exporting."],
      });
      return;
    }

    const exportCadIr = buildCurrentCadIr();

    if (!exportCadIr) {
      setCadIrValidationState({
        level: "error",
        title: "Export Unavailable",
        messages: ["No CAD data available to export. Upload a DXF first."],
      });
      return;
    }

    const valid = await validateCadIrOrAlert(exportCadIr);
    if (!valid) return;

    const defaultBase = sourceDxfName ? sourceDxfName.replace(/\.[^.]+$/, "") : "cadream-export";
    const requestedName = window.prompt("Enter DXF file name", defaultBase);
    if (requestedName === null) return;
    const normalizedFileBase = requestedName.trim().replace(/\.[^.]+$/, "") || defaultBase;

    let res: Response;
    try {
      res = await fetch("/api/dxf/export", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          source_token: doc.source_token,
          site_placements: sitePlacementPayload,
          cad_ir: exportCadIr,
          source_file_name: normalizedFileBase,
        }),
      });
    } catch {
      setCadIrValidationState({
        level: "error",
        title: "Export Service Unavailable",
        messages: ["Could not reach backend export service. Please ensure backend is running and try again."],
      });
      return;
    }

    if (!res.ok) {
      let detail = "DXF export failed.";
      try {
        const err = (await res.json()) as { detail?: string };
        if (typeof err.detail === "string" && err.detail.trim()) {
          detail = err.detail;
        }
      } catch {
        // keep default message
      }

      setCadIrValidationState({
        level: "error",
        title: "DXF Export Failed",
        messages: [detail],
      });
      return;
    }

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    const fileBase = normalizedFileBase;
    anchor.href = url;
    anchor.download = `${fileBase}.dxf`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  async function onLoadProject(file: File) {
    try {
      const raw = await file.text();
      const parsed = JSON.parse(raw) as unknown;

      const loaded = loadProjectFromAnySession(parsed, {
        scale,
        pos,
      });

      if (!loaded) {
        setCadIrValidationState({
          level: "error",
          title: "Load Failed",
          messages: ["Unsupported project file format."],
        });
        return;
      }

      setSourceDxfName(loaded.sitePlan.sourceDxfName);
      setCadIr(loaded.sitePlan.cadIr);
      loadBessPlacements(loaded.sitePlan.bessPlacements);
      loadCablePaths(loaded.sitePlan.cablePaths);
      setPoi(loaded.sitePlan.poi);
      setToolMode(loaded.sitePlan.toolMode);
      setBessSizeFactor(loaded.sitePlan.bessSizeFactor);
      setHiddenLayers(loaded.sitePlan.hiddenLayers);
      setScale(loaded.sitePlan.scale);
      setPos(loaded.sitePlan.pos);
      setSelectedBessId(null);
      setSelectedCableId(null);
      sldLoadSession(loaded.sldSession);
      setCadIrValidationState(null);
    } catch {
      setCadIrValidationState({
        level: "error",
        title: "Load Failed",
        messages: ["Failed to load project JSON."],
      });
    }
  }

  async function onUpload(file: File) {
    setSourceDxfName(file.name);
    const fd = new FormData();
    fd.append("file", file);

    const res = await fetch("/api/dxf/parse", {
      method: "POST",
      body: fd,
    });

    const data = (await res.json()) as RenderDoc;
    const fitBounds = getBestFitBounds(data);

    setDoc(data);
    setCadIr(
      buildCadIrFromRenderDoc({
        doc: data,
        sourceFileName: file.name,
      })
    );

    if (fitBounds) fitToBounds(fitBounds);
  }

  return {
    cadIrValidationState,
    setCadIrValidationState,
    onSaveProject,
    onExportDxf,
    onLoadProject,
    onUpload,
  };
}
