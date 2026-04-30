"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { PageHeader } from "@/components/app-shell";
import {
  FilterField,
  FilterSelect,
  FilterToolbar,
  InlineNotice,
  KeyValueGrid,
  Section,
  StatCard,
  StatusBadge,
} from "@/components/dashboard";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { uiApi, UiApiError } from "@/lib/api";
import { compactValue, formatCurrency, formatDateTime, formatNumber, formatPercent } from "@/lib/format";
import type {
  ManualTradePreviewAuditResponse,
  ManualTradeRiskCalcResponse,
  ManualTradeSubmitResponse,
  OperatorValidationDetail,
} from "@/lib/types";

const COMMON_SYMBOLS = ["XAUUSDm", "BTCUSDm", "XAGUSDm", "EURUSDm"] as const;

type ManualTicketFormState = {
  symbolMode: "preset" | "custom";
  presetSymbol: string;
  customSymbol: string;
  side: "buy" | "sell";
  orderType: "market" | "limit";
  entryPrice: string;
  riskMode: "money" | "equity_pct";
  riskValue: string;
  stopLossMode: "pips" | "price";
  stopLossInput: string;
  takeProfitEnabled: boolean;
  takeProfitMode: "pips" | "price";
  takeProfitInput: string;
  accountEquity: string;
  leverage: string;
};

const DEFAULT_FORM: ManualTicketFormState = {
  symbolMode: "preset",
  presetSymbol: "XAUUSDm",
  customSymbol: "",
  side: "buy",
  orderType: "market",
  entryPrice: "2300",
  riskMode: "money",
  riskValue: "100",
  stopLossMode: "price",
  stopLossInput: "2295",
  takeProfitEnabled: true,
  takeProfitMode: "price",
  takeProfitInput: "2310",
  accountEquity: "",
  leverage: "100",
};

function parseOptionalNumber(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function buildPayload(form: ManualTicketFormState) {
  const symbol = form.symbolMode === "custom" ? form.customSymbol.trim().toUpperCase() : form.presetSymbol;
  const entryPrice = parseOptionalNumber(form.entryPrice);
  const riskValue = parseOptionalNumber(form.riskValue);
  const stopLossInput = parseOptionalNumber(form.stopLossInput);
  const takeProfitInput = form.takeProfitEnabled ? parseOptionalNumber(form.takeProfitInput) : undefined;

  if (!symbol || entryPrice == null || riskValue == null || stopLossInput == null) {
    return null;
  }

  if (form.takeProfitEnabled && takeProfitInput == null) {
    return null;
  }

  return {
    symbol,
    side: form.side,
    order_type: form.orderType,
    entry_price: entryPrice,
    risk_mode: form.riskMode,
    risk_value: riskValue,
    stop_loss_mode: form.stopLossMode,
    stop_loss_input: stopLossInput,
    take_profit_mode: form.takeProfitEnabled ? form.takeProfitMode : undefined,
    take_profit_input: form.takeProfitEnabled ? takeProfitInput : undefined,
    account_equity: parseOptionalNumber(form.accountEquity),
    leverage: parseOptionalNumber(form.leverage),
  };
}

function getOperatorValidationDetail(error: unknown): OperatorValidationDetail | null {
  if (error instanceof UiApiError) {
    return error.operatorDetail ?? null;
  }
  return null;
}

function formatPlainNumber(value: unknown, maximumFractionDigits = 2) {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  return formatNumber(value, { maximumFractionDigits });
}

function buildClientSubmissionId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `manual-${crypto.randomUUID()}`;
  }
  return `manual-${Date.now()}`;
}

function formatWarningLabel(value: string) {
  return value.replace(/_/g, " ");
}

