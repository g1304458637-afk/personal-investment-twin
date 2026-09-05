import type { MarketPreview, TradePreview } from "./runtimeService";

export type ImportPreview = TradePreview | MarketPreview;

/** All rows, including those beyond the first viewport, require a decision. */
export function canConfirmImport(preview: ImportPreview, choices: Record<string, "keep" | "skip">): boolean {
  return Boolean(preview.preview_fingerprint) && preview.rows.every((row) =>
    row.status !== "possible_duplicate" || ("row_ref" in row && ["keep", "skip"].includes(choices[row.row_ref]))) &&
    (!("file_sha256" in preview) || (!preview.summary.conflicts && !preview.summary.invalid_rows));
}

/** Transport only: commit the exact configuration used to produce this preview. */
export function confirmedImportRequest(configuration: Record<string, unknown>, preview: ImportPreview,
  choices: Record<string, "keep" | "skip">): Record<string, unknown> {
  if (!canConfirmImport(preview, choices)) throw new Error("import_confirmation_incomplete");
  return { ...configuration, expected_file_sha256: "batch" in preview ? preview.batch.file_sha256 : preview.file_sha256,
    expected_preview_fingerprint: preview.preview_fingerprint, duplicate_choices: { ...choices } };
}
