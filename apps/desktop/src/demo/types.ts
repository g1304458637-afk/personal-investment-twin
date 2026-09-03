export type EvidenceStatus =
  | "complete"
  | "partial"
  | "insufficient_evidence"
  | "experimental";

export type DataTier = "synthetic" | "demo" | "authorized_beta" | "production";

export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

export interface DemoEvidenceProvenance {
  source_type: string;
  source_name: string;
  data_version: string;
  as_of: string | null;
  price_type: string | null;
  is_synthetic: boolean;
  source_id: string | null;
  instrument: string | null;
  benchmark_id: string | null;
  attributes: Record<string, JsonValue>;
}

export interface DemoEvidenceRecord {
  evidence_id: string;
  subject_id: string;
  metric_id: string;
  evidence_kind: string;
  method_id: string;
  method_version: string;
  observation_start: string | null;
  observation_end: string | null;
  as_of: string | null;
  value: string | number | boolean | null;
  numerator: number | null;
  denominator: number | string | null;
  observation_count: number | null;
  ci_lower: number | null;
  ci_upper: number | null;
  evidence_status: EvidenceStatus;
  evidence_reason: string | null;
  provenance: DemoEvidenceProvenance[];
  data_tier: DataTier;
  calculation_code_version: string;
  limitations: string[];
  attributes: Record<string, JsonValue>;
}

export interface PortfolioPoint {
  date: string;
  value: number;
  reference: number;
}

export interface PositionRow {
  symbol: string;
  name: string;
  marketValue: number;
  weight: number;
  positionReturn: number;
}

export interface AllocationRow {
  label: string;
  value: number;
  color: string;
}

export interface EvidenceMetric {
  id: string;
  label: string;
  eyebrow: string;
  primary: string;
  description: string;
  observationCount: number | null;
  status: EvidenceStatus;
  confidence: string | null;
  evidenceId: string;
  trend: number[];
  primaryValues?: Record<string, string | number>;
  descriptionValues?: Record<string, string | number>;
}

export interface PeriodSnapshot {
  id: "3m" | "12m" | "lifetime";
  label: string;
  observationWindow: string;
  episodeCount: number;
  evidenceCoverage: number;
  decisionNotes: string[];
  behaviorNotes: string[];
}
