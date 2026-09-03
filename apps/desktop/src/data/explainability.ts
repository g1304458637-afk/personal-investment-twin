export const TRACE_KINDS = [
  "formula_components",
  "rule_observations",
  "comparison",
  "before_after",
  "statistical_summary",
  "source_fact",
] as const;

export type TraceKind = (typeof TRACE_KINDS)[number];
export type TraceScalar = string | number | boolean | null;

export interface ExplainabilityBoundary {
  allowedClaims: string[];
  prohibitedClaims: string[];
}

export interface ExplainabilityConcept {
  conceptId: string;
  metricId: string | null;
  methodId: string;
  methodVersion: string;
  unit: string;
  directionality: string;
  formulaDisplay: string;
  titleKey: string;
  shortDefinitionKey: string;
  detailedDefinitionKey: string;
  traceKind: TraceKind;
  boundary: ExplainabilityBoundary;
  limitations: string[];
}

export interface ExplainabilityInput {
  id: string;
  semanticName: string;
  labelKey: string;
  value: TraceScalar;
  unit: string;
  timestamp: string | null;
  sourceType: string;
  sourceRef: string;
  role: string;
  availabilityStatus: "available" | "unavailable";
  attributes: Record<string, unknown>;
}

export interface ExplainabilityOperation {
  id: string;
  kind: string;
  formulaDisplay: string;
  inputRefs: string[];
  result: TraceScalar;
  unit: string;
  attributes: Record<string, unknown>;
}

export interface ExplainabilityTrace {
  traceId: string;
  evidenceId: string | null;
  subjectRef: string;
  conceptId: string;
  methodId: string;
  methodVersion: string;
  traceKind: TraceKind;
  asOf: string | null;
  status: "complete" | "partial" | "insufficient" | "rejected";
  result: TraceScalar;
  unit: string;
  formulaKind: string;
  formulaDisplay: string;
  inputs: ExplainabilityInput[];
  operations: ExplainabilityOperation[];
  observationWindow: {
    start: string | null;
    end: string | null;
    policySessions: number | null;
  } | null;
  sourceRefs: string[];
  provenance: ExplainabilityProvenance[];
  limitations: string[];
  calculationCodeVersion: string;
  reason: string | null;
  requiredCondition: string | null;
  availableObservation: Record<string, unknown>;
}

export interface ExplainabilityProvenance {
  sourceName: string;
  sourceType: string;
  dataVersion: string;
  instrument: string | null;
  priceType: string | null;
  isSynthetic: boolean | null;
  asOf: string | null;
  sourceId: string | null;
}

export interface ExplainabilityView {
  evidenceId: string | null;
  concept: ExplainabilityConcept;
  result: {
    value: TraceScalar;
    numerator: number | null;
    denominator: string | number | null;
    observationCount: number | null;
    ciLower: number | null;
    ciUpper: number | null;
    status: string;
    reason: string | null;
  } | null;
  trace: ExplainabilityTrace | null;
  provenance: ExplainabilityProvenance[];
  limitations: string[];
  boundary: ExplainabilityBoundary;
  unavailableReason: string | null;
}

export interface ExplainabilityCatalog {
  concepts: ExplainabilityConcept[];
  evidenceViews: ExplainabilityView[];
  pretrade: ExplainabilityView | null;
  invalidItems: string[];
}

type Raw = Record<string, unknown>;

