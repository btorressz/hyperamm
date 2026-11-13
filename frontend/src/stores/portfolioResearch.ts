import { create } from "zustand";
import type {
  FormDraft,
  Preview,
  TerminalResult,
} from "../types/portfolioResearch";
import { initialDraft } from "../utils/portfolioResearch";
import { useTerminalStore } from "./terminal";
export type RequestToken = { revision: number; epoch: number; id: number };
type State = {
  draft: FormDraft;
  revision: number;
  epoch: number;
  serial: number;
  pending: RequestToken | null;
  preview: Preview | null;
  result: TerminalResult | null;
  error: string;
  edit: (update: (draft: FormDraft) => FormDraft) => void;
  invalidate: () => void;
  begin: () => RequestToken | null;
  current: (token: RequestToken) => boolean;
  acceptPreview: (token: RequestToken, p: Preview) => boolean;
  acceptResult: (token: RequestToken, r: TerminalResult) => boolean;
  fail: (token: RequestToken, message: string) => void;
};
export const createPortfolioStore = () =>
  create<State>((set, get) => ({
    draft: initialDraft(),
    revision: 0,
    epoch: 0,
    serial: 0,
    pending: null,
    preview: null,
    result: null,
    error: "",
    edit: (update) =>
      set((s) => ({
        draft: update(s.draft),
        revision: s.revision + 1,
        preview: null,
        result: null,
        pending: null,
        error: "",
      })),
    invalidate: () =>
      set((s) => ({
        epoch: s.epoch + 1,
        preview: null,
        result: null,
        pending: null,
        error: "",
      })),
    begin: () => {
      const s = get();
      if (s.pending) return null;
      const token = { revision: s.revision, epoch: s.epoch, id: s.serial + 1 };
      set({ serial: token.id, pending: token, error: "", result: null });
      return token;
    },
    current: (t) => {
      const s = get();
      return (
        s.pending?.id === t.id &&
        s.revision === t.revision &&
        s.epoch === t.epoch
      );
    },
    acceptPreview: (t, p) => {
      if (!get().current(t)) return false;
      set({ preview: p, pending: null });
      return true;
    },
    acceptResult: (t, r) => {
      if (!get().current(t)) return false;
      set({ result: r, pending: null });
      return true;
    },
    fail: (t, error) => {
      if (get().current(t)) set({ error, pending: null, preview: null, result: null });
    },
  }));
export const usePortfolioResearchStore = createPortfolioStore();
// REST research is available without WS. Any observed connection/session change
// retires accepted evidence synchronously; reconnect never restores it.
useTerminalStore.subscribe((next, previous) => {
  if (
    (next.wsState === "connected") !== (previous.wsState === "connected") ||
    next.terminal?.process_id !== previous.terminal?.process_id ||
    next.terminal?.session_id !== previous.terminal?.session_id
  )
    usePortfolioResearchStore.getState().invalidate();
});
