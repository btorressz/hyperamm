import type { terminalPages } from "../utils/navigation";
type IconName = (typeof terminalPages)[number]["icon"];
const paths: Record<IconName, string> = {
  overview: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  markets: "M4 20V10 M9 20V4 M14 20v-8 M19 20V7 M2 20h20",
  strategy: "M2 16l5-7 5 4 5-8 5 3",
  controls: "M4 3v18 M12 3v18 M20 3v18 M1 8h6 M9 16h6 M17 8h6",
  execution: "M3 7h17l-4-4 M21 17H4l4 4",
  risk: "M12 2l8 4v6c0 5-8 10-8 10S4 17 4 12V6z M12 7v6 M12 17h.01",
  agents: "M8 5a4 4 0 1 0 8 0 M4 21v-3a8 8 0 0 1 16 0v3 M2 8h3 M19 8h3",
  vault: "M3 4h18v17H3z M3 8h18 M8 13h8 M12 10v8",
  analytics: "M3 3v18h18 M6 17l5-6 4 3 6-8",
  research: "M9 2v7L3 20h18L15 9V2 M7 2h10 M7 14h10",
  logs: "M5 4h14 M5 9h14 M5 14h14 M5 19h10",
};
export function NavIcon({ name }: { name: IconName }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name]} />
    </svg>
  );
}
