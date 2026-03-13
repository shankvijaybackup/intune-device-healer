import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchRules, deleteRule } from "../api/client";
import StatusBadge from "../components/StatusBadge";
import { Trash2 } from "lucide-react";

export default function Rules() {
  const qc = useQueryClient();
  const { data: rules, isLoading } = useQuery({ queryKey: ["rules"], queryFn: fetchRules });

  const remove = useMutation({
    mutationFn: deleteRule,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rules"] }),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Remediation Rules</h1>
        <span className="text-xs text-gray-500">Edit rules.yaml and restart to add YAML-sourced rules</span>
      </div>

      {isLoading ? (
        <p className="text-gray-400">Loading…</p>
      ) : (
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="border-b border-gray-800">
              <tr className="text-left text-gray-500">
                <th className="px-4 py-3">ID</th>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Trigger</th>
                <th className="px-4 py-3">Priority</th>
                <th className="px-4 py-3">Enabled</th>
                <th className="px-4 py-3">Source</th>
                <th className="px-4 py-3">Steps</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {(rules ?? []).map((rule: any) => (
                <tr key={rule.id} className="hover:bg-gray-800/40">
                  <td className="px-4 py-3 font-mono text-xs text-gray-400">{rule.id}</td>
                  <td className="px-4 py-3 text-white font-medium">{rule.name}</td>
                  <td className="px-4 py-3 font-mono text-xs text-blue-300">
                    {rule.trigger?.failure_type}
                  </td>
                  <td className="px-4 py-3"><StatusBadge value={rule.priority} /></td>
                  <td className="px-4 py-3">
                    <span className={rule.enabled ? "text-green-400" : "text-gray-500"}>
                      {rule.enabled ? "Yes" : "No"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-400 text-xs">{rule.source}</td>
                  <td className="px-4 py-3 text-gray-400 text-xs">
                    {rule.remediation?.steps?.length ?? 0}
                  </td>
                  <td className="px-4 py-3">
                    {rule.source === "api" && (
                      <button
                        onClick={() => remove.mutate(rule.id)}
                        className="text-red-500 hover:text-red-400 transition-colors"
                        title="Delete rule"
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="px-4 py-3 border-t border-gray-800 text-xs text-gray-500">
            {rules?.length ?? 0} rule(s) · YAML-sourced rules are read-only
          </div>
        </div>
      )}
    </div>
  );
}
