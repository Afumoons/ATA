import type {
  AuditTimelineResponse,
  ExecutionSummaryResponse,
  ManifestResponse,
  ManualTradePreviewAuditResponse,
  ManualTradeRiskCalcRequest,
  ManualTradeRiskCalcResponse,
  OverviewResponse,
  DriftSummaryResponse,
  OperatorValidationDetail,
  PoolSummaryResponse,
  ResearchSummaryResponse,
  ReviewQueueResponse,
  StrategyDetailResponse,
  StrategySummaryResponse,
} from "./types";

const API_BASE = (process.env.NEXT_PUBLIC_UI_API_BASE ?? "/api").replace(/\/$/, "");

export type UiApiErrorKind = "backend-unreachable" | "http-failure" | "malformed-payload";

export class UiApiError extends Error {
  kind: UiApiErrorKind;
  endpoint: string;
  status?: number;
  statusText?: string;
  detail?: string;
  operatorDetail?: OperatorValidationDetail;

  constructor({
    kind,
    endpoint,
    message,
    status,
    statusText,
      detail,
      operatorDetail,
    }: {
      kind: UiApiErrorKind;
      endpoint: string;
      message: string;
      status?: number;
      statusText?: string;
      detail?: string;
      operatorDetail?: OperatorValidationDetail;
  }) {
    super(message);
    this.name = "UiApiError";
    this.kind = kind;
    this.endpoint = endpoint;
    this.status = status;
    this.statusText = statusText;
    this.detail = detail;
    this.operatorDetail = operatorDetail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const endpoint = `${API_BASE}${path}`;

  let response: Response;
  try {
    response = await fetch(endpoint, {
      headers: { Accept: "application/json", ...(init?.headers ?? {}) },
      cache: "no-store",
      ...init,
    });
  } catch (error) {
    throw new UiApiError({
      kind: "backend-unreachable",
      endpoint,
      message: "The UI API could not be reached.",
      detail: error instanceof Error ? error.message : String(error),
    });
  }

  const raw = await response.text();
  let parsed: unknown;
  if (raw) {
    try {
      parsed = JSON.parse(raw);
    } catch {
      parsed = undefined;
    }
  }

  if (!response.ok) {
    const operatorDetail = parsed && typeof parsed === "object" && "detail" in parsed
      ? (parsed as { detail?: OperatorValidationDetail }).detail
      : undefined;

    throw new UiApiError({
      kind: "http-failure",
      endpoint,
      message: `The UI API returned ${response.status} ${response.statusText}.`,
      status: response.status,
      statusText: response.statusText,
      detail: raw.slice(0, 280) || undefined,
      operatorDetail,
    });
  }

  try {
    return raw ? ((parsed ?? JSON.parse(raw)) as T) : ({} as T);
  } catch (error) {
    throw new UiApiError({
      kind: "malformed-payload",
      endpoint,
      message: "The UI API responded, but the payload was not valid JSON.",
      status: response.status,
      statusText: response.statusText,
      detail: error instanceof Error ? error.message : raw.slice(0, 280),
    });
  }
}

export const uiApi = {
  overview: () => request<OverviewResponse>("/overview"),
  executionSummary: () => request<ExecutionSummaryResponse>("/execution/summary"),
  poolSummary: () => request<PoolSummaryResponse>("/pool/summary"),
  researchSummary: (symbol = "XAUUSDm", timeframe = "M15") => request<ResearchSummaryResponse>(`/research/summary?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}`),
  driftSummary: () => request<DriftSummaryResponse>("/drift/summary"),
  reviewQueue: () => request<ReviewQueueResponse>("/review/queue"),
  manifest: () => request<ManifestResponse>("/manifest"),
  strategies: () => request<StrategySummaryResponse[]>("/strategies"),
  strategyDetail: (name: string) => request<StrategyDetailResponse>(`/strategies/${encodeURIComponent(name)}`),
  auditTimeline: (limit = 100) => request<AuditTimelineResponse>(`/audit/timeline?limit=${limit}`),
  manualTradeRiskCalc: (payload: ManualTradeRiskCalcRequest) => request<ManualTradeRiskCalcResponse>("/execution/risk-calc", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }),
  manualTradePreviewIntent: (payload: ManualTradeRiskCalcRequest) => request<ManualTradePreviewAuditResponse>("/execution/manual-ticket/preview-intent", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }),
};
