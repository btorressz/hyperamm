import { useEffect, useState } from 'react';
import { useTerminalStore } from '../stores/terminal';
import type { TerminalState } from '../types';
import { sessionCurrent } from '../utils/researchEvidence';

// Increment synchronously on store transitions, even when React batches a reconnect.
// The REST wire has no session ID: this guards attribution, not cryptographic binding.
let connectionEpoch = 0;
useTerminalStore.subscribe((next, previous) => {
  if (next.wsState !== previous.wsState || next.terminal?.process_id !== previous.terminal?.process_id ||
      next.terminal?.session_id !== previous.terminal?.session_id) connectionEpoch++;
});
export function useResearchSession(t: TerminalState, historical: boolean) {
  const [epoch, setEpoch] = useState(connectionEpoch);
  useEffect(() => useTerminalStore.subscribe(() => setEpoch(connectionEpoch)), []);
  return {
    epoch,
    enabled: epoch === connectionEpoch && !historical && sessionCurrent(t, useTerminalStore.getState()),
    check: () => {
      if (epoch !== connectionEpoch || historical || !sessionCurrent(t, useTerminalStore.getState()))
        throw new Error('Research request belongs to a retired or disconnected observation.');
    },
  };
}
