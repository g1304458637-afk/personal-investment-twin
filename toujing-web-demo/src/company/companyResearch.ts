// Type-only contracts from the current R6 working tree; no legacy HTTP adapter.
export interface CompanyValue { period:string; value:string|null; display_value?:string; unit?:string; knowledge_status:string; validation_status:string; evidence_ids:string[] }
export interface CompanyMetric { key:string; name:string; unit:string; kind:string; values:CompanyValue[] }
export interface CompanySource { id:string; title:string; locator:string; note?:string }
export interface CompanyGraphNode { id:string; label:string; kind:string; detail?:string; note?:string; groupIds?:string[]; evidenceIds?:string[]; knowledge?:string; period?:{label:string}; value?:string|null; unit?:string }
export interface CompanyAnalysis { version_id:string; fingerprint:string; facts:CompanyMetric[]; ratios:CompanyMetric[]; quality: {numeric_observations:number; historical_validation_status:string; observation_validation_counts:Record<string,number>}; yoy?:Record<string,unknown> }
export interface CompanyRelation { id:string;source:string;target:string;kind:string;label?:string;evidenceIds?:string[] }
export interface CompanyGraph { projectionKind?:string;relations?:Record<string,CompanyRelation>; modelVersion:{id:string;twinId:string}; nodes:Record<string,CompanyGraphNode>; sources:Record<string,CompanySource>; coverage:{entities:number;metrics:number}; fingerprint?:string }
export interface CompanyModel { build_id:string; analysis:CompanyAnalysis; graph:CompanyGraph }
export interface ResearchCompany extends CompanyModel { key:string; buildId:string; name:string; ticker:string }