function explainManualTicketWarning(
  warning: string,
  context: {
    riskMode: ManualTicketFormState["riskMode"];
    orderType: ManualTicketFormState["orderType"];
    hasEquityOverride: boolean;
  },
) {
  switch (warning) {
    case "stop_loss_tighter_than_tick_size":
      return {
        title: "Stop loss lebih rapat dari tick broker",
        description: "Jarak SL setelah normalisasi lebih kecil dari tick minimum broker. Broker bisa menolak draft ini atau membulatkan harga sehingga proteksi tidak sesuai niat awal.",
      };
    case "risk_sizing_below_min_lot":
      return {
        title: "Risk terlalu kecil untuk min lot",
        description: `Ukuran lot hasil sizing jatuh di bawah min lot broker, jadi ticket ini tidak bisa mempertahankan risk ${context.riskMode === "money" ? "uang" : "% equity"} yang diminta. Kurangi jarak SL atau naikkan risk agar draft menjadi executable.`,
      };
    case "risk_sizing_exceeds_max_lot":
      return {
        title: "Risk butuh lot di atas batas broker",
        description: "Perhitungan sizing melewati max lot broker. Draft akan dipotong ke batas maksimum, jadi eksposur riil bisa berbeda dari niat awal dan perlu dicek ulang sebelum preview/submit.",
      };
    case "rounded_lot_reduces_risk_below_requested":
      return {
        title: "Pembulatan lot menurunkan risk aktual",
        description: "Backend membulatkan lot ke step broker terdekat ke bawah. Akibatnya risk aktual di SL menjadi lebih kecil dari target yang diminta. Ini aman, tetapi operator perlu sadar bahwa sizing tidak presisi 1:1.",
      };
    case "invalid_digits":
      return {
        title: "Metadata digit symbol tidak valid",
        description: "Broker metadata untuk symbol ini tidak punya digit price yang masuk akal. Pilih symbol lain atau tunggu metadata resolver pulih sebelum lanjut.",
      };
    case "min_lot_exceeds_max_lot":
      return {
        title: "Metadata lot broker kontradiktif",
        description: "min lot lebih besar dari max lot pada metadata symbol. Ticket ini sebaiknya tidak dipakai sampai spesifikasi symbol dari broker kembali normal.",
      };
    case "lot_step_exceeds_max_lot":
      return {
        title: "Lot step broker tidak masuk akal",
        description: "Kenaikan lot minimum lebih besar dari max lot. Ini menandakan metadata symbol rusak atau tidak lengkap, jadi sizing tidak bisa dipercaya.",
      };
    default:
      if (warning.startsWith("missing_or_non_positive_")) {
        const field = warning.replace("missing_or_non_positive_", "");
        return {
          title: `Metadata ${formatWarningLabel(field)} belum valid`,
          description: "Salah satu field spesifikasi broker yang dipakai untuk sizing masih kosong atau bernilai nol. Calculator boleh memberi sinyal, tetapi draft tidak layak lanjut sampai metadata symbol valid.",
        };
      }
      return {
        title: formatWarningLabel(warning),
        description: `Periksa kembali geometry ${context.orderType === "limit" ? "pending-limit" : "market reference"}, batas broker, dan hasil pembulatan sizing sebelum masuk ke tahap preview dan submit.${context.riskMode === "equity_pct" && !context.hasEquityOverride ? " Jika mode % equity terasa janggal, pertimbangkan isi equity override untuk cross-check cepat." : ""}`,
      };
  }
}

