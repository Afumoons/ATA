"use client";

import { useMemo, useState } from "react";
import { PageHeader } from "@/components/app-shell";
import {
  DataTable,
  EmptyState,
  ErrorState,
  FreshnessBadge,
  KeyValueGrid,
  LoadingState,
  Section,
  StatCard,
  StatusBadge,
  ToolbarButton,
} from "@/components/dashboard";
import { useQuery } from "@/hooks/use-query";
import { uiApi } from "@/lib/api";
import { compactValue, formatCurrency, formatDateTime, formatNumber, formatPercent } from "@/lib/format";
import {
  coerceRecord,
  getStrategyRelationshipState,
  pickFirstNumber,
  pickFirstString,
  toneFromMagnitude,
  toneFromSignedNumber,
} from "@/lib/ui-state";

const EMPTY_STRATEGY_ROWS: Awaited<ReturnType<typeof uiApi.strategies>> = [];

export default function PoolPage() {
  const [search, setSearch] = useState("");
  const [tierFilter, setTierFilter] = useState("all");
  const [selectedStrategy, setSelectedStrategy] = useState<string>("");

  const poolQuery = useQuery("pool-summary", uiApi.poolSummary, { refetchIntervalMs: 60_000 });
  const strategiesQuery = useQuery("strategies-summary", uiApi.strategies, { refetchIntervalMs: 90_000 });

  const { data, error, loading, hasData, refreshing, refresh } = poolQuery;
  const strategyRows = strategiesQuery.data ?? EMPTY_STRATEGY_ROWS;

  const filteredStrategies = useMemo(() => {
    return [...strategyRows]
      .sort((left, right) => {
        const manifestRankDelta = Number(Boolean(right.in_manifest)) - Number(Boolean(left.in_manifest));
        if (manifestRankDelta !== 0) return manifestRankDelta;
        return Number(right.score ?? -Infinity) - Number(left.score ?? -Infinity);
      })
      .filter((row) => {
        if (tierFilter !== "all" && String(row.tier ?? "unknown") !== tierFilter) return false;

        if (!search.trim()) return true;
        const haystack = [row.name, row.symbol, row.timeframe, row.status, row.family, row.motif, row.tier]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        return haystack.includes(search.trim().toLowerCase());
      });
  }, [search, strategyRows, tierFilter]);

  const resolvedSelectedStrategy = useMemo(() => {
    if (!filteredStrategies.length) return "";
    if (selectedStrategy && filteredStrategies.some((row) => row.name === selectedStrategy)) {
      return selectedStrategy;
    }
    return filteredStrategies[0].name;
  }, [filteredStrategies, selectedStrategy]);

  const detailQuery = useQuery(
    `strategy-detail:${resolvedSelectedStrategy}`,
    () => uiApi.strategyDetail(resolvedSelectedStrategy),
    { enabled: Boolean(resolvedSelectedStrategy) },
  );

  if (loading && !hasData) {
    return <LoadingState title="Loading pool overview" description="Collecting pool inventory, slot distribution, and strategy-layer relationship data." />;
  }

  if (!data) {
    return <ErrorState error={error} resourceLabel="pool summary" />;
  }

  const selectedDetail = detailQuery.data;
  const selectedManifest = coerceRecord(selectedDetail?.manifest_entry);
  const selectedIndex = coerceRecord(selectedDetail?.index_entry);
  const selectedPool = coerceRecord(selectedDetail?.pool_record);
  const selectedLiveStats = coerceRecord(selectedDetail?.live_stats);
  const selectedDerived = coerceRecord(selectedDetail?.derived);
  const relationship = getStrategyRelationshipState({
    manifest_entry: selectedDetail?.manifest_entry,
    index_entry: selectedDetail?.index_entry,
    pool_record: selectedDetail?.pool_record,
    live_stats: selectedDetail?.live_stats,
  });

  const livePnl = pickFirstNumber(selectedLiveStats.total_pnl, selectedLiveStats.realized_pnl);
  const liveTrades = pickFirstNumber(selectedLiveStats.num_trades, selectedLiveStats.total_trades);
  const liveLastUpdate = pickFirstString(selectedLiveStats.last_update);
  const liveVsResearchDelta = pickFirstNumber(selectedDerived.live_vs_research_delta);
  const ruleSource = Object.keys(selectedManifest).length ? selectedManifest : selectedPool;

  const tierOptions = Array.from(new Set(strategyRows.map((row) => String(row.tier ?? "unknown")))).sort();

  return (
    <div className="dashboard-stack">
      <PageHeader
        title="Pool overview"
        subtitle="Inventory depth, slot concentration, and cross-layer strategy drill-down so operators can see whether a strategy exists in the index, pool, manifest, and live stats at the same time."
        meta={`Snapshot ${formatDateTime(data.generated_at)}`}
        action={
          <div className="page-toolbar">
            <FreshnessBadge timestamp={data.generated_at} thresholds={{ warningMs: 15 * 60_000, criticalMs: 60 * 60_000 }} />
            <ToolbarButton
              label="Refresh now"
              onClick={() => {
                void Promise.all([refresh(), strategiesQuery.refresh(), detailQuery.refresh()]);
              }}
              busy={refreshing || strategiesQuery.refreshing || detailQuery.refreshing}
              tone="info"
            />
          </div>
        }
      />

      <section className="stats-grid">
        <StatCard label="Total strategies" value={formatNumber(data.total)} hint="Pool inventory count" tone="info" />
        <StatCard label="Distinct slots" value={formatNumber(data.by_slot.length)} hint="Symbol/timeframe combinations" tone="neutral" />
        <StatCard label="Top records" value={formatNumber(data.top_strategies.length)} hint="Returned by summary endpoint" tone="success" />
        <StatCard label="Status buckets" value={formatNumber(Object.keys(data.status_counts).length)} hint="Current pool status families" tone="warning" />
      </section>

      <Section title="Pool status counts" description="How current pool inventory is distributed across workflow states.">
        {Object.keys(data.status_counts ?? {}).length ? (
          <KeyValueGrid data={data.status_counts} />
        ) : (
          <EmptyState title="Pool artifact looks empty" description="No status buckets were returned. The pool state may be missing or empty." />
        )}
      </Section>

      <div className="detail-grid-2">
        <Section title="Family concentration" description="Which strategy families dominate the current pool.">
          <KeyValueGrid data={data.family_counts ?? {}} emptyTitle="No family mix" emptyDescription="Family concentration was not returned by the backend." />
        </Section>
        <Section title="Symbol concentration" description="How inventory is split across tradable symbols.">
          <KeyValueGrid data={data.symbol_counts ?? {}} emptyTitle="No symbol mix" emptyDescription="Symbol concentration was not returned by the backend." />
        </Section>
      </div>

      <Section title="Slot distribution" description="Volume concentration by symbol and timeframe.">
        <DataTable
          columns={["Symbol", "Timeframe", "Count"]}
          rows={data.by_slot.map((slot) => [slot.symbol, slot.timeframe, formatNumber(slot.count)])}
          emptyTitle="No slot distribution"
          emptyDescription="No symbol/timeframe distribution was returned for the pool snapshot."
        />
      </Section>

      <Section title="Strategy explorer" description="Searchable strategy list with quick selection into per-strategy relationship detail.">
        <div className="filter-toolbar panel">
          <label className="filter-field">
            <span>Search</span>
            <input
              className="filter-input"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="name, symbol, family, motif"
            />
          </label>
          <label className="filter-field">
            <span>Tier</span>
            <select className="filter-input" value={tierFilter} onChange={(event) => setTierFilter(event.target.value)}>
              <option value="all">All tiers</option>
              {tierOptions.map((tier) => (
                <option key={tier} value={tier}>
                  {tier}
                </option>
              ))}
            </select>
          </label>
          <div className="filter-summary">
            <span className="eyebrow">Visible</span>
            <strong>{formatNumber(filteredStrategies.length)}</strong>
          </div>
        </div>

        <DataTable
          columns={["Strategy", "Symbol", "Timeframe", "Tier", "Family", "Motif", "Status", "Manifest", "Score"]}
          rows={filteredStrategies.slice(0, 32).map((strategy) => [
            <button
              key={strategy.name}
              type="button"
              className={`table-link-button${resolvedSelectedStrategy === strategy.name ? " is-active" : ""}`}
              onClick={() => setSelectedStrategy(strategy.name)}
            >
              {strategy.name}
            </button>,
            compactValue(strategy.symbol),
            compactValue(strategy.timeframe),
            compactValue(strategy.tier),
            compactValue(strategy.family),
            compactValue(strategy.motif),
            compactValue(strategy.status),
            <StatusBadge
              key={`${strategy.name}-manifest`}
              label={strategy.in_manifest ? "Present" : "Absent"}
              tone={strategy.in_manifest ? "success" : "warning"}
            />,
            formatNumber(strategy.score),
          ])}
          emptyTitle="No strategies match the current filters"
          emptyDescription="Adjust the search text or tier filter to widen the visible strategy set."
        />
      </Section>

      <Section
        title="Strategy detail"
        description="Cross-layer view showing whether the selected strategy exists in the manifest, index, pool record, and live stats at the same time."
        action={resolvedSelectedStrategy ? <StatusBadge label={resolvedSelectedStrategy} tone="info" /> : null}
      >
        {!resolvedSelectedStrategy ? (
          <EmptyState title="No strategy selected" description="Choose a strategy from the explorer table above to inspect its layer relationships." />
        ) : detailQuery.loading && !selectedDetail ? (
          <LoadingState title="Loading strategy detail" description="Pulling manifest, index, pool, and live-stat context for the selected strategy." />
        ) : detailQuery.error && !selectedDetail ? (
          <ErrorState error={detailQuery.error} resourceLabel={`strategy detail for ${resolvedSelectedStrategy}`} />
        ) : !selectedDetail ? (
          <EmptyState title="No strategy detail returned" description="The selected strategy could not be resolved into any layer detail payload." />
        ) : (
          <div className="dashboard-stack">
            <div className="badge-row">
              {relationship.relationshipBadges.map((badge) => (
                <StatusBadge key={badge.label} label={badge.label} tone={badge.tone} />
              ))}
            </div>

            <section className="stats-grid">
              <StatCard
                label="Status"
                value={compactValue(pickFirstString(selectedManifest.status, selectedIndex.status, selectedPool.status))}
                hint={compactValue(pickFirstString(selectedIndex.tier, selectedPool.tier, selectedManifest.tier))}
                tone={relationship.inManifest ? "success" : "warning"}
              />
              <StatCard
                label="Score"
                value={formatNumber(pickFirstNumber(selectedManifest.score, selectedIndex.score, selectedPool.score, selectedPool.pool_score))}
                hint={compactValue(pickFirstString(selectedManifest.symbol, selectedIndex.symbol, selectedPool.symbol))}
                tone="info"
              />
              <StatCard
                label="Family / motif"
                value={compactValue(
                  `${pickFirstString(selectedManifest.family, selectedIndex.family, selectedPool.family) ?? "unknown"} / ${pickFirstString(selectedManifest.motif, selectedIndex.motif, selectedPool.motif) ?? "unknown"}`,
                )}
                hint={compactValue(pickFirstString(selectedManifest.timeframe, selectedIndex.timeframe, selectedPool.timeframe))}
                tone="neutral"
              />
              <StatCard
                label="Live stats"
                value={formatNumber(liveTrades)}
                hint={liveLastUpdate ? `Last update ${formatDateTime(liveLastUpdate)}` : "No live-stat timestamp"}
                tone={toneFromSignedNumber(livePnl)}
              />
            </section>

            <section className="stats-grid">
              <StatCard
                label="Best / worst regime"
                value={compactValue(`${pickFirstString(selectedDerived.best_regime) ?? "unknown"} / ${pickFirstString(selectedDerived.worst_regime) ?? "unknown"}`)}
                hint="Research explain meta"
                tone="info"
              />
              <StatCard
                label="Best / worst session"
                value={compactValue(`${pickFirstString(selectedDerived.best_session) ?? "unknown"} / ${pickFirstString(selectedDerived.worst_session) ?? "unknown"}`)}
                hint="Session edge profile"
                tone="neutral"
              />
              <StatCard
                label="Routing / specialist"
                value={compactValue(`${formatNumber(pickFirstNumber(selectedDerived.routing_confidence))} / ${formatNumber(pickFirstNumber(selectedDerived.specialist_score))}`)}
                hint="Routing confidence / specialist score"
                tone="success"
              />
              <StatCard
                label="Live vs research delta"
                value={formatNumber(liveVsResearchDelta)}
                hint="live_total_pnl - research_return_pct"
                tone={toneFromMagnitude(liveVsResearchDelta, 50, 200)}
              />
            </section>

            <Section title="Key rules summary" description="Entry and exit logic surfaced from the strongest available strategy source.">
              <div className="rule-grid panel">
                <div className="rule-card">
                  <span className="kv-key">Long entry</span>
                  <strong>{compactValue(ruleSource.long_entry_rule)}</strong>
                </div>
                <div className="rule-card">
                  <span className="kv-key">Short entry</span>
                  <strong>{compactValue(ruleSource.short_entry_rule)}</strong>
                </div>
                <div className="rule-card">
                  <span className="kv-key">Exit rule</span>
                  <strong>{compactValue(ruleSource.exit_rule)}</strong>
                </div>
                <div className="rule-card">
                  <span className="kv-key">Risk framing</span>
                  <strong>
                    SL {compactValue(ruleSource.sl_atr_mult ?? ruleSource.stop_loss_pips)} / TP {compactValue(ruleSource.tp_atr_mult ?? ruleSource.take_profit_pips)}
                  </strong>
                </div>
              </div>
            </Section>

            <div className="detail-grid-2">
              <Section title="Regime map" description="Where the strategy actually makes or loses money across detected market regimes.">
                <KeyValueGrid data={coerceRecord(selectedDerived.regime_pnl)} emptyTitle="No regime map" emptyDescription="Research explain did not return regime-level PnL details for this strategy." />
              </Section>
              <Section title="Session map" description="Which sessions contribute most to edge or drag.">
                <KeyValueGrid data={coerceRecord(selectedDerived.session_pnl)} emptyTitle="No session map" emptyDescription="Research explain did not return session-level PnL details for this strategy." />
              </Section>
            </div>

            <Section title="Live stats summary" description="Compact live trading statistics for the selected strategy, when available.">
              <section className="stats-grid">
                <StatCard label="Live trades" value={formatNumber(liveTrades)} hint="num_trades from live stats" tone="info" />
                <StatCard label="Live PnL" value={formatCurrency(livePnl)} hint="total_pnl from live stats" tone={toneFromSignedNumber(livePnl)} />
                <StatCard label="Manifest rank" value={formatNumber(pickFirstNumber(selectedManifest.manifest_rank, selectedIndex.last_manifest_rank))} hint="Last known manifest placement" tone="neutral" />
                <StatCard label="Research return" value={formatPercent(pickFirstNumber(selectedDerived.research_return_pct))} hint="Backtest return pct" tone="success" />
                <StatCard label="Payload health" value={relationship.inManifest || relationship.inPool ? "Shaped" : "Thin"} hint="Whether a strategy payload is available in surfaced layers" tone={relationship.inManifest || relationship.inPool ? "success" : "warning"} />
              </section>
            </Section>

            <div className="detail-grid-2">
              <Section title="Manifest layer" description="Live manifest-facing record for the selected strategy.">
                <KeyValueGrid data={selectedManifest} emptyTitle="Manifest record absent" emptyDescription="This strategy is not currently present in the manifest layer." />
              </Section>
              <Section title="Index layer" description="Strategy index representation used for broader inventory visibility.">
                <KeyValueGrid data={selectedIndex} emptyTitle="Index record absent" emptyDescription="This strategy is not present in the strategy index payload." />
              </Section>
              <Section title="Pool layer" description="Pool record for the selected strategy.">
                <KeyValueGrid data={selectedPool} emptyTitle="Pool record absent" emptyDescription="This strategy is not currently recoverable from the pool record set." />
              </Section>
              <Section title="Live-stat layer" description="Runtime performance counters for the selected strategy.">
                <KeyValueGrid data={selectedLiveStats} emptyTitle="Live stats absent" emptyDescription="The runtime stats file currently has no entry for this strategy." />
              </Section>
            </div>
          </div>
        )}
      </Section>

      <Section title="Top strategy records" description="Highest-ranked strategies from the pool summary endpoint.">
        <DataTable
          columns={["Name", "Symbol", "Timeframe", "Status", "Score"]}
          rows={data.top_strategies.map((strategy) => [
            strategy.name,
            strategy.symbol,
            strategy.timeframe,
            strategy.status,
            formatNumber(strategy.score),
          ])}
          emptyTitle="No top strategy rows"
          emptyDescription="The pool summary returned no top-ranked strategies for this snapshot."
        />
      </Section>
    </div>
  );
}
