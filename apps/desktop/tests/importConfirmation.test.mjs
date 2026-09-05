import assert from "node:assert/strict";
import test from "node:test";
import { canConfirmImport, confirmedImportRequest } from "../src/data/importConfirmation.ts";

const preview = () => ({ preview_fingerprint: "confirmed-config", batch: { file_sha256: "confirmed-bytes" },
  summary: {}, rows: Array.from({ length: 15 }, (_, i) => ({ row_ref: `row:${i}`, status: "possible_duplicate" })) });

test("all 15 duplicate rows need explicit choices, including rows beyond viewport", () => {
  const value = preview();
  const choices = Object.fromEntries(value.rows.slice(0, 12).map((r) => [r.row_ref, "skip"]));
  assert.equal(canConfirmImport(value, choices), false);
  assert.throws(() => confirmedImportRequest({}, value, choices), /incomplete/);
  for (const r of value.rows.slice(12)) choices[r.row_ref] = "keep";
  assert.equal(canConfirmImport(value, choices), true);
  const config = { subject_id: "owner", initial_cash: 100, resolution_market: "XNAS" };
  const request = confirmedImportRequest(config, value, choices);
  assert.equal(request.expected_preview_fingerprint, "confirmed-config");
  assert.equal(request.expected_file_sha256, "confirmed-bytes");
  assert.equal(Object.keys(request.duplicate_choices).length, 15);
  choices["row:14"] = "skip";
  assert.equal(request.duplicate_choices["row:14"], "keep");
  assert.deepEqual(config, { subject_id: "owner", initial_cash: 100, resolution_market: "XNAS" });
});

test("missing confirmation identity and invalid market preview cannot commit", () => {
  assert.equal(canConfirmImport({ ...preview(), rows: [], preview_fingerprint: "" }, {}), false);
  for (const field of ["conflicts", "invalid_rows"]) {
    assert.equal(canConfirmImport({ file_sha256: "bytes", preview_fingerprint: "config", rows: [], summary: { [field]: 1 } }, {}), false);
  }
});