export default function ManualTicketPage() {
  const [form, setForm] = useState<ManualTicketFormState>(DEFAULT_FORM);
  const [calc, setCalc] = useState<ManualTradeRiskCalcResponse | null>(null);
  const [calcError, setCalcError] = useState<unknown>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [previewAudit, setPreviewAudit] = useState<ManualTradePreviewAuditResponse | null>(null);
  const [previewAuditStatus, setPreviewAuditStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [previewAuditError, setPreviewAuditError] = useState<unknown>(null);
  const [previewConfirmed, setPreviewConfirmed] = useState(false);
  const [submitConfirmed, setSubmitConfirmed] = useState(false);
  const [submitResponse, setSubmitResponse] = useState<ManualTradeSubmitResponse | null>(null);
  const [submitStatus, setSubmitStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [submitError, setSubmitError] = useState<unknown>(null);
  const [clientSubmissionId, setClientSubmissionId] = useState(() => buildClientSubmissionId());
  const requestSeq = useRef(0);

  const payload = useMemo(() => buildPayload(form), [form]);
  const operatorError = getOperatorValidationDetail(calcError);
  const metadataUnavailable = operatorError?.code === "symbol_metadata_unavailable";
  const accountSnapshotUnavailable = operatorError?.code === "account_snapshot_unavailable";
  const accountEquityUnavailable = operatorError?.code === "account_equity_unavailable";
  const derived = calc?.derived ?? {};
  const previewPayload = calc?.preview_payload ?? {};
  const symbolSpec = calc?.symbol_spec ?? {};
  const warnings = [
    ...(calc?.symbol_spec_warnings ?? []),
    ...((Array.isArray(derived.warnings) ? derived.warnings : []) as string[]),
  ];
  const warningNotices = warnings.map((warning) => ({
    warning,
    ...explainManualTicketWarning(warning, {
      riskMode: form.riskMode,
      orderType: form.orderType,
      hasEquityOverride: Boolean(form.accountEquity.trim()),
    }),
  }));
  const previewAuditEvent = previewAudit?.audit_event ?? {};
  const brokerValidation = previewAudit?.broker_validation ?? {};
  const previewOperatorError = getOperatorValidationDetail(previewAuditError);
  const submitOperatorError = getOperatorValidationDetail(submitError);
  const submitBrokerResponse: Record<string, unknown> = submitResponse?.broker_response ?? {};
  const submitAuditAfter: Record<string, unknown> = submitResponse?.audit_event_after ?? {};

  useEffect(() => {
    if (!payload) {
      setCalc(null);
      setCalcError(null);
      setStatus("idle");
      return;
    }

    const currentSeq = ++requestSeq.current;
    setStatus("loading");
    setPreviewConfirmed(false);

    const timeout = window.setTimeout(() => {
      void uiApi.manualTradeRiskCalc(payload)
        .then((response) => {
          if (currentSeq !== requestSeq.current) return;
          setCalc(response);
          setCalcError(null);
          setStatus("success");
          setPreviewAudit(null);
          setPreviewAuditStatus("idle");
          setPreviewAuditError(null);
          setSubmitConfirmed(false);
          setSubmitResponse(null);
          setSubmitStatus("idle");
          setSubmitError(null);
          setClientSubmissionId(buildClientSubmissionId());
        })
        .catch((error) => {
          if (currentSeq !== requestSeq.current) return;
          setCalc(null);
          setCalcError(error);
          setStatus("error");
          setPreviewAudit(null);
          setPreviewAuditStatus("idle");
          setPreviewAuditError(null);
          setSubmitConfirmed(false);
          setSubmitResponse(null);
          setSubmitStatus("idle");
          setSubmitError(null);
        });
    }, 350);

    return () => {
      window.clearTimeout(timeout);
    };
  }, [payload]);

  const symbolLabel = form.symbolMode === "custom" ? form.customSymbol.trim().toUpperCase() || "Custom symbol" : form.presetSymbol;
  const entryLabel = form.orderType === "market" ? "Reference market price" : "Pending entry price";
  const draftStepState = !payload ? "blocked" : status === "success" ? "ready" : status === "loading" ? "active" : status === "error" ? "warning" : "active";
  const previewStepState = previewAuditStatus === "success" ? "ready" : previewAuditStatus === "loading" ? "active" : previewConfirmed ? "warning" : "blocked";
  const submitStepState = submitStatus === "success" ? "ready" : submitStatus === "loading" ? "active" : previewAuditStatus === "success" ? "warning" : "blocked";

  async function handleRecordPreviewIntent() {
    if (!payload || !calc || !previewConfirmed) return;
    setPreviewAuditStatus("loading");
    setPreviewAuditError(null);
    setSubmitConfirmed(false);
    setSubmitResponse(null);
    setSubmitStatus("idle");
    setSubmitError(null);
    setClientSubmissionId(buildClientSubmissionId());
    try {
      const response = await uiApi.manualTradePreviewIntent(payload);
      setPreviewAudit(response);
      setPreviewAuditStatus("success");
    } catch (error) {
      setPreviewAuditError(error);
      setPreviewAuditStatus("error");
    }
  }

  async function handleSubmitManualTrade() {
    if (!payload || !calc || !previewAudit || !previewConfirmed || !submitConfirmed) return;
    setSubmitStatus("loading");
    setSubmitError(null);
    try {
      const response = await uiApi.manualTradeSubmit({
        ...payload,
        confirm_submit: true,
        client_submission_id: clientSubmissionId,
      });
      setSubmitResponse(response);
      setSubmitStatus("success");
    } catch (error) {
      setSubmitError(error);
      setSubmitStatus("error");
    }
  }

  return (
    <div className="dashboard-stack">
      <PageHeader
        title="Manual trade ticket"
        subtitle="Calculator-only operator ticket for risk-based manual trades. Every preview stays explicitly tagged as manual_user and separate from autonomous strategy attribution."
        meta={calc?.generated_at ? `Last calc ${formatDateTime(calc.generated_at)}` : "Awaiting complete inputs"}
        action={<StatusBadge label={status === "loading" ? "Calculating" : status === "success" ? "Calculator ready" : "Drafting"} tone={status === "error" ? "warning" : status === "success" ? "success" : "info"} />}
      />

      <InlineNotice
        tone="info"
        title="Manual-user segregation is locked in"
        description="This slice is calculator and preview only. Any payload shown here is pre-tagged with order_origin=manual_user, execution_origin=operator_ui, is_manual=true, and exclude_from_strategy_eval=true."
      />

      <section className="manual-ticket-stage-grid" aria-label="Manual ticket workflow status">
        <article className={`manual-ticket-stage-card is-${draftStepState}`}>
          <div>
            <p className="manual-ticket-stage-eyebrow">Step 1</p>
            <h3>Draft and sizing</h3>
          </div>
          <p>Isi geometry order, risk, dan SL/TP sampai calculator memberi draft yang valid untuk <strong>{symbolLabel || "manual_user"}</strong>.</p>
          <StatusBadge label={draftStepState === "ready" ? "Calculator ready" : draftStepState === "warning" ? "Check inputs" : draftStepState === "active" ? "Drafting" : "Waiting for required fields"} tone={draftStepState === "ready" ? "success" : draftStepState === "warning" ? "warning" : "info"} />
        </article>
        <article className={`manual-ticket-stage-card is-${previewStepState}`}>
          <div>
            <p className="manual-ticket-stage-eyebrow">Step 2</p>
            <h3>Broker preview audit</h3>
          </div>
          <p>Konfirmasi manual_user lalu validasi ke broker agar snapshot preview tercatat ke audit sebelum submit live dibuka.</p>
          <StatusBadge label={previewStepState === "ready" ? "Preview validated" : previewStepState === "warning" ? "Confirmation ready" : previewStepState === "active" ? "Validating preview" : "Preview still locked"} tone={previewStepState === "ready" ? "success" : previewStepState === "warning" ? "warning" : "info"} />
        </article>
        <article className={`manual-ticket-stage-card is-${submitStepState}`}>
          <div>
            <p className="manual-ticket-stage-eyebrow">Step 3</p>
            <h3>Explicit live submit</h3>
          </div>
          <p>Submit tetap pakai gate kedua, client submission id idempoten, dan marker manual_user yang tetap terpisah dari statistik strategi.</p>
          <StatusBadge label={submitStepState === "ready" ? "Submit completed" : submitStepState === "warning" ? "Submit can open" : submitStepState === "active" ? "Submitting live" : "Waiting for preview audit"} tone={submitStepState === "ready" ? "success" : submitStepState === "warning" ? "warning" : "info"} />
        </article>
      </section>

      <div className="detail-grid-2 manual-ticket-layout">
        <Card>
          <CardHeader>
            <CardTitle>Ticket inputs</CardTitle>
            <CardDescription>Choose the manual order geometry, risk mode, and SL/TP definition. The calculator refreshes automatically once required fields are valid.</CardDescription>
          </CardHeader>
          <CardContent className="dashboard-stack">
            <FilterToolbar className="manual-ticket-form-grid">
              <FilterField label="Symbol source">
                <FilterSelect value={form.symbolMode} onChange={(event) => setForm((current) => ({ ...current, symbolMode: event.target.value as "preset" | "custom" }))}>
                  <option value="preset">Preset selector</option>
                  <option value="custom">Custom symbol</option>
                </FilterSelect>
              </FilterField>

              {form.symbolMode === "preset" ? (
                <FilterField label="Symbol selector">
                  <FilterSelect value={form.presetSymbol} onChange={(event) => setForm((current) => ({ ...current, presetSymbol: event.target.value }))}>
                    {COMMON_SYMBOLS.map((symbol) => <option key={symbol} value={symbol}>{symbol}</option>)}
                  </FilterSelect>
                </FilterField>
              ) : (
                <FilterField label="Custom symbol">
                  <input className="filter-input" value={form.customSymbol} onChange={(event) => setForm((current) => ({ ...current, customSymbol: event.target.value }))} placeholder="e.g. ETHUSDm" autoCapitalize="characters" />
                </FilterField>
              )}

              <FilterField label="Side">
                <FilterSelect value={form.side} onChange={(event) => setForm((current) => ({ ...current, side: event.target.value as "buy" | "sell" }))}>
                  <option value="buy">Buy</option>
                  <option value="sell">Sell</option>
                </FilterSelect>
              </FilterField>

              <FilterField label="Order type">
                <FilterSelect value={form.orderType} onChange={(event) => setForm((current) => ({ ...current, orderType: event.target.value as "market" | "limit" }))}>
                  <option value="market">Market</option>
                  <option value="limit">Pending / limit</option>
                </FilterSelect>
              </FilterField>

              <FilterField label={entryLabel}>
                <input className="filter-input" inputMode="decimal" value={form.entryPrice} onChange={(event) => setForm((current) => ({ ...current, entryPrice: event.target.value }))} placeholder={form.orderType === "market" ? "Current quoted price" : "Limit entry price"} />
              </FilterField>

              <FilterField label="Risk mode">
                <FilterSelect value={form.riskMode} onChange={(event) => setForm((current) => ({ ...current, riskMode: event.target.value as "money" | "equity_pct" }))}>
                  <option value="money">Money</option>
                  <option value="equity_pct">% equity</option>
                </FilterSelect>
              </FilterField>

              <FilterField label={form.riskMode === "money" ? "Risk value (USD)" : "Risk value (%)"}>
                <input className="filter-input" inputMode="decimal" value={form.riskValue} onChange={(event) => setForm((current) => ({ ...current, riskValue: event.target.value }))} placeholder={form.riskMode === "money" ? "100" : "1"} />
              </FilterField>

              <FilterField label="Stop loss mode">
                <FilterSelect value={form.stopLossMode} onChange={(event) => setForm((current) => ({ ...current, stopLossMode: event.target.value as "pips" | "price" }))}>
                  <option value="pips">By pips</option>
                  <option value="price">By price</option>
                </FilterSelect>
              </FilterField>

              <FilterField label={form.stopLossMode === "pips" ? "Stop loss distance (pips)" : "Stop loss price"}>
                <input className="filter-input" inputMode="decimal" value={form.stopLossInput} onChange={(event) => setForm((current) => ({ ...current, stopLossInput: event.target.value }))} />
              </FilterField>

              <FilterField label="Take profit mode">
                <FilterSelect value={form.takeProfitMode} onChange={(event) => setForm((current) => ({ ...current, takeProfitMode: event.target.value as "pips" | "price" }))} disabled={!form.takeProfitEnabled}>
                  <option value="pips">By pips</option>
                  <option value="price">By price</option>
                </FilterSelect>
              </FilterField>

              <FilterField label={form.takeProfitEnabled ? (form.takeProfitMode === "pips" ? "Take profit distance (pips)" : "Take profit price") : "Take profit disabled"}>
                <div className="manual-ticket-inline-row">
                  <input className="filter-input" inputMode="decimal" value={form.takeProfitInput} onChange={(event) => setForm((current) => ({ ...current, takeProfitInput: event.target.value }))} disabled={!form.takeProfitEnabled} placeholder={form.takeProfitEnabled ? undefined : "No TP for this draft"} />
                  <Button variant={form.takeProfitEnabled ? "outline" : "secondary"} size="sm" onClick={() => setForm((current) => ({ ...current, takeProfitEnabled: !current.takeProfitEnabled }))}>
                    {form.takeProfitEnabled ? "Disable TP" : "Enable TP"}
                  </Button>
                </div>
              </FilterField>

              <FilterField label="Account equity override (optional)">
                <input className="filter-input" inputMode="decimal" value={form.accountEquity} onChange={(event) => setForm((current) => ({ ...current, accountEquity: event.target.value }))} placeholder="Used if live equity snapshot is stale" />
              </FilterField>

              <FilterField label="Leverage (optional)">
                <input className="filter-input" inputMode="decimal" value={form.leverage} onChange={(event) => setForm((current) => ({ ...current, leverage: event.target.value }))} placeholder="Adds margin estimate" />
              </FilterField>
            </FilterToolbar>

            <div className="manual-ticket-chip-row">
              <StatusBadge label={`${form.side.toUpperCase()} ${symbolLabel || "SYMBOL"}`} tone={form.side === "buy" ? "success" : "warning"} />
              <StatusBadge label={form.orderType === "market" ? "Market reference pricing" : "Limit entry pricing"} tone="info" />
              <StatusBadge label={form.riskMode === "money" ? "Fixed cash risk" : "% equity risk"} tone="neutral" />
              <StatusBadge label="Live submit remains operator-gated" tone="warning" />
            </div>

            {form.orderType === "market" ? (
              <InlineNotice
                tone="info"
                title="Market mode uses a reference price"
                description="This calculator treats entry_price as the latest operator-observed quote. The live-submit phase will still need a confirmation gate and a fresh broker-side fill." 
              />
            ) : (
              <InlineNotice
                tone="warning"
                title="Pending limit price must stay on the valid side"
                description="This first UI slice collects the limit entry explicitly. Broker-side validation still happens later, so keep the pending price aligned with the intended buy-limit or sell-limit geometry."
              />
            )}

            {!payload ? (
              <InlineNotice tone="warning" title="Complete the required fields" description="Symbol, entry price, risk value, and stop loss are required before the live calculator can run." />
            ) : null}

            {operatorError ? (
              <InlineNotice
                tone={metadataUnavailable ? "critical" : accountSnapshotUnavailable || accountEquityUnavailable ? "warning" : "warning"}
                title={metadataUnavailable ? "Symbol metadata unavailable" : accountSnapshotUnavailable ? "Snapshot akun tidak tersedia" : accountEquityUnavailable ? "Equity akun belum tersedia" : "Calculator validation blocked"}
                description={operatorError.message ?? "The backend rejected this ticket draft."}
              />
            ) : null}

            {(accountSnapshotUnavailable || accountEquityUnavailable) && form.riskMode === "equity_pct" ? (
              <InlineNotice
                tone="info"
                title="Fallback untuk mode % equity"
                description={accountSnapshotUnavailable
                  ? "Isi Account equity override agar sizing tetap bisa dihitung saat snapshot akun/live state gagal dibaca. Setelah feed akun pulih, override bisa dikosongkan lagi."
                  : "Isi Account equity override bila snapshot live state belum punya equity_current yang valid, lalu cek proses updater akun bila kondisi ini berulang."}
              />
            ) : null}
          </CardContent>
        </Card>

        <div className="dashboard-stack">
          <Section title="Derived risk snapshot" description="Rounded lot sizing, normalized exit prices, and operator-facing warnings from the backend sizing engine.">
            {metadataUnavailable ? (
              <InlineNotice
                tone="critical"
                title="Calculator disabled for this symbol"
                description={`Broker symbol metadata could not be resolved, so the manual ticket stays disabled until a supported symbol is chosen or metadata becomes available.${operatorError?.meta?.resolver_message ? ` Resolver detail: ${compactValue(operatorError.meta.resolver_message)}.` : ""}`}
              />
            ) : null}

            {accountSnapshotUnavailable || accountEquityUnavailable ? (
              <InlineNotice
                tone="warning"
                title="Sizing menunggu data akun valid"
                description={accountSnapshotUnavailable
                  ? `Risk mode % equity but the live account snapshot could not be read.${operatorError?.meta?.resolver_message ? ` Detail: ${compactValue(operatorError.meta.resolver_message)}.` : ""}`
                  : `Risk mode % equity but live_state belum memberi equity_current > 0.${Array.isArray(operatorError?.meta?.snapshot_keys) && operatorError?.meta?.snapshot_keys.length ? ` Snapshot keys: ${(operatorError.meta.snapshot_keys as Array<unknown>).map((value) => compactValue(value)).join(", ")}.` : ""}`}
              />
            ) : null}

            <section className="stats-grid">
              <StatCard label="Lot size" value={formatPlainNumber(Number(derived.lot_size), 4)} hint="Rounded to broker lot step" tone={derived.lot_size == null ? "warning" : "success"} />
              <StatCard label="Risk at SL" value={formatCurrency(typeof derived.estimated_loss_at_stop === "number" ? derived.estimated_loss_at_stop : typeof derived.risk_amount === "number" ? derived.risk_amount : null)} hint={form.riskMode === "money" ? "Requested cash risk" : "Resolved from equity percentage"} tone="warning" />
              <StatCard label="TP payoff" value={formatCurrency(typeof derived.estimated_profit_at_take_profit === "number" ? derived.estimated_profit_at_take_profit : null)} hint="Expected profit at normalized TP" tone="success" />
              <StatCard label="R:R" value={typeof derived.risk_reward_ratio === "number" ? `${formatPlainNumber(derived.risk_reward_ratio, 2)}R` : "—"} hint="Reward divided by risk at rounded prices" tone="info" />
              <StatCard label="Notional" value={formatCurrency(typeof derived.notional_estimate === "number" ? derived.notional_estimate : null)} hint="Entry price × contract size × lot size" tone="neutral" />
              <StatCard label="Margin est." value={formatCurrency(typeof derived.margin_estimate === "number" ? derived.margin_estimate : null)} hint="Shown only when leverage is provided" tone="neutral" />
              <StatCard label="Pip size" value={formatPlainNumber(Number(derived.pip_size), 5)} hint="Resolved from symbol class + broker digits" tone="info" />
              <StatCard label="Tick size" value={formatPlainNumber(Number(symbolSpec.tick_size), 5)} hint={`Class ${compactValue(symbolSpec.instrument_class)}`} tone="info" />
            </section>

            {warningNotices.length ? (
              <div className="manual-ticket-warning-list">
                {warningNotices.map((notice) => (
                  <InlineNotice key={notice.warning} tone="warning" title={notice.title} description={notice.description} />
                ))}
              </div>
            ) : null}
          </Section>

          <Section title="Normalized price geometry" description="The backend converts every distance-based input into explicit prices so the future preview/submit flow can stay audit-friendly.">
            <KeyValueGrid
              data={{
                symbol: derived.symbol,
                execution_symbol: derived.execution_symbol,
                side: derived.side,
                entry_price: derived.entry_price,
                stop_loss_price: derived.stop_loss_price,
                take_profit_price: derived.take_profit_price,
                stop_loss_distance_price: derived.stop_loss_distance_price,
                take_profit_distance_price: derived.take_profit_distance_price,
                risk_amount: derived.risk_amount,
                requested_risk_value: derived.requested_risk_value,
              }}
              emptyTitle="No normalized geometry yet"
              emptyDescription="The calculator will populate normalized entry, SL, TP, and resolved risk numbers once the ticket draft is valid."
            />
          </Section>

          <Section title="Preview and confirmation" description="Review the final manual ticket payload before any future live-submit endpoint is allowed to reuse it.">
            <section className="stats-grid">
              <StatCard label="Final entry" value={formatPlainNumber(Number(derived.entry_price), 5)} hint={form.orderType === "market" ? "Reference market quote" : "Pending limit entry"} tone="info" />
              <StatCard label="Final stop loss" value={formatPlainNumber(Number(derived.stop_loss_price), 5)} hint={compactValue(previewPayload.stop_loss_mode)} tone="warning" />
              <StatCard label="Final take profit" value={formatPlainNumber(Number(derived.take_profit_price), 5)} hint={form.takeProfitEnabled ? compactValue(previewPayload.take_profit_mode) : "TP disabled"} tone="success" />
              <StatCard label="Final lot size" value={formatPlainNumber(Number(derived.lot_size), 4)} hint="Rounded broker lot size" tone="success" />
              <StatCard label="Expected loss" value={formatCurrency(typeof derived.estimated_loss_at_stop === "number" ? derived.estimated_loss_at_stop : null)} hint="At normalized stop loss" tone="warning" />
              <StatCard label="Expected profit" value={formatCurrency(typeof derived.estimated_profit_at_take_profit === "number" ? derived.estimated_profit_at_take_profit : null)} hint="At normalized take profit" tone="success" />
            </section>

            <div className="manual-ticket-chip-row">
              <StatusBadge label={`order_origin=${compactValue(previewPayload.order_origin)}`} tone="warning" />
              <StatusBadge label={`execution_origin=${compactValue(previewPayload.execution_origin)}`} tone="info" />
              <StatusBadge label={`is_manual=${compactValue(previewPayload.is_manual)}`} tone="success" />
              <StatusBadge label={`magic_number=${compactValue(previewPayload.magic_number)}`} tone="neutral" />
              <StatusBadge label={`exclude_from_strategy_eval=${compactValue(previewPayload.exclude_from_strategy_eval)}`} tone="critical" />
            </div>
            <KeyValueGrid
              data={{
                comment_tag: previewPayload.comment_tag,
                order_type: previewPayload.order_type,
                symbol: previewPayload.symbol,
                lot_size: previewPayload.lot_size,
                stop_loss_mode: previewPayload.stop_loss_mode,
                take_profit_mode: previewPayload.take_profit_mode,
                risk_mode: previewPayload.risk_mode,
                risk_value: previewPayload.risk_value,
                magic_number: previewPayload.magic_number,
              }}
              emptyTitle="No preview payload yet"
              emptyDescription="Once the calculator succeeds, the preview payload block shows the exact manual-only markers that must survive into submit and audit layers."
            />

            <InlineNotice
              tone={previewConfirmed ? "success" : "warning"}
              title={previewConfirmed ? "Preview confirmed" : "Explicit confirmation required"}
              description={previewConfirmed
                ? "This draft is now confirmed as an operator-initiated manual_user trade preview and can be recorded into audit before a later live-submit slice is built."
                : "Confirm that this ticket is a manual_user trade, excluded from autonomous strategy attribution, and still requires a separate live-submit confirmation step."}
            />

            <label className="manual-ticket-confirmation">
              <input
                type="checkbox"
                checked={previewConfirmed}
                onChange={(event) => setPreviewConfirmed(event.target.checked)}
                disabled={!payload || !calc || status !== "success"}
              />
              <span>
                Saya konfirmasi draft ini adalah manual trade operator, tetap bertag <code>manual_user</code>, dan belum boleh dikirim live tanpa gate konfirmasi submit terpisah.
              </span>
            </label>

            <div className="manual-ticket-inline-row manual-ticket-action-row">
              <Button onClick={() => void handleRecordPreviewIntent()} disabled={!payload || !calc || status !== "success" || !previewConfirmed || previewAuditStatus === "loading"}>
                {previewAuditStatus === "loading" ? "Validating broker + recording preview..." : "Validate with broker and record preview"}
              </Button>
              {previewAuditStatus === "success" ? <StatusBadge label="Broker validated, audit recorded" tone="success" /> : null}
            </div>
            {previewAuditStatus === "success" ? (
              <KeyValueGrid
                data={{
                  audit_recorded_at: previewAudit?.generated_at,
                  preview_fingerprint: previewAuditEvent.preview_fingerprint,
                  audit_stage: previewAuditEvent.audit_stage,
                  event: previewAuditEvent.event,
                  broker_validation_retcode: brokerValidation.retcode,
                  broker_validation_message: compactValue(brokerValidation.message),
                  broker_magic_number: brokerValidation.request && typeof brokerValidation.request === "object" ? compactValue((brokerValidation.request as Record<string, unknown>).magic) : "—",
                }}
                emptyTitle=""
                emptyDescription=""
              />
            ) : null}
            {previewAuditStatus === "error" ? (
              <InlineNotice
                tone={previewOperatorError?.code === "broker_validation_failed" ? "critical" : "warning"}
                title={previewOperatorError?.code === "broker_validation_failed" ? "Broker menolak draft order" : "Preview audit gagal direkam"}
                description={previewOperatorError?.code === "broker_validation_failed"
                  ? `${previewOperatorError.message}${previewOperatorError.meta?.message ? ` Detail broker: ${compactValue(previewOperatorError.meta.message)}.` : ""}`
                  : previewOperatorError?.message ?? (previewAuditError instanceof Error ? previewAuditError.message : "Preview audit request gagal.")}
              />
            ) : null}
          </Section>

          <Section title="Live submit gate" description="Submit live tetap terpisah dari preview, wajib pakai gate konfirmasi kedua, dan selalu membawa marker manual_user yang sama.">
            <InlineNotice
              tone={previewAuditStatus === "success" ? "info" : "warning"}
              title={previewAuditStatus === "success" ? "Preview audit siap dipromosikan ke submit" : "Submit live menunggu preview tervalidasi"}
              description={previewAuditStatus === "success"
                ? "Gunakan client submission id ini untuk satu percobaan submit. Retry dengan id yang sama akan tetap idempoten selama payload preview tidak berubah."
                : "Selesaikan broker validation + preview audit dulu. Submit tidak dibuka langsung dari hasil kalkulator agar jejak audit tetap eksplisit."}
            />

            <FilterToolbar className="manual-ticket-form-grid">
              <FilterField label="Client submission id">
                <input
                  className="filter-input"
                  value={clientSubmissionId}
                  onChange={(event) => setClientSubmissionId(event.target.value)}
                  disabled={previewAuditStatus !== "success" || submitStatus === "loading"}
                  placeholder="manual-..."
                />
              </FilterField>
            </FilterToolbar>

            <label className="manual-ticket-confirmation">
              <input
                type="checkbox"
                checked={submitConfirmed}
                onChange={(event) => setSubmitConfirmed(event.target.checked)}
                disabled={previewAuditStatus !== "success" || submitStatus === "loading"}
              />
              <span>
                Saya konfirmasi submit live ini memang order manual operator, tetap dikecualikan dari statistik strategi/research, dan saya siap menerima order market/limit sesuai payload broker tervalidasi di atas.
              </span>
            </label>

            <div className="manual-ticket-inline-row manual-ticket-action-row">
              <Button onClick={() => void handleSubmitManualTrade()} disabled={!payload || !calc || !previewAudit || previewAuditStatus !== "success" || !previewConfirmed || !submitConfirmed || submitStatus === "loading" || !clientSubmissionId.trim()}>
                {submitStatus === "loading" ? "Submitting live manual order..." : "Submit live manual order"}
              </Button>
              {submitStatus === "success" ? <StatusBadge label={submitResponse?.duplicate_submission ? "Duplicate retry resolved idempotently" : "Manual order submitted"} tone="success" /> : null}
            </div>

            {submitStatus === "success" ? (
              <>
                <section className="stats-grid">
                  <StatCard label="Submit status" value={compactValue(submitResponse?.submit_status)} hint={submitResponse?.duplicate_submission ? "Existing execution result reused" : "Fresh broker send result"} tone="success" />
                  <StatCard label="Order ticket" value={compactValue(submitBrokerResponse.order_ticket)} hint="Broker order identifier" tone="info" />
                  <StatCard label="Deal ticket" value={compactValue(submitBrokerResponse.deal_ticket)} hint="Present when broker filled immediately" tone="info" />
                  <StatCard label="Position id" value={compactValue(submitBrokerResponse.position_id)} hint="MT5 position/order linkage" tone="neutral" />
                </section>
                <KeyValueGrid
                  data={{
                    submit_recorded_at: submitResponse?.generated_at,
                    client_submission_id: submitResponse?.client_submission_id,
                    preview_fingerprint: submitResponse?.preview_fingerprint,
                    broker_retcode: submitBrokerResponse.retcode,
                    broker_message: compactValue(submitBrokerResponse.message),
                    broker_comment: submitBrokerResponse.raw_result && typeof submitBrokerResponse.raw_result === "object" ? compactValue((submitBrokerResponse.raw_result as Record<string, unknown>).comment) : "—",
                    audit_stage: submitAuditAfter.audit_stage,
                    audit_event: submitAuditAfter.event,
                    order_origin: submitAuditAfter.order_origin,
                    execution_origin: submitAuditAfter.execution_origin,
                  }}
                  emptyTitle=""
                  emptyDescription=""
                />
              </>
            ) : null}

            {submitStatus === "error" ? (
              <InlineNotice
                tone={submitOperatorError?.code?.includes("manual_trade") || submitOperatorError?.code === "broker_validation_failed" ? "critical" : "warning"}
                title={submitOperatorError?.code === "manual_submit_confirmation_required" ? "Konfirmasi submit masih wajib" : "Submit live gagal"}
                description={submitOperatorError?.message ?? (submitError instanceof Error ? submitError.message : "Submit request gagal.")}
              />
            ) : null}
          </Section>
        </div>
      </div>

      <Section title="What this slice completes" description="This UI pass closes the operator-facing preview-to-submit flow while preserving manual_user segregation and explicit confirmation gates.">
        <section className="stats-grid">
          <StatCard label="Symbol" value={symbolLabel || "—"} hint="Preset selector plus custom fallback" tone="info" />
          <StatCard label="Entry mode" value={form.orderType === "market" ? "Market reference" : "Pending limit"} hint={entryLabel} tone="neutral" />
          <StatCard label="Risk input" value={form.riskMode === "money" ? formatCurrency(parseOptionalNumber(form.riskValue) ?? null) : formatPercent(parseOptionalNumber(form.riskValue) ?? null)} hint="Money or % equity" tone="success" />
          <StatCard label="Submit gate" value="Preview audit + live confirm" hint="Live submit now stays explicit, idempotent, and audit-backed" tone="warning" />
        </section>
      </Section>
    </div>
  );
}
