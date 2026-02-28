import { useRef, useState } from "react";
import type { BessPlacement } from "../types/cad";

type UseBessEditingResult = {
  bessPlacements: BessPlacement[];
  selectedBessId: number | null;
  addBessAt: (x: number, y: number) => BessPlacement;
  setSelectedBessId: (id: number | null) => void;
  setBessPlacements: React.Dispatch<React.SetStateAction<BessPlacement[]>>;
  loadBessPlacements: (items: BessPlacement[]) => void;
  deleteSelectedBess: () => void;
  clearBess: () => void;
};

export function useBessEditing(): UseBessEditingResult {
  const nextBessIdRef = useRef(1);
  const [bessPlacements, setBessPlacements] = useState<BessPlacement[]>([]);
  const [selectedBessId, setSelectedBessId] = useState<number | null>(null);

  function addBessAt(x: number, y: number) {
    const id = nextBessIdRef.current;
    nextBessIdRef.current += 1;

    const placement: BessPlacement = {
      id,
      label: `BESS-${id}`,
      x,
      y,
    };

    setBessPlacements((prev) => [...prev, placement]);
    setSelectedBessId(id);
    return placement;
  }

  function deleteSelectedBess() {
    if (selectedBessId === null) return;
    setBessPlacements((prev) => prev.filter((b) => b.id !== selectedBessId));
    setSelectedBessId(null);
  }

  function clearBess() {
    setBessPlacements([]);
    setSelectedBessId(null);
    nextBessIdRef.current = 1;
  }

  function loadBessPlacements(items: BessPlacement[]) {
    setBessPlacements(items);
    setSelectedBessId(null);
    const maxId = items.reduce((max, item) => Math.max(max, item.id), 0);
    nextBessIdRef.current = maxId + 1;
  }

  return {
    bessPlacements,
    selectedBessId,
    addBessAt,
    setSelectedBessId,
    setBessPlacements,
    loadBessPlacements,
    deleteSelectedBess,
    clearBess,
  };
}
