import { UiApiError } from "@/lib/api";
import { compactValue, formatDateTime, formatRelativeAge, prettifyKey } from "@/lib/format";
import type { ExecutionSummaryResponse, StatusTone } from "@/lib/types";

export function toneFromSignedNumber(value: number | null | undefined): StatusTone {
  if (value == null || Number.isNaN(value) || value === 0) return "neutral";
  return value > 0 ? "success" : "critical";
}

export function toneFromBoolean(value: boolean | null | undefined, positive = true): StatusTone {
  if (value == null) return "neutral";
  if (positive) return value ? "success" : "warning";
  return value ? "warning" : "success";
}

export function getFreshnessState(
  timestamp: unknown,
  thresholds?: { warningMs?: number; criticalMs?: number },
): {
  label: string;
  tone: StatusTone;
  description: string;
  isStale: boolean;
} {
  const warningMs = thresholds?.warningMs ?? 5 * 60_000;
  const criticalMs = thresholds?.criticalMs ?? 20 * 60_000;

  if (!timestamp || typeof timestamp !== "string") {
    return {
      label: "Freshness unknown",
      tone: "warning",
      description: "The payload does not expose a usable generated_at timestamp.",
      isStale: true,
    };
  }

  const parsed = new Date(timestamp);
  if (Number.isNaN(parsed.getTime())) {
    return {
      label: "Freshness unknown",
      tone: "warning",
      description: `Timestamp could not be parsed: ${String(timestamp)}`,
      isStale: true,
    };
  }

  const ageMs = Date.now() - parsed.getTime();
  if (ageMs >= criticalMs) {
    return {
      label: `Critical stale · ${formatRelativeAge(timestamp)}`,
      tone: "critical",
      description: `Snapshot time ${formatDateTime(timestamp)}`,
      isStale: true,
    };
  }

  if (ageMs >= warningMs) {
    return {
      label: `Stale · ${formatRelativeAge(timestamp)}`,
      tone: "warning",
      description: `Snapshot time ${formatDateTime(timestamp)}`,
      isStale: true,
    };
  }

  return {
    label: `Fresh · ${formatRelativeAge(timestamp)}`,
    tone: "success",
    description: `Snapshot time ${formatDateTime(timestamp)}`,
    isStale: false,
  };
}

export function describeQueryError(error: unknown, resourceLabel: string) {
  if (error instanceof UiApiError) {
    if (error.kind === "backend-unreachable") {
      return {
        tone: "critical" as const,
        badge: "Backend unreachable",
        title: `Unable to reach ${resourceLabel}`,
        description:
          "The frontend could not connect to the UI API at all. Check the backend service, local networking, and NEXT_PUBLIC_UI_API_BASE.",
        detail: error.detail,
      };
    }

    if (error.kind === "http-failure") {
      return {
        tone: error.status && error.status >= 500 ? ("critical" as const) : ("warning" as const),
        badge: `HTTP ${error.status ?? "error"}`,
        title: `${resourceLabel} request failed`,
        description:
          "The UI API responded, but the request did not succeed. This is usually a route, backend, or upstream adapter problem rather than a browser issue.",
        detail: error.detail || error.message,
      };
    }

    return {
      tone: "warning" as const,
      badge: "Malformed payload",
      title: `${resourceLabel} payload is not usable`,
      description:
        "The UI API responded with content that could not be parsed as valid JSON. The route is up, but the payload shape is broken for the operator UI.",
      detail: error.detail || error.message,
    };
  }

  return {
    tone: "critical" as const,
    badge: "Unknown failure",
    title: `Unable to load ${resourceLabel}`,
    description: "The request failed in an unexpected way before the UI could classify it.",
    detail: error instanceof Error ? error.message : String(error),
  };
}

export function coerceRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return value as Record<string, unknown>;
}

export function hasRecordContent(value: unknown) {
  return Object.keys(coerceRecord(value)).length > 0;
}

export function pickFirstString(...values: unknown[]) {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value;
  }
  return null;
}

export function pickFirstNumber(...values: unknown[]) {
  for (const value of values) {
    if (typeof value === "number" && Number.isFinite(value)) return value;
  }
  return null;
}

export function getEventTimestamp(event: Record<string, unknown>) {
  return pickFirstString(event.recorded_at, event.last_update, event.generated_at, event.timestamp, event.closed_at, event.open_time);
}

export function getEventStrategyName(event: Record<string, unknown>) {
  return pickFirstString(event.strategy_name, event.strategy, event.comment, event.magic_comment);
}

export function getEventSymbol(event: Record<string, unknown>) {
  return pickFirstString(event.symbol, event.instrument);
}

