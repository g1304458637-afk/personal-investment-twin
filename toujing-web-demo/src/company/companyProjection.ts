import type {ResearchScope} from '../alignment';
import type {CompanyGraph, ResearchCompany} from './companyResearch';

export type OperatingEvidence = {
  id: string; text: string; document_id: string; document_title: string;
  page: number; start: number; end: number; source_version: string;
};
export type OperatingProjection = {
  status: string; reason?: string; instrument_id: string;
  document_id: string; document_title: string; source_year: number; source_sha256: string;
  graph?: CompanyGraph; evidence: Record<string, OperatingEvidence>;
  held_count: number; unknown_count: number; boundary: string; model_called_for_artifact: boolean;
};

// The display adapter is the one used by R6 CompanyOperatingGraph. It does not
// manufacture financial facts or turn source-grounded candidates into causes.
export function operatingCompany(value: OperatingProjection, instrument: string, name: string): ResearchCompany | null {
  if (value.instrument_id !== instrument) throw new Error('经营结构与当前公司不一致，请重新读取。');
  if (!value.graph) return null;
  if (value.graph.modelVersion.twinId !== instrument) throw new Error('经营模型的公司范围不一致。');
  return {
    key: instrument, buildId: value.graph.modelVersion.id, build_id: value.graph.modelVersion.id,
    name, ticker: instrument, graph: value.graph,
    analysis: {version_id: value.graph.modelVersion.id, fingerprint: value.graph.fingerprint ?? '',
      facts: [], ratios: [], quality: {numeric_observations: 0,
        historical_validation_status: 'not_financially_admitted', observation_validation_counts: {}}},
  };
}

export function operatingEvidenceScope(scope: ResearchScope, value: OperatingProjection, id?: string): ResearchScope {
  if (value.instrument_id !== scope.instrument_id) throw new Error('该节点属于另一家公司，请返回当前公司重新选择。');
  const next: ResearchScope = {...scope, origin: 'company', focus: 'public_price', kind: 'disclosure', selection_object: undefined};
  if (!id) return next;
  const row = value.evidence[id];
  if (!row || row.document_id !== value.document_id || row.source_version !== value.source_sha256 ||
      !Number.isInteger(row.page) || row.page < 1 || !Number.isInteger(row.start) || !Number.isInteger(row.end) || row.start < 0 || row.end <= row.start) {
    throw new Error('这条来源的位置或版本不完整，请重新核对图谱来源。');
  }
  return {...next, selection_object: {document_id: row.document_id, page: row.page, start: row.start, end: row.end}};
}
