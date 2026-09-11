# Agent presentation upgrade — 2026-09-11

## Scope

Make implemented Agent capabilities discoverable during a conversation, show numerical results as readable tables, and explain real progress/failure states. Preserve the existing orbital background, account boundaries, model consent, local conversation archive, and financial calculations. No new upstream feature parity or production-reliability claim is made.

The user authorized backing up, replacing and restarting `/Applications/投镜.app` **after validation**. Installation evidence is recorded below only when performed. This turn does not call a live model, read credentials, or send account data to an external service.

## User-visible changes

- Six entry points: investment review, comparison with one's own history, a Synthetic trade scenario, public stock research, financial knowledge, and chart guidance.
- A compact overview explains the benefit and the supported inputs. The same six categories remain above the composer after messages appear.
- Example questions fill and focus the composer; they do not send automatically, change consent, or silently switch accounts. Menus open above the composer, close with Escape, and restore keyboard focus.
- Whole-account tools link back to whole-account chat from an Episode. Trade scenarios are explicitly restricted to the existing Synthetic method. Professional comparison links to its dedicated workspace; strategy Lens is described as planned, not delivered.
- Verified new answers can include trade before/after tables, effective-period comparisons, owned same-stock records, public technical indicators, and report-period financial fields.
- Metric definitions and the originating cited-record reference can be expanded. Public material and owned account facts remain distinct. Non-overlapping or incompatible Episodes are not ranked as common-market performance.
- Reading, public searching, quote retrieval, answer preparation, and evidence checking have distinct status copy. Failures retain safe error categories and an allowlisted diagnostic ID. No fabricated percentage, elapsed-time promise, or hidden reasoning is shown.
- Existing saved text remains readable; it is not silently regenerated to add new tables.

## Data and implementation contract

`src/agents/analysis_cards.py` projects **only the intersection of read receipt references and references actually cited in the validated answer**. Values come from existing deterministic tool records, not from parsing model prose. The projector does display formatting and unit rendering, not new financial calculations. Optional malformed cards are omitted without invalidating otherwise valid text.

`account_conversation.py` adds the optional result-level field only after finalization. It is not a new LLM output schema. The existing runtime and archive retain the complete result envelope.

`apps/desktop/src/data/agentAnalysisCards.ts` validates bilingual text, bounded row/column counts, unique IDs/references and category/scope gates after the enclosing result passes its existing verification. `AgentAnalysisCards.tsx` renders escaped React text and accessible table headers, never HTML from the provider.

Relevant UI files: `AgentWorkspace.tsx`, `AgentCapabilityOverview.tsx`, `agentCapabilityCatalog.ts`, `AgentTurnStatus.tsx`, `agentTurnStatusModel.ts` and their scoped styles. The capitalized component and status-model helper have different basenames for macOS case-insensitive filesystems.

## Browser acceptance

The production chat route was checked using the registered Synthetic example in local browser preview. Choosing a question only filled the composer; the browser-only Send button remained disabled. Persistent comparison menus did not displace the composer, and Escape closed the menu.

The offline harness at `apps/desktop/tests/fixtures/agent-presentation.html` imports the actual production components. Its five card shapes are generated from the real Synthetic tool projections plus deterministic fake public adapters, explicitly marked `live_public_data: false`. It does not invoke a model or masquerade as live market data. It is not a production build entry.

Visual checks covered all five card kinds, Chinese/English, dark/light styles, narrow container overflow, method explanations and categorized failure status. Light-theme muted text was strengthened after visual inspection. Account performance values and a marked open Episode are labeled separately from realized results.

## Verification and installation

- Frontend: **357 tests passed**, typecheck and production build passed. The existing large-chunk Vite warning remains; it is not presented as resolved.
- Combined backend regression: **78 passed**, covering analysis cards, account conversation, chat archive, real analysis-tool integration, DSA conversation and public analysis. A later card-only run after explanatory-copy changes passed **6 tests**. These overlapping counts are not added together.
- Additional owned-source isolation, source-binding, sparse-history and fallback tests passed. `git diff --check` passed. No live provider or model was called in this turn.

