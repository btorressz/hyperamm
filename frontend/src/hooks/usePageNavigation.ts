import { useEffect, useSyncExternalStore } from "react";
import {
  normalizePageHash,
  pageFromHash,
  subscribeNavigation,
} from "../utils/navigation";

export function usePageNavigation() {
  const page = useSyncExternalStore(
    subscribeNavigation,
    () => pageFromHash(window.location.hash),
    () => "Dashboard" as const,
  );
  useEffect(() => {
    normalizePageHash();
    window.addEventListener("hashchange", normalizePageHash);
    return () => window.removeEventListener("hashchange", normalizePageHash);
  }, []);
  return page;
}
