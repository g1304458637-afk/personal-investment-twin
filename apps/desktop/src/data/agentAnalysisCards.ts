/** Deterministic presentation data, never parsed out of a model's prose. */
export type CardText = { zh: string; en: string };
export const analysisCardKinds = ["hypothetical_trade_impact", "owned_period_comparison", "owned_same_stock_comparison", "public_technical", "public_financials"] as const;
export type AnalysisCardKind = typeof analysisCardKinds[number];
export interface AgentAnalysisCard {
  id: string; kind: AnalysisCardKind; source_ref: string;
  title: CardText; subtitle: CardText; columns: CardText[];
  rows: { label: CardText; cells: CardText[]; explanation: CardText }[];
  notes: CardText[];
}
type Ledger = { read: readonly string[]; cited: readonly string[]; analysis: readonly string[]; public: readonly string[]; synthetic: boolean };
const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === "object" && !Array.isArray(value);
const local = (value: unknown, max = 1200): value is CardText => object(value)
  && [value.zh, value.en].every(text => typeof text === "string" && text.trim().length > 0 && text.length <= max);
const text = (value: unknown, max: number): value is string => typeof value === "string" && value.trim().length > 0 && value.length <= max;

/** Called only after the enclosing answer's scope, fingerprint and receipts pass.
 * Optional bad cards are omitted; older saved, verified text remains readable.
 */
export function validatedAnalysisCards(value: unknown, ledger: Ledger): AgentAnalysisCard[] {
  if (!Array.isArray(value) || value.length > 5) return [];
  const read = new Set(ledger.read), cited = new Set(ledger.cited);
  const ids = new Set<string>(), refs = new Set<string>();
  return value.filter((card): card is AgentAnalysisCard => {
    if (!object(card) || !text(card.id, 200) || ids.has(card.id) || !text(card.source_ref, 1000) || refs.has(card.source_ref)
      || !read.has(card.source_ref) || !cited.has(card.source_ref)
      || !analysisCardKinds.includes(card.kind as AnalysisCardKind)
      || !local(card.title, 160) || !local(card.subtitle, 1200)
      || !Array.isArray(card.columns) || card.columns.length < 2 || card.columns.length > 4 || !card.columns.every(c => local(c, 160))
      || !Array.isArray(card.rows) || !card.rows.length || card.rows.length > 16
      || !Array.isArray(card.notes) || card.notes.length > 5 || !card.notes.every(n => local(n))) return false;
    const category = String(card.kind).startsWith("public_") ? ledger.public : ledger.analysis;
    if (!category.includes(card.source_ref) || (card.kind === "hypothetical_trade_impact" && !ledger.synthetic)) return false;
    const width = card.columns.length;
    if (!card.rows.every(row => object(row) && local(row.label, 160) && local(row.explanation)
      && Array.isArray(row.cells) && row.cells.length === width && row.cells.every(cell => local(cell)))) return false;
    ids.add(card.id); refs.add(card.source_ref);
    return true;
  }).map(card => structuredClone(card));
}
