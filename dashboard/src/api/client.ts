import axios from "axios";

const api = axios.create({ baseURL: "/api/v1" });

// Attach JWT on every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Redirect to login on 401
api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem("token");
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

export default api;

// ── Auth ──────────────────────────────────────────────────────────────────────
export async function login(username: string, password: string) {
  const form = new URLSearchParams({ username, password });
  const { data } = await axios.post("/api/v1/auth/token", form.toString(), {
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  });
  return data as { access_token: string; token_type: string; role: string };
}

// ── Devices ───────────────────────────────────────────────────────────────────
export async function fetchDevices(filter?: string) {
  const params: Record<string, string> = {};
  if (filter) params.filter_compliance = filter;
  const { data } = await api.get("/devices", { params });
  return data as { total: number; devices: any[] };
}

// ── Jobs ──────────────────────────────────────────────────────────────────────
export async function fetchJobs(params?: { device_id?: string; status?: string; limit?: number }) {
  const { data } = await api.get("/jobs", { params });
  return data as any[];
}

export async function fetchJob(jobId: string) {
  const { data } = await api.get(`/jobs/${jobId}`);
  return data;
}

export async function retryJob(jobId: string) {
  const { data } = await api.post(`/jobs/${jobId}/retry`);
  return data;
}

// ── Rules ─────────────────────────────────────────────────────────────────────
export async function fetchRules() {
  const { data } = await api.get("/rules");
  return data as any[];
}

export async function createRule(rule: any) {
  const { data } = await api.post("/rules", rule);
  return data;
}

export async function updateRule(id: string, rule: any) {
  const { data } = await api.put(`/rules/${id}`, rule);
  return data;
}

export async function deleteRule(id: string) {
  await api.delete(`/rules/${id}`);
}
