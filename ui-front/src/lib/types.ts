export type StatusTone = "neutral" | "positive" | "warning" | "danger" | "info";

export interface OverviewResponse {
  generated_at: string;
  live_state_date?: string | null;
  equity_current?: number | null;
  daily_pnl?: number | null;
  trades_today?: number | null;
  locked_for_day?: boolean | null;
  pool_total: number;
  pool_status_counts: Record<string, number>;
  manifest_entry_count: number;
  strategy_index_entry_count: number;
  live_slots: Array<{ symbol: string; timeframe: string; count: number }>;
  diagnostics: Record<string, unknown>;
}

export interface ExecutionSummaryResponse {
  generated_at: string;
  live_state: Record<string, unknown>;
  strategy_live_stats: {
    strategy_count?: number;
    total_realized_pnl?: number;
    total_trades?: number;
    top_active?: Array<Record<string, unknown>>;
  };
  open_trades: {
    count?: number;
    trades?: Array<Record<string, unknown>>;
  };
  unmatched_closed_deals: {
    count?: number;
    recent?: Array<Record<string, unknown>>;
  };
  recent_trade_log: Array<Record<string, unknown>>;
}

export interface PoolSummaryResponse {
  generated_at: string;
  total: number;
  status_counts: Record<string, number>;
  by_slot: Array<{ symbol: string; timeframe: string; count: number }>;
  top_strategies: Array<{
    name: string;
    symbol: string;
    timeframe: string;
    status: string;
    score?: number | null;
  }>;
}

export interface ManifestResponse {
  schema_version: number;
  generated_at?: string | null;
  source: string;
  entry_count: number;
  entries: Array<Record<string, unknown>>;
}

export interface AuditTimelineResponse {
  generated_at: string;
  events: Array<Record<string, unknown>>;
}
