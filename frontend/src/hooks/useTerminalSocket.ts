import { useEffect } from "react";
import { startTerminalSocket } from "../utils/terminalSocket";
export function useTerminalSocket() {
  useEffect(startTerminalSocket, []);
}