function object(value: unknown, field: string): Raw {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${field} must be an object.`);
  }
  return value as Raw;
}

function string(value: unknown, field: string): string {
  if (typeof value !== "string" || value.length === 0) throw new Error(`${field} must be text.`);
  return value;
}

function optionalString(value: unknown, field: string): string | null {
  return value === null || value === undefined ? null : string(value, field);
}

function number(value: unknown, field: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) throw new Error(`${field} must be finite.`);
  return value;
}

function optionalNumber(value: unknown, field: string): number | null {
  return value === null || value === undefined ? null : number(value, field);
}

function scalar(value: unknown, field: string): TraceScalar {
  if (value === null || typeof value === "string" || typeof value === "boolean") return value;
  if (typeof value === "number" && Number.isFinite(value)) return value;
  throw new Error(`${field} must be a JSON scalar.`);
}

function strings(value: unknown, field: string): string[] {
  if (!Array.isArray(value)) throw new Error(`${field} must be a list.`);
  return value.map((item, index) => string(item, `${field}[${index}]`));
}

function traceKind(value: unknown): TraceKind {
  const result = string(value, "trace_kind");
  if (!(TRACE_KINDS as readonly string[]).includes(result)) throw new Error("Unsupported trace kind.");
  return result as TraceKind;
}

function boundary(value: unknown): ExplainabilityBoundary {
  const raw = object(value, "interpretation_boundary");
  return {
    allowedClaims: strings(raw.allowed_claims, "allowed_claims"),
    prohibitedClaims: strings(raw.prohibited_claims, "prohibited_claims"),
  };
}

function concept(value: unknown): ExplainabilityConcept {
  const raw = object(value, "concept");
  return {
    conceptId: string(raw.concept_id, "concept_id"),
    metricId: optionalString(raw.metric_id, "metric_id"),
    methodId: string(raw.method_id, "method_id"),
    methodVersion: string(raw.method_version, "method_version"),
    unit: string(raw.unit, "unit"),
    directionality: string(raw.directionality, "directionality"),
    formulaDisplay: string(raw.formula_display, "formula_display"),
    titleKey: string(raw.title_key, "title_key"),
    shortDefinitionKey: string(raw.short_definition_key, "short_definition_key"),
    detailedDefinitionKey: string(raw.detailed_definition_key, "detailed_definition_key"),
    traceKind: traceKind(raw.calculation_trace_kind),
    boundary: boundary(raw.interpretation_boundary),
    limitations: strings(raw.limitations, "concept.limitations"),
  };
}

function provenance(value: unknown): ExplainabilityProvenance[] {
  if (!Array.isArray(value)) throw new Error("provenance must be a list.");
  return value.map((item, index) => {
    const raw = object(item, `provenance[${index}]`);
    return {
      sourceName: string(raw.source_name, "source_name"),
      sourceType: string(raw.source_type, "source_type"),
      dataVersion: string(raw.data_version, "data_version"),
      instrument: optionalString(raw.instrument, "instrument"),
      priceType: optionalString(raw.price_type, "price_type"),
      isSynthetic: raw.is_synthetic === null || raw.is_synthetic === undefined
        ? null
        : typeof raw.is_synthetic === "boolean"
          ? raw.is_synthetic
          : (() => { throw new Error("is_synthetic must be boolean or null."); })(),
      asOf: optionalString(raw.as_of, "as_of"),
      sourceId: optionalString(raw.source_id, "source_id"),
    };
  });
}

function inputs(value: unknown): ExplainabilityInput[] {
  if (!Array.isArray(value)) throw new Error("inputs must be a list.");
  return value.map((item, index) => {
    const raw = object(item, `inputs[${index}]`);
    const availability = string(raw.availability_status, "availability_status");
    if (availability !== "available" && availability !== "unavailable") {
      throw new Error("Unsupported input availability status.");
    }
    return {
      id: string(raw.input_id, "input_id"),
      semanticName: string(raw.semantic_name, "semantic_name"),
      labelKey: string(raw.label_key, "label_key"),
      value: scalar(raw.value, "input.value"),
      unit: string(raw.unit, "input.unit"),
      timestamp: optionalString(raw.timestamp, "input.timestamp"),
      sourceType: string(raw.source_type, "input.source_type"),
      sourceRef: string(raw.source_ref, "input.source_ref"),
      role: string(raw.role, "input.role"),
      availabilityStatus: availability,
      attributes: object(raw.attributes ?? {}, "input.attributes"),
    };
  });
}

function operations(value: unknown): ExplainabilityOperation[] {
  if (!Array.isArray(value)) throw new Error("operations must be a list.");
  return value.map((item, index) => {
    const raw = object(item, `operations[${index}]`);
    return {
      id: string(raw.operation_id, "operation_id"),
      kind: string(raw.operation_kind, "operation_kind"),
      formulaDisplay: string(raw.formula_display, "operation.formula_display"),
      inputRefs: strings(raw.input_refs, "operation.input_refs"),
      result: scalar(raw.result, "operation.result"),
      unit: string(raw.unit, "operation.unit"),
      attributes: object(raw.attributes ?? {}, "operation.attributes"),
    };
  });
}

function trace(value: unknown, expected: ExplainabilityConcept): ExplainabilityTrace {
  const raw = object(value, "calculation_trace");
  const kind = traceKind(raw.trace_kind);
  const status = string(raw.calculation_status, "calculation_status");
  if (!["complete", "partial", "insufficient", "rejected"].includes(status)) {
    throw new Error("Unsupported calculation status.");
  }
  const result: ExplainabilityTrace = {
    traceId: string(raw.trace_id, "trace_id"),
    evidenceId: optionalString(raw.evidence_id, "trace.evidence_id"),
    subjectRef: string(raw.subject_ref, "subject_ref"),
    conceptId: string(raw.concept_id, "trace.concept_id"),
    methodId: string(raw.method_id, "trace.method_id"),
    methodVersion: string(raw.method_version, "trace.method_version"),
    traceKind: kind,
    asOf: optionalString(raw.as_of, "trace.as_of"),
    status: status as ExplainabilityTrace["status"],
    result: scalar(raw.result, "trace.result"),
    unit: string(raw.unit, "trace.unit"),
    formulaKind: string(raw.formula_kind, "formula_kind"),
    formulaDisplay: string(raw.formula_display, "trace.formula_display"),
    inputs: inputs(raw.inputs),
    operations: operations(raw.operations),
    observationWindow: null,
    sourceRefs: strings(raw.source_refs, "source_refs"),
    provenance: provenance(raw.provenance),
    limitations: strings(raw.limitations, "trace.limitations"),
    calculationCodeVersion: string(raw.calculation_code_version, "calculation_code_version"),
    reason: optionalString(raw.reason, "trace.reason"),
    requiredCondition: optionalString(raw.required_condition, "required_condition"),
    availableObservation: object(raw.available_observation ?? {}, "available_observation"),
  };
  if (raw.observation_window !== null && raw.observation_window !== undefined) {
    const window = object(raw.observation_window, "observation_window");
    result.observationWindow = {
      start: optionalString(window.start, "window.start"),
      end: optionalString(window.end, "window.end"),
      policySessions: optionalNumber(window.policy_sessions, "window.policy_sessions"),
    };
  }
  if (
    result.conceptId !== expected.conceptId
    || result.methodId !== expected.methodId
    || result.methodVersion !== expected.methodVersion
    || result.traceKind !== expected.traceKind
  ) throw new Error("Trace does not match its registered concept.");
  return result;
}

function result(value: unknown): ExplainabilityView["result"] {
  if (value === null || value === undefined) return null;
  const raw = object(value, "result");
  return {
    value: scalar(raw.value, "result.value"),
    numerator: optionalNumber(raw.numerator, "result.numerator"),
    denominator: raw.denominator === null || raw.denominator === undefined
      ? null
      : typeof raw.denominator === "string"
        ? raw.denominator
        : number(raw.denominator, "result.denominator"),
    observationCount: optionalNumber(raw.observation_count, "result.observation_count"),
    ciLower: optionalNumber(raw.ci_lower, "result.ci_lower"),
    ciUpper: optionalNumber(raw.ci_upper, "result.ci_upper"),
    status: string(raw.evidence_status, "evidence_status"),
    reason: optionalString(raw.evidence_reason, "evidence_reason"),
  };
}

function view(rawValue: unknown, knownConcept?: ExplainabilityConcept): ExplainabilityView {
  const raw = object(rawValue, "evidence_view");
  const parsedConcept = knownConcept ?? concept(raw.concept);
  const parsedTrace = raw.calculation_trace === null || raw.calculation_trace === undefined
    ? null
    : trace(raw.calculation_trace, parsedConcept);
  const conceptBoundary = raw.concept === null || raw.concept === undefined
    ? undefined
    : object(raw.concept, "concept").interpretation_boundary;
  const interpretationBoundary = raw.interpretation_boundary ?? conceptBoundary;
  const viewLimitations = strings(raw.limitations ?? [], "limitations");
  return {
    evidenceId: optionalString(raw.evidence_id, "evidence_id"),
    concept: parsedConcept,
    result: result(raw.result),
    trace: parsedTrace,
    provenance: provenance(raw.provenance ?? parsedTrace?.provenance ?? []),
    limitations: Array.from(new Set([
      ...viewLimitations,
      ...parsedConcept.limitations,
      ...(parsedTrace?.limitations ?? []),
    ])),
    boundary: boundary(interpretationBoundary),
    unavailableReason: parsedTrace ? null : "calculation_trace_unavailable",
  };
}

function unavailable(parsedConcept: ExplainabilityConcept, reason: string): ExplainabilityView {
  return {
    evidenceId: null,
    concept: parsedConcept,
    result: null,
    trace: null,
    provenance: [],
    limitations: parsedConcept.limitations,
    boundary: parsedConcept.boundary,
    unavailableReason: reason,
  };
}

export function adaptExplainabilityPayload(value: unknown): ExplainabilityCatalog {
  const raw = object(value, "explainability");
  const invalidItems: string[] = [];
  const concepts = Array.isArray(raw.concepts)
    ? raw.concepts.flatMap((item, index) => {
        try { return [concept(item)]; }
        catch (error) { invalidItems.push(`concept[${index}]: ${String(error)}`); return []; }
      })
    : [];
  const byId = new Map(concepts.map((item) => [item.conceptId, item]));
  const evidenceViews = Array.isArray(raw.evidence_views)
    ? raw.evidence_views.flatMap((item, index) => {
        try {
          const itemObject = object(item, `evidence_views[${index}]`);
          const itemConcept = concept(itemObject.concept);
          const registered = byId.get(itemConcept.conceptId);
          if (registered && (
            registered.methodId !== itemConcept.methodId
            || registered.methodVersion !== itemConcept.methodVersion
            || registered.traceKind !== itemConcept.traceKind
          )) throw new Error("Evidence view concept does not match the registry.");
          return [view(itemObject, registered ?? itemConcept)];
        } catch (error) {
          invalidItems.push(`evidence_view[${index}]: ${String(error)}`);
          return [];
        }
      })
    : [];
  let pretrade: ExplainabilityView | null = null;
  if (raw.pretrade_trace !== null && raw.pretrade_trace !== undefined) {
    const pretradeConcept = byId.get("pretrade_concentration_impact");
    if (pretradeConcept) {
      try {
        const parsedTrace = trace(raw.pretrade_trace, pretradeConcept);
        pretrade = {
          ...unavailable(pretradeConcept, "calculation_trace_unavailable"),
          trace: parsedTrace,
          result: {
            value: parsedTrace.result,
            numerator: null,
            denominator: null,
            observationCount: null,
            ciLower: null,
            ciUpper: null,
            status: parsedTrace.status,
            reason: parsedTrace.reason,
          },
          provenance: parsedTrace.provenance,
          limitations: parsedTrace.limitations,
          unavailableReason: null,
        };
      } catch (error) {
        invalidItems.push(`pretrade_trace: ${String(error)}`);
        pretrade = unavailable(pretradeConcept, "malformed_calculation_trace");
      }
    }
  }
  return { concepts, evidenceViews, pretrade, invalidItems };
}

export function conceptOnlyView(
  catalog: ExplainabilityCatalog,
  conceptId: string,
): ExplainabilityView | null {
  const parsedConcept = catalog.concepts.find((item) => item.conceptId === conceptId);
  return parsedConcept ? unavailable(parsedConcept, "calculation_trace_unavailable") : null;
}