An initial combined Python run returned 77 passed / 1 failed: the hypothetical-trade tool exceeded its existing 20-second deadline while rebuilding already prepared account HHI history. The fix reuses a private immutable history bound to the exact account, source fingerprint, method and valuation date. It is never serialized into model context and is discarded when narrowing to an Episode. Sparse history preserves the existing insufficient-evidence behavior. Formulae, tool deadlines and permission boundaries were not relaxed. A serial Synthetic comparison produced equal tool outputs with prepared-history reuse (~0.12 seconds) and fallback rebuilding (~6.29 seconds); this is **tool execution time, not total model-answer latency**.

The first signed package passed structural signature verification but failed process startup: Tauri had added hardened-runtime library validation to an ad-hoc PyInstaller process. The installed previous version used ad-hoc signing without that runtime flag. [PyInstaller's macOS signing documentation](https://pyinstaller.org/en/stable/feature-notes.html#macos-binary-code-signing) explains the distinction, and [Tauri's configuration reference](https://v2.tauri.app/reference/config/) documents the opt-in configuration override. A separate `src-tauri/tauri.local-adhoc.conf.json` and `npm run bundle:local` now make this **local-only** packaging mode reproducible. Default release configuration was not weakened. No system security setting, Gatekeeper policy or Keychain permission was changed. A future notarized release requires a properly signed nested Python payload and a real Developer ID workflow; this local build does not claim that status.

Final packaged-process acceptance (`scripts/qa_agent_presentation_package.py`) used a new temporary Synthetic database, with no credentials. It passed: handshake 15.67 s, local AKShare readiness 1.76 s, first account context 71.05 s, repeated context 0.028 s, equal scope/fingerprint/references, empty conversation archive, no private history leakage, and clean shutdown. These are one local measurement, not an SLA.

The verified package was installed at `/Applications/投镜.app` and restarted under the user's authorization. The original app was moved to `agent-ui-upgrade-20260911/backup-NDSzsd/投镜.original.app.backup` in the `investment-twin` workspace; a separately verified copy also exists there as `投镜.app.backup`. Database, chat archive and Keychain locations were not edited or deleted.

Installed SHA-256:

- Desktop executable: `788c51ddb901223d2c9b99ae501ebd3214092a8b55d5557bcd4a3a4a5973bdc1`
- Sidecar executable: `8df8103cebd943b3165541d2d9647d53a12167c8463618fbaf85e13867e2e1dd`
- Orb icon: `7aaed091d562421bbe8cb0b3b9550d2d71ed5f2a23a6ea0d562e309e16c181fb` (unchanged)

`codesign --verify --deep --strict` passed after installation. Native-window acceptance passed on the installed `/Applications` app: all six overview cards appeared in a 3×2 layout; configured model/research statuses resolved; the scenario example only filled the composer and left consent unchecked and Send disabled. Previously saved Synthetic conversations, including the first knowledge question and the latest stock-research question, reappeared without requesting a new answer. After navigating to Investments and back to Ask, the existing history appeared without a context-loading message, and all six persistent capability buttons remained. The pre-upgrade unsent public-research question was restored after the fill-only check. No Send button was clicked. The app was left on the new Agent page, and the temporary browser QA tab and development server were closed.

Native cold preparation was observed but was not instrumented as a clean timing benchmark; only the separate temporary-database measurement above has timed evidence. Archived old text is deliberately not rewritten or backfilled with new tables.

## Limits

The first cold financial-context build can still take time. Service configuration is not a guarantee that a public provider will respond. This update is not automatic trading, a complete strategy library, real-account hypothetical execution support, or professional account comparison inside chat. Offline scripted-provider tests demonstrate contracts and execution, not live-model answer quality or a measured production success rate.
