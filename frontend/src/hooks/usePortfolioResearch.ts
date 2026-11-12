import { useEffect, useRef } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { Mode, TerminalRequest } from "../types/portfolioResearch";
import { usePortfolioResearchStore } from "../stores/portfolioResearch";
import {
  checkedPreview,
  checkedTerminal,
  draftRequest,
} from "../utils/portfolioResearch";
export function usePortfolioResearch() {
  const s = usePortfolioResearchStore(),
    controller = useRef<AbortController | null>(null);
  const catalog = useQuery({
    queryKey: ["portfolio-scenarios"],
    queryFn: api.simulationScenarios,
    retry: false,
    refetchOnWindowFocus: false,
  });
  const mutation = useMutation({
    retry: false,
    gcTime: 0,
    mutationFn: async (mode: Mode | "PREVIEW") => {
      const state = usePortfolioResearchStore.getState();
      const draft = draftRequest(state.draft),
        preview = state.preview;
      if (mode !== "PREVIEW" && !preview)
        throw new Error("Validate the current draft before running research.");
      const token = state.begin();
      if (!token) return;
      controller.current?.abort();
      const abort = new AbortController();
      controller.current = abort;
      try {
        if (mode === "PREVIEW") {
          const p = checkedPreview(
            await api.portfolioPreview(draft, abort.signal),
            draft,
          );
          usePortfolioResearchStore.getState().acceptPreview(token, p);
        } else {
          const q: TerminalRequest = {
            mode,
            config: preview!.config,
            config_fingerprint: preview!.config_fingerprint,
            risk_policy: preview!.risk_policy,
            ...(mode === "STRESS" && preview!.stress
              ? { scenario: preview!.stress }
              : {}),
          };
          const r = checkedTerminal(
            await api.portfolioTerminal(q, abort.signal),
            q,
          );
          usePortfolioResearchStore.getState().acceptResult(token, r);
        }
      } catch (e) {
        usePortfolioResearchStore
          .getState()
          .fail(
            token,
            e instanceof TypeError
              ? "Local research connection unavailable. Retry after checking the backend. The admitted job may still run."
              : e instanceof Error
                ? e.message
                : "Portfolio research unavailable.",
          );
      }
    },
  });
  useEffect(() => {
    const unsubscribe = usePortfolioResearchStore.subscribe((n, p) => {
      if (n.revision !== p.revision || n.epoch !== p.epoch)
        controller.current?.abort();
    });
    return () => {
      unsubscribe();
      controller.current?.abort();
      usePortfolioResearchStore.getState().invalidate();
    };
  }, []);
  return {
    ...s,
    error:
      s.error ||
      (mutation.error instanceof Error ? mutation.error.message : ""),
    catalog,
    submit: (mode: Mode | "PREVIEW") => {
      mutation.reset();
      mutation.mutate(mode);
    },
  };
}
