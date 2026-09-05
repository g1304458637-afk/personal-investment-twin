# Evidence-grounded review and limited Episode sharing v1

This is the native OpenAI Agents SDK loop over the existing DeepSeek Responses
provider (`tool_choice=required`, reasoning effort `none`). There is no new
HTTP runtime or new financial engine. Six function tools expose scoped derived
facts, not raw CSV, arbitrary account queries or SQL.

Every accepted run must have actually executed own-Episode retrieval, both
support and contradiction searches, registered historical comparisons, and
registered self-history. A comparison run must also execute the comparison
tool. SDK `new_items` receipts are audited. All final references must have been
retrieved in this run. Valid reference existence alone does not establish
support: v1 hypothesis kinds require matching deterministic relationship tags
or explicitly labeled user testimony. Known prior-plan notes must be addressed
as contrary material when considering price influence.

## Deliberately bounded interpretations

The model selects tools, references, hypotheses, alternatives, missing inputs,
and a follow-up question in a structured native SDK output. V1 has four supported
hypothesis kinds: price influence possible, reported staged plan, reported reason,
and unknown. Their final wording is bounded; the model does not author financial
numbers or freely assert motives. This is a real tool loop but **not an open-ended
financial essay generator**. Unsupported explanations abstain. Scripted-model
tests verify enforcement, not live-model behavioral quality.

Actual facts, registered historical alternatives and revisable interpretations
remain separate. Scenario definitions/versions come from the existing registry.
Self-history reuses only HHI and mean daily turnover, not an invented sequence
frequency or long-term skill score. Shared underlying execution refs are not
multiple independent observations.

## Mutable local read models

The existing SQLite connection owns separate `review_*_v1` tables for notes,
inferences and imported shares. No new database file, canonical row, Evidence
schema or Twin fact is created by review. Notes are recorded now and labeled
retrospective. New notes invalidate old interpretations; a new interpretation
records its predecessor replacement. Account-source fingerprint changes or
revoked/expired share permissions invalidate historical review display.
Worker threads receive projections, never the SQLite connection. Request jobs
are bounded, timed out, account scoped, and cannot publish stale results after
new notes, data changes, or permission expiry/revocation.

## Explicitly approved sharing contract

The user approved: the counterpart voluntarily exports one limited Episode's
derived facts, which are imported locally; no raw trade CSV is shared.

`episode_derived_share_v1` binds the qualified instrument, subject/account/Episode,
as-of, derived decisions/path/results, recipient subject/account, expiry and
separate model-review permission. It contains decision times, quantities,
execution prices and outcomes: this is still sensitive derived information.
Original execution IDs are replaced by internal share refs. There is no raw
file, cohort contribution permission or arbitrary remote account access.

A separately conveyed bearer secret and HMAC protect exact package integrity.
This **does not verify legal identity, brokerage truth or independently replay
the received facts**. The share source and Inspector disclose this limitation.
It is a local explicit-consent boundary, not a multi-user authentication system.
Both actors are trusted to own the local records they explicitly share.

Local comparison permission does not authorize model transmission. Model review
requires both the sender's separate permission and the recipient's explicit
model consent. The secret is not persisted or sent to the model. Imports verify
the exact bytes read once; exports exclusively create a `.toujing-share.json`
file and never overwrite an existing path. Permissions are checked before
counterpart model facts are constructed, at tool use, and before accepting
results. Revocation cannot retract an offline copy on a different machine or
facts already transmitted; the UI discloses that limitation.

## Runtime and UX

Narrow allowlisted local RPC: `review.context/start/poll/add_note` and
`compare.export_share/import_share/list_shares/revoke_share`. The existing
provider reads existing environment configuration; no key is logged or written.
Browser mode is explicitly offline with deterministic synthetic charts only.
It cannot claim a model call. Native runtime performs the actual tools/model loop.

Outstanding acceptance evidence must be recorded separately for browser, native
runtime, live provider, and physical trackpad/WKWebView. Unit tests alone cannot
certify any of those product interactions.
