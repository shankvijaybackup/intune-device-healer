import clsx from "clsx";

const palette: Record<string, string> = {
  // Job status
  pending:   "bg-yellow-900 text-yellow-300",
  running:   "bg-blue-900 text-blue-300",
  success:   "bg-green-900 text-green-300",
  failed:    "bg-red-900 text-red-300",
  escalated: "bg-purple-900 text-purple-300",
  // Device compliance
  compliant:    "bg-green-900 text-green-300",
  noncompliant: "bg-red-900 text-red-300",
  unknown:      "bg-gray-700 text-gray-300",
  // Priority
  critical: "bg-red-900 text-red-300",
  high:     "bg-orange-900 text-orange-300",
  medium:   "bg-yellow-900 text-yellow-300",
  low:      "bg-gray-700 text-gray-300",
};

export default function StatusBadge({ value }: { value: string }) {
  return (
    <span className={clsx("inline-block px-2 py-0.5 rounded text-xs font-medium", palette[value] ?? "bg-gray-700 text-gray-300")}>
      {value}
    </span>
  );
}
