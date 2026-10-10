import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { HistoryRange } from "../types";
export const displayDefaults = {
  dense: false,
  sidebarCollapsed: false,
  historySize: 600,
  defaultRange: "session" as HistoryRange,
};
export const displayRanges: HistoryRange[] = [
  "session",
  "1m",
  "5m",
  "15m",
  "1h",
];
export const displayHistorySizes = [100, 300, 600, 1000];
export function validatedDisplay(value: unknown) {
  const v =
    value && typeof value === "object"
      ? (value as Record<string, unknown>)
      : {};
  return {
    dense: typeof v.dense === "boolean" ? v.dense : displayDefaults.dense,
    sidebarCollapsed:
      typeof v.sidebarCollapsed === "boolean"
        ? v.sidebarCollapsed
        : displayDefaults.sidebarCollapsed,
    historySize:
      typeof v.historySize === "number" &&
      displayHistorySizes.includes(v.historySize)
        ? v.historySize
        : displayDefaults.historySize,
    defaultRange: displayRanges.includes(v.defaultRange as HistoryRange)
      ? (v.defaultRange as HistoryRange)
      : displayDefaults.defaultRange,
  };
}
type Display = {
  dense: boolean;
  sidebarCollapsed: boolean;
  historySize: number;
  defaultRange: HistoryRange;
  setDense: (x: boolean) => void;
  setSidebarCollapsed: (x: boolean) => void;
  setHistorySize: (x: number) => void;
  setDefaultRange: (x: HistoryRange) => void;
  resetDisplayPreferences: () => void;
};
export const useDisplayStore = create<Display>()(
  persist(
    (set) => ({
      ...displayDefaults,
      setDense: (dense) => set({ dense }),
      setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
      setHistorySize: (historySize) =>
        set({ historySize: validatedDisplay({ historySize }).historySize }),
      setDefaultRange: (defaultRange) =>
        set({ defaultRange: validatedDisplay({ defaultRange }).defaultRange }),
      resetDisplayPreferences: () => set({ ...displayDefaults }),
    }),
    {
      name: "hyperamm-display-v1",
      partialize: ({ dense, sidebarCollapsed, historySize, defaultRange }) => ({
        dense,
        sidebarCollapsed,
        historySize,
        defaultRange,
      }),
      merge: (persisted, current) => ({
        ...current,
        ...validatedDisplay(persisted),
      }),
    },
  ),
);
