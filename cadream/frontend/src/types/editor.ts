export type EditorEntityId = string;

export type EditorSelection = {
  entityIds: EditorEntityId[];
};

export type EditorCommandContext<TState> = {
  getState: () => TState;
  setState: (next: TState) => void;
};

export type EditorCommand<TState> = {
  id: string;
  label: string;
  execute: (context: EditorCommandContext<TState>) => void;
  undo?: (context: EditorCommandContext<TState>) => void;
};

export type EditorCommandBus<TState> = {
  run: (command: EditorCommand<TState>) => void;
  undo: () => void;
  redo: () => void;
  canUndo: () => boolean;
  canRedo: () => boolean;
};

export type ViewportState = {
  scale: number;
  pos: { x: number; y: number };
};
