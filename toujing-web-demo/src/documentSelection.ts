export type PassageLocation = {document_id: string; page: number; start: number; end: number};

// The company engine records Python Unicode code-point offsets. JS string
// offsets are UTF-16, so source excerpts containing astral characters must not
// shift when they are highlighted or sent back to the research session.
export function locatedPassage(text: string, documentId: string, page: number, location?: PassageLocation) {
  if (!location || location.document_id !== documentId || location.page !== page ||
      !Number.isInteger(location.start) || !Number.isInteger(location.end) || location.start < 0 || location.end <= location.start) return null;
  const points = Array.from(text);
  if (location.end > points.length) return null;
  return {before: points.slice(0, location.start).join(''), text: points.slice(location.start, location.end).join(''), after: points.slice(location.end).join('')};
}
