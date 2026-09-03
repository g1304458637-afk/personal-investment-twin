export type PretradeSimulationStatus = "complete" | "rejected" | "insufficient_evidence";

interface BackendProposedTrade {
  subject_id: string;
  proposed_time: string;
  symbol: string;
  side: string;
  quantity: number;
  execution_price: number;
  fees: number;
}

interface BackendPortfolioImpactState {
  cash: number;
  portfolio_value: number;
  symbol_quantity: number;
  symbol_weight: number;
  hhi: number;
  active_assets: number;
}

interface BackendTradeImpactDelta {
  cash: number;
  symbol_weight: number;
  hhi: number;
}

interface BackendSelfHhiContext {
  historical_hhi_median: number;
  current_hhi: number;
  proposed_hhi: number;
  historical_observation_count: number;
  history_method_id: string;
}

interface BackendPeerHhiContext {
  cohort_id: string;
  cohort_n: number;
  metric_n: number;
  cohort_hhi_median: number;
  current_percentile: number;
  proposed_percentile: number;
  percentile_method: string;
}

export interface BackendPretradeImpact {
  proposed_trade: BackendProposedTrade;
  before: BackendPortfolioImpactState | null;
  after: BackendPortfolioImpactState | null;
  delta: BackendTradeImpactDelta | null;
  self_context: BackendSelfHhiContext | null;
  peer_context: BackendPeerHhiContext | null;
  simulation_status: PretradeSimulationStatus;
  simulation_reason: string | null;
  data_tier: "synthetic";
  limitations: string[];
}

export interface PretradeImpactStateView {
  cash: number;
  portfolioValue: number;
  symbolQuantity: number;
  symbolWeight: number;
  hhi: number;
  activeAssets: number;
}

export interface PretradeDemoView {
  subjectId: string;
  proposedTime: string;
  symbol: string;
  side: "BUY" | "SELL";
  quantity: number;
  executionPrice: number;
  fees: number;
  before: PretradeImpactStateView | null;
  after: PretradeImpactStateView | null;
  delta: { cash: number; symbolWeight: number; hhi: number } | null;
  selfContext: {
    historicalHhiMedian: number;
    currentHhi: number;
    proposedHhi: number;
    historicalObservationCount: number;
    historyMethodId: string;
  } | null;
  peerContext: {
    cohortId: string;
    cohortN: number;
    metricN: number;
    cohortHhiMedian: number;
    currentPercentile: number;
    proposedPercentile: number;
    percentileMethod: string;
  } | null;
  status: PretradeSimulationStatus;
  reason: string | null;
  limitations: string[];
}

function finite(value: number, name: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`Pre-trade ${name} must be finite.`);
  }
  return value;
}

function state(value: BackendPortfolioImpactState | null): PretradeImpactStateView | null {
  if (value === null) return null;
  return {
    cash: finite(value.cash, "cash"),
    portfolioValue: finite(value.portfolio_value, "portfolio value"),
    symbolQuantity: finite(value.symbol_quantity, "symbol quantity"),
    symbolWeight: finite(value.symbol_weight, "symbol weight"),
    hhi: finite(value.hhi, "HHI"),
    activeAssets: finite(value.active_assets, "active assets"),
  };
}

export function adaptPretradeImpact(value: BackendPretradeImpact): PretradeDemoView {
  if (value.data_tier !== "synthetic") {
    throw new Error("Desktop pre-trade demo must remain explicitly synthetic.");
  }
  if (value.proposed_trade.side !== "BUY" && value.proposed_trade.side !== "SELL") {
    throw new Error("Desktop pre-trade demo side must be BUY or SELL.");
  }
  const before = state(value.before);
  const after = state(value.after);
  if (
    value.simulation_status === "complete"
    && (!before || !after || !value.delta || !value.self_context || !value.peer_context)
  ) {
    throw new Error("Complete pre-trade demo is missing deterministic context.");
  }
  if (
    value.peer_context
    && value.peer_context.percentile_method !== "scipy_percentileofscore_rank_v1"
  ) {
    throw new Error("Pre-trade peer context must use the registered rank percentile method.");
  }
  return {
    subjectId: value.proposed_trade.subject_id,
    proposedTime: value.proposed_trade.proposed_time,
    symbol: value.proposed_trade.symbol,
    side: value.proposed_trade.side,
    quantity: finite(value.proposed_trade.quantity, "quantity"),
    executionPrice: finite(value.proposed_trade.execution_price, "execution price"),
    fees: finite(value.proposed_trade.fees, "fees"),
    before,
    after,
    delta: value.delta
      ? {
          cash: finite(value.delta.cash, "cash delta"),
          symbolWeight: finite(value.delta.symbol_weight, "symbol weight delta"),
          hhi: finite(value.delta.hhi, "HHI delta"),
        }
      : null,
    selfContext: value.self_context
      ? {
          historicalHhiMedian: finite(value.self_context.historical_hhi_median, "historical HHI median"),
          currentHhi: finite(value.self_context.current_hhi, "current HHI context"),
          proposedHhi: finite(value.self_context.proposed_hhi, "proposed HHI context"),
          historicalObservationCount: finite(value.self_context.historical_observation_count, "HHI history count"),
          historyMethodId: value.self_context.history_method_id,
        }
      : null,
    peerContext: value.peer_context
      ? {
          cohortId: value.peer_context.cohort_id,
          cohortN: finite(value.peer_context.cohort_n, "cohort N"),
          metricN: finite(value.peer_context.metric_n, "metric N"),
          cohortHhiMedian: finite(value.peer_context.cohort_hhi_median, "cohort HHI median"),
          currentPercentile: finite(value.peer_context.current_percentile, "current percentile"),
          proposedPercentile: finite(value.peer_context.proposed_percentile, "proposed percentile"),
          percentileMethod: value.peer_context.percentile_method,
        }
      : null,
    status: value.simulation_status,
    reason: value.simulation_reason,
    limitations: value.limitations,
  };
}
