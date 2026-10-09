import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { HistoryRange } from "../types";
type Display = {
  dense: boolean;
  sidebarCollapsed: boolean;
  historySize: number;
  defaultRange: HistoryRange;
  setDense: (x: boolean) => void;
  setSidebarCollapsed: (x: boolean) => void;
  setHistorySize: (x: number) => void;
  setDefaultRange: (x: HistoryRange) => void;
};
export const useDisplayStore = create<Display>()(
  persist(
    (set) => ({
      dense: false,
      sidebarCollapsed: false,
      historySize: 600,
      defaultRange: "session",
      setDense: (dense) => set({ dense }),
      setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
      setHistorySize: (historySize) => set({ historySize }),
      setDefaultRange: (defaultRange) => set({ defaultRange }),
    }),
    { name: "hyperamm-display-v1" },
  ),
);
