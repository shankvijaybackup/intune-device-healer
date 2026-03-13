import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchDevices } from "../api/client";
import StatusBadge from "../components/StatusBadge";

const FILTERS = ["all", "compliant", "noncompliant", "unknown"] as const;

export default function Devices() {
  const [filter, setFilter] = useState<string>("all");
  const { data, isLoading } = useQuery({
    queryKey: ["devices", filter],
    queryFn: () => fetchDevices(filter === "all" ? undefined : filter),
  });

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Devices</h1>

      <div className="flex gap-2">
        {FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              filter === f ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-400 hover:bg-gray-700"
            }`}
          >
            {f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}
      </div>

      {isLoading ? (
        <p className="text-gray-400">Loading…</p>
      ) : (
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="border-b border-gray-800">
              <tr className="text-left text-gray-500">
                <th className="px-4 py-3">Device Name</th>
                <th className="px-4 py-3">OS</th>
                <th className="px-4 py-3">Compliance</th>
                <th className="px-4 py-3">Owner</th>
                <th className="px-4 py-3">Last Sync</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {(data?.devices ?? []).map((d: any) => (
                <tr key={d.id} className="hover:bg-gray-800/40">
                  <td className="px-4 py-3 text-white font-medium">{d.deviceName}</td>
                  <td className="px-4 py-3 text-gray-400">{d.operatingSystem}</td>
                  <td className="px-4 py-3"><StatusBadge value={d.complianceState} /></td>
                  <td className="px-4 py-3 text-gray-400">{d.userPrincipalName ?? "—"}</td>
                  <td className="px-4 py-3 text-gray-400">
                    {d.lastSyncDateTime ? new Date(d.lastSyncDateTime).toLocaleString() : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="px-4 py-3 border-t border-gray-800 text-xs text-gray-500">
            {data?.total ?? 0} device(s)
          </div>
        </div>
      )}
    </div>
  );
}
