import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchJobs, retryJob } from "../api/client";
import StatusBadge from "../components/StatusBadge";
import { RefreshCw } from "lucide-react";

export default function Jobs() {
  const [status, setStatus] = useState("");
  const qc = useQueryClient();

  const { data: jobs, isLoading } = useQuery({
    queryKey: ["jobs", status],
    queryFn: () => fetchJobs({ status: status || undefined, limit: 100 }),
    refetchInterval: 10_000,
  });

  const retry = useMutation({
    mutationFn: retryJob,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });

  const STATUSES = ["", "pending", "running", "success", "failed", "escalated"];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Remediation Jobs</h1>

      <div className="flex gap-2">
        {STATUSES.map((s) => (
          <button
            key={s || "all"}
            onClick={() => setStatus(s)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              status === s ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-400 hover:bg-gray-700"
            }`}
          >
            {s || "All"}
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
                <th className="px-4 py-3">Job ID</th>
                <th className="px-4 py-3">Device</th>
                <th className="px-4 py-3">Rule</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Progress</th>
                <th className="px-4 py-3">Created</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {(jobs ?? []).map((job: any) => (
                <tr key={job.id} className="hover:bg-gray-800/40">
                  <td className="px-4 py-3 font-mono text-xs text-gray-400">{job.id.slice(0, 8)}…</td>
                  <td className="px-4 py-3 text-white">{job.device_id}</td>
                  <td className="px-4 py-3 text-gray-300">{job.rule_name ?? "—"}</td>
                  <td className="px-4 py-3"><StatusBadge value={job.status} /></td>
                  <td className="px-4 py-3 text-gray-400 text-xs">
                    {job.steps_done}/{job.steps_total} steps
                  </td>
                  <td className="px-4 py-3 text-gray-400 text-xs">
                    {new Date(job.created_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-3">
                    {(job.status === "failed" || job.status === "escalated") && (
                      <button
                        onClick={() => retry.mutate(job.id)}
                        className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 transition-colors"
                        title="Retry job"
                      >
                        <RefreshCw size={12} /> Retry
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
