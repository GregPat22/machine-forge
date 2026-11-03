const paths = {
  overview: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  model: "m12 3 9 5v9l-9 5-9-5V8z M3 8l9 5 9-5 M12 13v9",
  timing: "M4 4v16h17 M8 8h10 M8 12h6 M14 16h7",
  layout: "M3 3h18v18H3z M3 10h18 M10 3v18",
  parts: "M4 7h16v14H4z M2 3h20v4H2z M9 11h6",
  docs: "M5 3h10l4 4v14H5z M14 3v5h5 M8 12h8 M8 16h6",
  history: "M3 11a9 9 0 1 1 2 7 M3 4v7h7 M12 7v6l4 2",
  arrow: "M5 12h14 M13 6l6 6-6 6",
  external: "M6 18 18 6 M6 6h12v12",
  chevron: "m9 6 6 6-6 6",
  question: "M9 9a3 3 0 0 1 6 0c0 2-3 2-3 5 M12 17v.1 M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0",
  close: "m6 6 12 12 M6 18 18 6",
  spark: "m12 3 2 7 7 2-7 2-2 7-2-7-7-2 7-2z",
  menu: "M4 6h16 M4 12h16 M4 18h16",
  machine: "M3 7h18v14H3z M7 7V3h10v4 M7 12h4v4H7z M15 12h2 M15 16h2",
  plc: "M5 3h14v18H5z M8 7h8 M8 11h8 M8 15h2 M14 15h2",
} as const;

export type IconName = keyof typeof paths;
export default function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      aria-hidden="true"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinejoin="round"
      strokeLinecap="round"
    >
      <path d={paths[name]} />
    </svg>
  );
}