export function summarizeEvent(event: Record<string, unknown>) {
  const source = pickFirstString(event.source, "event") ?? "event";
  const strategy = getEventStrategyName(event);
  const symbol = getEventSymbol(event);
  const reason = pickFirstString(event.reason, event.event, event.type, event.detail, event.message, event.comment);

  const parts = [prettifyKey(source)];
  if (strategy) parts.push(strategy);
  if (symbol) parts.push(symbol);
  if (reason) parts.push(reason);

  return parts.join(" · ");
}

export function attentionToneForEvent(event: Record<string, unknown>): StatusTone {
  const source = String(event.source ?? "").toLowerCase();
  const reason = String(event.reason ?? event.event ?? event.type ?? "").toLowerCase();
  const profit = pickFirstNumber(event.profit, event.pnl, event.floating_pnl);

  if (source.includes("unmatched") || reason.includes("miss") || reason.includes("error") || reason.includes("fail")) {
    return "critical";
  }
  if (profit != null && profit < 0) return "warning";
  if (source.includes("trade") || source.includes("pool")) return "info";
  return "neutral";
}

export function getHighSignalExecutionReasons(data: ExecutionSummaryResponse) {
  const reasons: Array<{ tone: StatusTone; label: string; detail: string }> = [];
  const locked = Boolean(data.live_state?.locked_for_day);
  const openTrades = Number(data.open_trades?.count ?? 0);
  const liveStrategies = Number(data.strategy_live_stats?.strategy_count ?? 0);
  const totalTrades = Number(data.strategy_live_stats?.total_trades ?? 0);
  const unmatched = Number(data.unmatched_closed_deals?.count ?? 0);
  const recentLogCount = data.recent_trade_log?.length ?? 0;

  if (locked) {
    reasons.push({
      tone: "warning",
      label: "Day lock is active",
      detail: "The backend reports locked_for_day=true, so inactivity may be intentional rather than a runtime failure.",
    });
  }

  if (!locked && openTrades === 0 && recentLogCount === 0) {
    reasons.push({
      tone: "warning",
      label: "No active execution traces",
      detail: "There are no open trades and no recent trade-log entries in this snapshot, so the system currently looks inactive.",
    });
  }

  if (!locked && liveStrategies === 0) {
    reasons.push({
      tone: "critical",
      label: "No live strategy stats",
      detail: "The execution summary returned zero live strategies, which weakens confidence that runtime strategy telemetry is healthy.",
    });
  }

  if (unmatched > 0) {
    reasons.push({
      tone: unmatched >= 5 ? "critical" : "warning",
      label: `${unmatched} unmatched closed deal${unmatched === 1 ? "" : "s"}`,
      detail: "Closed-deal reconciliation is not clean. This deserves operator review even if the rest of the runtime looks healthy.",
    });
  }

  if (!reasons.length) {
    reasons.push({
      tone: totalTrades > 0 || openTrades > 0 ? "success" : "neutral",
      label: totalTrades > 0 || openTrades > 0 ? "Execution feed looks coherent" : "No strong diagnosis signal",
      detail:
        totalTrades > 0 || openTrades > 0
          ? "The runtime is surfacing open trades or live trade counts without obvious reconciliation faults in this snapshot."
          : "Current fields do not strongly explain inactivity yet; more backend hints may still improve no-trade explanation later.",
    });
  }

  return reasons;
}

export function getStrategyRelationshipState(detail: {
  manifest_entry?: Record<string, unknown> | null;
  index_entry?: Record<string, unknown> | null;
  pool_record?: Record<string, unknown> | null;
  live_stats?: Record<string, unknown> | null;
}) {
  const inManifest = hasRecordContent(detail.manifest_entry);
  const inIndex = hasRecordContent(detail.index_entry);
  const inPool = hasRecordContent(detail.pool_record);
  const hasLiveStats = hasRecordContent(detail.live_stats);

  return {
    inManifest,
    inIndex,
    inPool,
    hasLiveStats,
    relationshipBadges: [
      { label: inManifest ? "Manifest present" : "Manifest absent", tone: inManifest ? "success" : "warning" },
      { label: inIndex ? "Index present" : "Index absent", tone: inIndex ? "info" : "warning" },
      { label: inPool ? "Pool present" : "Pool absent", tone: inPool ? "success" : "warning" },
      { label: hasLiveStats ? "Live stats present" : "No live stats", tone: hasLiveStats ? "info" : "neutral" },
    ] as Array<{ label: string; tone: StatusTone }>,
  };
}

export function describeFieldValue(label: string, value: unknown) {
  return `${prettifyKey(label)}: ${compactValue(value)}`;
}
