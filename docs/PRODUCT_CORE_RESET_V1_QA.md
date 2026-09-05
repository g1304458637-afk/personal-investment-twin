# Product Core Reset v1 — Checkpoints 1–3 acceptance

Scope: Product Shell / My Investments / Episode Review. Stop here for user review.
No account-level Review feed, Journal, Agent, Peer/Cohort work or push.

## Implementation boundaries

- Primary navigation: My Investments, Data; Settings is ancillary. Root and Overview
  redirect to Investments. Compatible legacy routes remain, outside primary navigation
  and commands. Legacy examples are explicitly separated from the selected account.
- New sessions start in real-user mode. No account is an import empty state, not an
  automatic example. Example ownership is selected explicitly by subject + account.
  Runtime errors never substitute example results.
- Investment rows copy authoritative Outcome results through one account-level
  `outcome_summaries` projection. Reopened positions remain separate rows. No per-row
  Path construction or frontend PnL/return calculation.
- `review_presentation` is optional presentation metadata, not a new financial
  Evidence contract. Story steps reference existing ordered phases and their recorded
  decision counts. More than four phases yields a deliberately abbreviated story.
- Review facts filter the existing `presentation_items` order for scope, valid dates,
  availability, deduplication and a maximum of three. No new importance score.
- Price and quantity charts reuse existing navigation and financial data; optional
  heights and user-controlled outside-holding context are display-only changes.
- Historical comparisons require an explicit selection/disclosure and state that
  their local evaluation result is not the investment's final result. Scenario,
  next-decision time and valuation observation remain inspectable.

## Reference implementation review

Local source reviewed for architecture only; no external source or visual assets copied:

| Reference | Inspected implementation | Applied idea |
| --- | --- | --- |
| Wealthfolio | `apps/frontend/src/pages/holdings/components/holdings-table.tsx` | Dense list, clear list/detail boundary |
| Ghostfolio | `apps/client/src/app/components/holding-detail-dialog/holding-detail-dialog.html` | Result-led holding detail, secondary detail disclosure |
| Portfolio Performance | `name.abuchen.portfolio.ui/.../views/panes/TradesPane.java` | Explicit trade periods and row-level results |
| Actual | `packages/desktop-client/src/components/accounts/AccountEmptyMessage.tsx` | Task-oriented empty state |
| ECharts | `test/connect-manually.html` | Linked chart interaction, reuse installed chart runtime |

## Actual product QA

Browser: actual localhost UI, zh-CN, dark, 1440×900 and 1280×720.
Native: separately identified **Toujing Product Reset QA** debug bundle,
`com.personal-investment-twin.product-reset-qa`, captured window 1246×768
(at least the configured 1180 minimum width). Formal account storage was not used.

The native QA account was seeded through the existing preview/confirmed import APIs
using `fixture_a_lifecycle.csv` and `runtime_lifecycle_prices.csv`. These are synthetic
test facts exercising the real-user runtime, not a claim of authentic investor data.
Its display name explicitly identifies it as isolated synthetic QA.

| Case | Observed result |
| --- | --- |
| No Account | Import-first explanation and secondary example button; no financial values; returning from Example clears its values |
| SYN_PRODUCT | Closed, CNY −283.50, −2.43%; 400 → 1,100 → 400 → closed, with two adds and two reductions |
| SYN_LONG_CLOSED | Closed, CNY 1,299.50, 10.44%; actual 2021–2025 observation axis |
| SYN_LONG_OPEN | Current marked result CNY 2,429.50, 24.89%; valuation 2026-01-15, explicitly not a realized exit |
| Isolated Real Runtime | Two rounds of 600000: closed CNY 366.00 / 23.61%, reopened marked CNY −1.00 / −0.40%; remains real-first after app restart |
| Short native lifecycle | No eligible review facts: no empty facts card is rendered |
| Review interval | Selecting consecutive adds / 894-day no-execution interval focuses both charts; timeline rail dragging keeps their domains synchronized |
| Disclosure | All trades, decision drawer, historical comparison and method/source details remain reachable; comparisons are initially hidden |
| Market background | Explicit outside-holding notice; opening background does not change the displayed lifecycle period/result |
| English | Navigation, archive, story, marked/final labels and currency formatting switch correctly; restored to Chinese after QA |

At 1440×900 the closed-example chart section starts around y=299; at 1280×720
the open-example section starts around y=324. Price chart remains on the first screen.
No horizontal document overflow was observed. Quantity and review facts require
vertical scrolling in the smaller window; there is no attempt to squeeze every fact
onto the first screen.

One focused polish pass removed inherited extra archive gaps, translated the Instrument
column, corrected Data-page Demo badges for real mode, and clarified browser-only
access limitations/loading copy. No financial algorithm or frozen contract changed.

## Automated verification

- Full Python: **611 passed** (395.26 s).
- Relevant Python presentation, Path, long-horizon and runtime tests: **47 passed**.
- Full Desktop Node: **148 passed**, zero failures.
- `npm run check`, `npm run build`, `cargo check`: passed.
- Isolated Tauri debug app bundle: built and actually launched.
- `git diff --check`: passed.
- Export run twice: byte-identical; SHA-256:
  `089905385baedfc09a92edd635e42aef4aca0a63967e343ffbcb866e5c49a99a`.
- Removing only the new `review_presentation` metadata makes the generated payload
  structurally identical to checkpoint `cedf749`; all pre-existing financial fields
  remain unchanged.

New tests cover single-build archive projection, exact authoritative result copying,
unavailable-result handling, example ownership, real-first startup, source-linked story
counts/order, no-lookahead review eligibility, deduplication, empty/max-three facts,
malformed review refs and explicit disclosure. Existing UI structure assertions were
updated to the new hierarchy while retaining financial/adapter assertions.

## Screenshots and known limits

Actual screenshots remain local/ignored under `artifacts/ui/product-reset-v1/`.
The `product-reset-*.jpg` files are original CUA JPEG bytes, not generated mockups or
resized renders. Both requested sizes exist for the three examples and archive/empty
states. Native screenshots are `product-reset-real-open-tauri.jpg` and
`real-closed-tauri.jpg`.

- Build retains the existing large-bundle warning; no dependency or bundling overhaul.
- Development logs contained transient `DataModeProvider missing` errors during hot
  replacement. A fresh load after source/export stabilized, followed by account and
  page navigation, produced no new errors. The native built application loaded and
  read the isolated persisted account successfully. HMR hardening is not claimed here.
- Some endpoint chart labels remain close to the chart edge; complete execution text
  is available via its marker/drawer. No navigation/financial chart algorithm changed.
- Existing detailed evidence/method UI is intentionally retained, not redesigned into
  Checkpoint 4. Absence of linked Evidence remains explicit rather than fabricated.
- This is product QA, not a new exhaustive trackpad, packaged-sidecar, large-account
  performance or authentic-user-data certification.

Next action belongs to the user: inspect My Investments and Episode Review, then decide
whether Review should become a primary destination and how Inspector should converge.
