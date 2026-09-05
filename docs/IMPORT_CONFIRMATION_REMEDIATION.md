# Confirmed import identity and instrument reconciliation

Commit parses the same byte payload whose SHA was checked (Repair 1). It now
also requires the preview fingerprint covering those bytes and the supplied
interpretation configuration. Subject/account, timezone, row ordering, mapping,
initial cash, source/version and instrument confirmation changes require a new
preview. Only transport, confirmation tokens, audit timestamp and explicit
post-preview duplicate choices are excluded. No silent re-preview/accept occurs.

Desktop retains the configuration that produced the preview, hides it when
inputs change, ignores obsolete preview completions and renders every row in a
scrollable review. Every possible duplicate requires an explicit keep/skip.

SQLite migration 2 adds append-once, account-owned execution instrument
resolutions. An unresolved persisted fact is matched using the same confirmed
bytes interpreted without the instrument override. Qualification changes only
its instrument projection; original execution ID, raw payload, sequence and
financial facts remain immutable. A conflicting second resolution fails closed.
Restart rebuilds the qualified projection from canonical facts plus the audited
resolution. Deleting the account cascades through resolution audit records.

This changes persistence metadata and the narrow runtime confirmation protocol,
not Canonical Execution or any financial method/Evidence contract.

Verification: 37 runtime/import/persistence/process tests; 127 Desktop Node
tests; TypeScript check and build. Adversarial tests cover changed configuration,
original-byte integrity, stable identity after qualification/restart, schema-1
migration and explicit duplicate decisions beyond row 12.
