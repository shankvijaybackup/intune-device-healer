import { useQuery } from "@tanstack/react-query";
import { fetchDevices, fetchJobs } from "../api/client";
import StatusBadge from "../components/StatusBadge";
import { CheckCircle, AlertTriangle, XCircle, Activity } from "lucide-react";

function StatCard({ label, value, icon: Icon, color }: { label: string; value: number; icon: any; color: string }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm text-gray-400">{label}</span>
        <Icon size={18} className={color} />
      </div>
      <p className="text-3xl font-bold text-white">{value}</p>
    </div>
  );
}

export default function Dashboard() {
  const { data: deviceData } = useQuery({ queryKey: ["devices"], queryFn: () => fetchDevices() });
  const { data: jobs } = useQuery({ queryKey: ["jobs-recent"], queryFn: () => fetchJobs({ limit: 10 }) });

  const devices = deviceData?.devices ?? [];
  const compliant = devices.filter((d) => d.complianceState === "compliant").length;
  const noncompliant = devices.filter((d) => d.complianceState === "noncompliant").length;
  const unknown = devices.length - compliant - noncompliant;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white">Fleet Overview</h1>
        <p className="text-gray-400 text-sm mt-1">Real-time device health &amp; remediation status</p>
      </div>

      <div className="grid grid-cols-4 gap-4">
        <StatCard label="Total Devices" value={devices.length} icon={Activity} color="text-blue-400" />
        <StatCard label="Compliant" value={compliant} icon={CheckCircle} color="text-green-400" />
        <StatCard label="Non-Compliant" value={noncompliant} icon={XCircle} color="text-red-400" />
        <StatCard label="Unknown" value={unknown} icon={AlertTriangle} color="text-yellow-400" />
      </div>

      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
        <h2 className="text-sm font-semibold text-gray-300 mb-4">Recent Remediation Jobs</h2>
        {!jobs?.length ? (
          <p className="text-gray-500 text-sm">No jobs yet.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b border-gray-800">
                <th className="pb-2">Job ID</th>
                <th className="pb-2">Device</th>
                <th className="pb-2">Rule</th>
                <th className="pb-2">Status</th>
                <th className="pb-2">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {jobs.map((job: any) => (
                <tr key={job.id} className="hover:bg-gray-800/50">
                  <td className="py-2 font-mono text-xs text-gray-400">{job.id.slice(0, 8)}…</td>
                  <td className="py-2 text-white">{job.device_id}</td>
                  <td className="py-2 text-gray-300">{job.rule_name ?? "—"}</td>
                  <td className="py-2"><StatusBadge value={job.status} /></td>
                  <td className="py-2 text-gray-400">{new Date(job.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
