import type {
  AuditTimelineResponse,
  ExecutionSummaryResponse,
  ManifestResponse,
  OverviewResponse,
  PoolSummaryResponse,
} from "./types";

const API_BASE = (process.env.NEXT_PUBLIC_UI_API_BASE ?? "/api").replace(/\/$/, "");

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status} ${response.statusText}`);
  }

  return response.json() as Promise<T>;
}

export const uiApi = {
  overview: () => request<OverviewResponse>("/overview"),
  executionSummary: () => request<ExecutionSummaryResponse>("/execution/summary"),
  poolSummary: () => request<PoolSummaryResponse>("/pool/summary"),
  manifest: () => request<ManifestResponse>("/manifest"),
  auditTimeline: (limit = 100) => request<AuditTimelineResponse>(`/audit/timeline?limit=${limit}`),
};
