export type StatusTone = "neutral" | "info" | "success" | "warning" | "critical";

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
  attention_queue: Array<{ label: string; tone?: StatusTone; value?: number | string; detail?: string }>;
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
    summary?: {
      symbol_count?: number;
      net_floating_pnl?: number;
      protected_count?: number;
      incomplete_protection_count?: number;
      aged_trade_count?: number;
      stale_update_count?: number;
      floating_loss_count?: number;
      by_symbol?: Array<Record<string, unknown>>;
    };
    drilldown?: Array<Record<string, unknown>>;
  };
  unmatched_closed_deals: {
    count?: number;
    recent?: Array<Record<string, unknown>>;
    dashboard?: {
      summary?: Record<string, unknown>;
      confidence?: {
        heuristic?: string;
        buckets?: Array<Record<string, unknown>>;
        signals?: Array<Record<string, unknown>>;
      };
      lanes?: Array<Record<string, unknown>>;
      reasons?: Array<Record<string, unknown>>;
      symbols?: Array<Record<string, unknown>>;
      manual_buckets?: Array<Record<string, unknown>>;
      recent?: Array<Record<string, unknown>>;
    };
  };
  execution_artifact_warnings?: {
    headline?: string;
    tone?: StatusTone;
    critical_count?: number;
    warning_count?: number;
    missing_count?: number;
    healthy_count?: number;
    artifacts?: Array<Record<string, unknown>>;
  };
  trade_context_registration_failures?: {
    count?: number;
    latest_at?: string | null;
    entry_count?: number;
    exit_count?: number;
    files_scanned?: string[];
    causes?: Array<Record<string, unknown>>;
    strategies?: Array<Record<string, unknown>>;
    recent?: Array<Record<string, unknown>>;
  };
  recent_activity?: {
    window_hours?: number;
    fills?: {
      count?: number;
      total_volume?: number;
      buy_count?: number;
      sell_count?: number;
      latest_at?: string | null;
      top_symbol?: string | null;
      recent?: Array<Record<string, unknown>>;
    };
    exits?: {
      count?: number;
      net_pnl?: number;
      avg_pnl?: number;
      win_count?: number;
      loss_count?: number;
      latest_at?: string | null;
      top_symbol?: string | null;
      recent?: Array<Record<string, unknown>>;
    };
  };
  no_trade_diagnosis?: {
    posture?: string;
    headline?: string;
    detail?: string;
    primary_cause?: string;
    active_cause_count?: number;
    causes?: Array<{
      key: string;
      label: string;
      tone: StatusTone;
      status: "active" | "context" | "clear";
      evidence?: string;
      detail?: string;
    }>;
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
  family_counts: Record<string, number>;
  symbol_counts: Record<string, number>;
  family_comparison?: {
    summary?: {
      family_count?: number;
      strongest_research_family?: Record<string, unknown> | null;
      strongest_live_family?: Record<string, unknown> | null;
      deepest_manifest_family?: Record<string, unknown> | null;
      highest_warning_density_family?: Record<string, unknown> | null;
    };
    rows?: Array<Record<string, unknown>>;
  };
}

export interface ManifestResponse {
  schema_version: number;
  generated_at?: string | null;
  source: string;
  entry_count: number;
  entries: Array<Record<string, unknown>>;
}

export interface StrategySummaryResponse {
  name: string;
  symbol?: string;
  timeframe?: string;
  status?: string;
  tier?: string;
  score?: number | null;
  family?: string | null;
  motif?: string | null;
  archived?: boolean;
  has_strategy_payload?: boolean;
  last_manifest_rank?: number | null;
  in_manifest?: boolean;
  pool_score?: number | null;
}

export interface StrategyDetailResponse {
  name: string;
  manifest_entry?: Record<string, unknown> | null;
  index_entry?: Record<string, unknown> | null;
  pool_record?: Record<string, unknown> | null;
  live_stats?: Record<string, unknown> | null;
  derived?: Record<string, unknown> | null;
}

export interface ResearchSummaryResponse {
  generated_at: string;
  symbol: string;
  timeframe: string;
  families: Record<string, unknown>;
  funnel_totals: Record<string, number>;
  rejection_totals: Record<string, number>;
  top_rejection_samples: Record<string, string[]>;
  family_skip_drilldown?: Array<{
    family: string;
    generated: number;
    accepted: number;
    rejection_count: number;
    conversion_pct: number;
    top_rejection: string;
    reasons: Array<{
      reason: string;
      count: number;
      samples: string[];
    }>;
  }>;
  comparison?: Record<string, unknown>;
  available_filters?: {
    symbols?: string[];
    timeframes?: string[];
    timeframes_by_symbol?: Record<string, string[]>;
  };
}

