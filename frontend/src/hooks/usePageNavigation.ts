import { useEffect, useSyncExternalStore } from "react";
import {
  normalizePageHash,
  pageFromHash,
  subscribeNavigation,
  workspaceFromHash,
} from "../utils/navigation";

export function usePageNavigation() {
  const hash = useSyncExternalStore(
    subscribeNavigation,
    () => window.location.hash,
    () => "",
  );
  useEffect(() => {
    normalizePageHash();
    window.addEventListener("hashchange", normalizePageHash);
    return () => window.removeEventListener("hashchange", normalizePageHash);
  }, []);
  return { page: pageFromHash(hash), workspace: workspaceFromHash(hash) };
}
