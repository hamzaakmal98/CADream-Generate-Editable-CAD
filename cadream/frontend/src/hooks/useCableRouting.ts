import { useRef, useState } from "react";
import type { BessPlacement, CablePath, PointOfInterconnection } from "../types/cad";

type SnapResult = {
  point: number[];
  bessId: number;
};

type UseCableRoutingArgs = {
  bessPlacements: BessPlacement[];
  poi: PointOfInterconnection | null;
  bessMarkerSize: number;
  scale: number;
};

type UseCableRoutingResult = {
  cablePaths: CablePath[];
  draftCablePoints: number[][];
  selectedCableId: number | null;
  setSelectedCableId: (id: number | null) => void;
  addDraftPoint: (point: number[]) => void;
  finishCableDraft: () => void;
  cancelCableDraft: () => void;
  deleteSelectedCable: () => void;
  clearCables: () => void;
  updateSelectedCableStart: (point: number[]) => void;
  snapAllCableEndsToPoi: (nextPoi: PointOfInterconnection | null) => void;
  snapPointToNearestBess: (point: number[]) => SnapResult | null;
};

export function useCableRouting({
  bessPlacements,
  poi,
  bessMarkerSize,
  scale,
}: UseCableRoutingArgs): UseCableRoutingResult {
  const nextCableIdRef = useRef(1);
  const [cablePaths, setCablePaths] = useState<CablePath[]>([]);
  const [draftCablePoints, setDraftCablePoints] = useState<number[][]>([]);
  const [selectedCableId, setSelectedCableId] = useState<number | null>(null);

  function snapPointToNearestBess(point: number[]) {
    if (bessPlacements.length === 0) return null;

    const snapDistance = Math.max(bessMarkerSize * 1.6, 60 / Math.max(scale, 0.0001));
    const snapDistanceSq = snapDistance * snapDistance;

    let nearest: BessPlacement | null = null;
    let nearestDistSq = Infinity;

    for (const bess of bessPlacements) {
      const dx = bess.x - point[0];
      const dy = bess.y - point[1];
      const distSq = dx * dx + dy * dy;
      if (distSq < nearestDistSq) {
        nearestDistSq = distSq;
        nearest = bess;
      }
    }

    if (!nearest || nearestDistSq > snapDistanceSq) return null;
    return {
      point: [nearest.x, nearest.y],
      bessId: nearest.id,
    };
  }

  function addDraftPoint(point: number[]) {
    setDraftCablePoints((prev) => [...prev, point]);
  }

  function finishCableDraft() {
    if (draftCablePoints.length < 2 || !poi) return;

    const firstRaw = draftCablePoints[0];
    const firstSnap = snapPointToNearestBess(firstRaw);

    const points = [...draftCablePoints];
    points[0] = firstSnap?.point ?? firstRaw;
    points[points.length - 1] = [poi.x, poi.y];

    const id = nextCableIdRef.current;
    nextCableIdRef.current += 1;

    const cable: CablePath = {
      id,
      points,
      from_bess_id: firstSnap?.bessId ?? null,
      to_bess_id: null,
      to_poi: true,
    };

    setCablePaths((prev) => [...prev, cable]);
    setDraftCablePoints([]);
    setSelectedCableId(id);
  }

  function cancelCableDraft() {
    setDraftCablePoints([]);
  }

  function deleteSelectedCable() {
    if (selectedCableId === null) return;
    setCablePaths((prev) => prev.filter((c) => c.id !== selectedCableId));
    setSelectedCableId(null);
  }

  function clearCables() {
    setCablePaths([]);
    setDraftCablePoints([]);
    setSelectedCableId(null);
  }

  function updateSelectedCableStart(point: number[]) {
    if (selectedCableId === null) return;

    const snap = snapPointToNearestBess(point);
    const startPoint = snap?.point ?? point;

    setCablePaths((prev) =>
      prev.map((cable) => {
        if (cable.id !== selectedCableId || cable.points.length < 2) return cable;
        const nextPoints = [...cable.points];
        nextPoints[0] = startPoint;
        return {
          ...cable,
          points: nextPoints,
          from_bess_id: snap?.bessId ?? null,
        };
      })
    );
  }

  function snapAllCableEndsToPoi(nextPoi: PointOfInterconnection | null) {
    if (!nextPoi) return;
    setCablePaths((prev) =>
      prev.map((cable) => {
        if (cable.points.length < 2) return cable;
        const nextPoints = [...cable.points];
        nextPoints[nextPoints.length - 1] = [nextPoi.x, nextPoi.y];
        return {
          ...cable,
          points: nextPoints,
          to_poi: true,
          to_bess_id: null,
        };
      })
    );
  }

  return {
    cablePaths,
    draftCablePoints,
    selectedCableId,
    setSelectedCableId,
    addDraftPoint,
    finishCableDraft,
    cancelCableDraft,
    deleteSelectedCable,
    clearCables,
    updateSelectedCableStart,
    snapAllCableEndsToPoi,
    snapPointToNearestBess,
  };
}