export interface DriftSummaryRow {
  name: string;
  symbol?: string | null;
  timeframe?: string | null;
  status?: string | null;
  family?: string | null;
  research_return_pct?: number | null;
  research_sharpe?: number | null;
  live_total_pnl?: number | null;
  live_trades?: number | null;
  recent_avg_pnl?: number | null;
  recent_pnls?: number[] | null;
  best_regime?: string | null;
  worst_regime?: string | null;
  live_observed_regime?: string | null;
  regime_alignment?: "aligned" | "mismatch" | "insufficient_live_data" | "unknown" | null;
  drift_score?: number | null;
  decay_warning?: boolean | null;
  decay_warning_count?: number | null;
  latest_decay_reason?: string | null;
  severity?: "healthy" | "watch" | "drifting" | "broken" | null;
  last_update?: string | null;
  unmatched_close_count?: number | null;
  unresolved_anomalies?: string[] | null;
  unresolved_anomaly_count?: number | null;
  needs_manual_review?: boolean | null;
  review_reasons?: string[] | null;
}

export interface DriftSummaryResponse {
  generated_at: string;
  rows: DriftSummaryRow[];
  manual_review_queue?: DriftSummaryRow[];
  summary: {
    strategy_count?: number;
    attention_count?: number;
    decay_warning_count?: number;
    repeated_decay_strategy_count?: number;
    negative_recent_avg_count?: number;
    manual_review_count?: number;
    severity_counts?: Record<string, number>;
    regime_alignment_counts?: Record<string, number>;
    unresolved_anomaly_groups?: Record<string, number>;
    available_filters?: {
      symbols?: string[];
      families?: string[];
      statuses?: string[];
      severities?: string[];
    };
    [key: string]: unknown;
  };
}

export interface ReviewQueueRow {
  name: string;
  symbol?: string | null;
  timeframe?: string | null;
  status?: string | null;
  tier?: string | null;
  family?: string | null;
  score?: number | null;
  manifest_rank?: number | null;
  manifest_floor_score?: number | null;
  promotion_gap?: number | null;
  category_flags?: string[] | null;
  triage_bucket?: "promote_watch" | "demote_watch" | "inspect" | "archive" | null;
  triage_reasons?: string[] | null;
  drift_severity?: "healthy" | "watch" | "drifting" | "broken" | null;
  drift_score?: number | null;
  research_return_pct?: number | null;
  live_total_pnl?: number | null;
  recent_avg_pnl?: number | null;
  regime_alignment?: "aligned" | "mismatch" | "insufficient_live_data" | "unknown" | null;
  last_update?: string | null;
  stale_hours?: number | null;
  unmatched_close_count?: number | null;
  decay_warning_count?: number | null;
  unresolved_anomaly_count?: number | null;
  family_mismatch?: boolean | null;
  regime_mismatch?: boolean | null;
}

export interface ReviewQueueResponse {
  generated_at: string;
  rows: ReviewQueueRow[];
  summary: {
    queue_count?: number;
    category_counts?: Record<string, number>;
    triage_counts?: Record<string, number>;
    status_counts?: Record<string, number>;
    available_filters?: {
      symbols?: string[];
      statuses?: string[];
      categories?: string[];
      triage_buckets?: Array<"promote_watch" | "demote_watch" | "inspect" | "archive">;
    };
    [key: string]: unknown;
  };
}

export interface AuditTimelineResponse {
  generated_at: string;
  events: Array<Record<string, unknown>>;
}

export interface ManualTradeRiskCalcRequest {
  symbol: string;
  side: "buy" | "sell";
  entry_price: number;
  risk_mode: "money" | "equity_pct";
  risk_value: number;
  stop_loss_mode: "pips" | "price";
  stop_loss_input: number;
  take_profit_mode?: "pips" | "price";
  take_profit_input?: number;
  account_equity?: number;
  leverage?: number;
  order_type?: "market" | "limit";
}

export interface ManualTradeRiskCalcResponse {
  generated_at: string;
  symbol_spec: Record<string, unknown>;
  symbol_spec_warnings: string[];
  derived: Record<string, unknown>;
  preview_payload: Record<string, unknown>;
}

export interface OperatorValidationDetail {
  code?: string;
  message?: string;
  field?: string;
  meta?: Record<string, unknown>;
}
