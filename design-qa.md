# Liquid Glass application pass — 2026-09-06

## Target and scope

The user selected the **right-hand translucent investment card** in the running
Liquid Glass demo and requested an application-wide implementation. This is an
adaptation of that material to a working financial application, not a pixel clone
of the demo's marketing composition.

- Source: `/private/tmp/toujing-liquid-reference-1440.png`, captured from `http://127.0.0.1:1423/`.
- Implementation: `/private/tmp/toujing-liquid-investments.png`, `http://127.0.0.1:1420/#/investments`.
- Further evidence: `/private/tmp/toujing-liquid-analysis.png`, `/private/tmp/toujing-liquid-episode.png`, `/private/tmp/toujing-liquid-mobile.png`.
- Desktop reference and implementation: 1440 × 900 CSS/pixel captures, 1:1; no density rescaling. Mobile: 390 × 844.
- State: zh-CN, dark, explicitly selected Synthetic example. English/light and real-account empty states were also inspected.
- Source and implementation were opened together in a single image comparison input. The investment cards are readable at this size; a separate enlarged crop was not needed to inspect the edge, type, value, date and action treatment.

## Design and information hierarchy

- Three primary tasks: Investments, Analysis & comparison, Decision preparation. Data and Settings remain auxiliary. Existing review, history, journal, ask and evidence routes remain reachable; command search includes the new analysis hub.
- Application-shell video persists across route transitions. A stronger page scrim and darker chart/reading panels intentionally reduce motion and contrast competition relative to the standalone demo.
- Card material retains the 1% white surface, 4px backdrop blur and masked gradient edge. Interactive cards have pointer-following light, restrained hover lift and press feedback. Static financial panels do not lift on hover.
- Existing charts, quantities, Outcomes, historical metrics, comparison values and permission/runtime gates are reused. No generated payload or financial implementation was edited.
- The source's oversized hero and non-monospace result are deliberately not copied: the application retains its existing system typography and monospace financial values for scanability, offline font support and consistency.

## Comparison history

1. P2 — lazy page CSS overrode card layout and restored table columns. Fixed by scoping the application material with higher specificity. Later archive capture shows three separate cards with readable values and actions.
2. P2 — inherited flex gaps plus section margins pushed the first investment below the fold. Removed redundant margins; later archive capture shows the complete first row at 1440 × 900.
3. P2 — inherited account-context width stacked History provenance chips into a large header. Removed that width restriction in the History scope, retaining every source field.
4. P2 — light-mode Synthetic label had insufficient contrast. Applied a darker amber label/semantic warning token in light mode.
5. P2 — same-stock page mixed flex gaps and utility spacing. Grouped its introduction and reused glass result panels; no comparison values, formula, scope or callbacks changed.

## Fidelity and interaction checks

- Typography: Chinese/English hierarchy and wrapping inspected; system font retained intentionally. Financial values remain monospace.
- Spacing: cards, task hub, chart/detail, form and settings checked at desktop size; 390px archive and Settings have no document horizontal overflow. Mobile navigation opens, routes and closes after selection.
- Colors/material: same supplied blue/amber video, masked quiet edges, transparent surfaces. Light mode is an intentional daylight counterpart. Chart and inspector glass is more opaque for reading.
- Imagery: original remote video, no downloaded copy, no substituted bitmap or copied branding. Retains existing Toujing mark. Failure falls back to a static gradient; decorative media has no account parameters.
- Copy: actual/marked results and Synthetic/offline/runtime boundaries retained. Missing history does not load another account until an explicit registered-example switch.
- Verified interactions: investment card → Episode, execution → factual drawer → close; history mismatch → explicitly select registered study; comparison hub → independent A/B example; decision-check offline result → edit quantity → stale result cleared; Settings language/theme; background pause/resume; mobile menu.
- No Vite error overlay or blocking route failure observed. No authenticated native import, real-user share or paid model invocation was performed in this visual pass.

## Verification

- Python: 751 passed.
- Desktop Node: 184 passed, including four new navigation/media-boundary tests.
- TypeScript check, Vite production build, cargo check: passed.
- `git diff --check`: passed.
- Vite retains `strictPort: true`, port 1420; actual HTTP response verified as 200.
- Existing large-chunk build warnings remain; no dependency was added.

## Follow-up / intentional boundaries

- Video is the user-supplied remote asset. Fully offline video packaging and distribution rights were not established; graceful fallback is present.
- Browser import and unconnected capabilities remain labelled previews; this pass does not claim native workflow recertification.
- The classic presentation and isolated reference demo are preserved. No commit or push.

final result: passed

## Welcome entrance and animated sphere logo

- Source: `/private/tmp/toujing-liquid-reference-1440.png` (approved liquid-glass demo).
- Implementation: `/private/tmp/toujing-welcome-final.png`; mobile English: `/private/tmp/toujing-welcome-mobile-en.png`.
- Desktop source and implementation are both 1440 × 900 pixels/CSS viewport; no density resampling. Mobile is 390 × 844.
- Source and implementation opened together for comparison. Introduction content intentionally replaces the lab controls; the right-hand example uses existing generated results.
- Typography: restrained system font, two-line Chinese headline; English wraps naturally on mobile. Layout: left explanation/right single translucent card; no horizontal mobile overflow (380px content in 390px viewport).
- Color/image: same supplied video and thin masked glass edge. Initial overlay dimmed the blue/gold excessively (P2); reduced overlay opacity and re-captured/re-compared. Final video remains visible with legible foreground text. Sphere logo uses independent local artwork, no hand/video crop; visible circle has no checkerboard leakage.
- Focused logo and card inspected in the full-resolution capture; monetary values, dates and Synthetic label remain readable. No replacement financial calculations.
- Interaction checks: explicit sample CTA selects matching subject/account and opens exact Episode; enter-workspace preserves selected account; logo returns to welcome; English toggle works. Reduced-motion rules disable logo animation and existing video control remains available. No Vite blocking overlay; video readyState 4. Native/offline media delivery not newly certified.
- Tests: frontend 189 passed; TypeScript and production build passed; existing bundle-size warnings remain. Five added tests cover startup preference, restricted storage, scoped example entry and reduced-motion asset use. No backend changes this increment.
- Residual P3: independent high-resolution logo bitmap could later be optimized for packaging; remote-video distribution/offline rights remain a separate deployment consideration.

final result: passed

## Opt-in investment review sample — local only

- Target: existing glass Episode detail plus the approved process-first hierarchy; not a new visual identity. Source `/private/tmp/episode-original-1440.png`, implementation `/private/tmp/episode-sample-final.png`, both 1440 × 900 at 1:1 density. Original has its default top padding; sample scroll aligns its toolbar to the content start. Both show the same Synthetic H account and full investment range.
- Both images were opened in the same comparison input. The original result, dates, story, price/quantity paths and three backend-selected facts are retained. Only section grouping, sizing and surface hierarchy differ intentionally.
- Initial findings: quantity pane below the first screen; shortening it caused cramped ticks; chart scrim referenced a nonexistent background token. Fixed by compacting the price pane/header, restoring the original quantity height and using the existing canvas token. Revised capture shows the full quantity pane and a stable 92%-opaque chart surface.
- Typography and spacing: existing system fonts/tabular figures; compact heading, separate result, four section buttons. Colors: existing glass palette, subdued fact rail and stronger chart reading surface. Assets: existing video/logo untouched. Copy: bilingual presentation strings, explicit Synthetic and unavailable-analysis boundaries; no new financial claims.
- Focused interaction evidence: selecting consecutive additions exposes 2025/01/24 and 2025/02/20 actions; first action opens original drawer (300 shares, recorded fee ¥2, before 400 / after 700). Existing counterfactual and provenance disclosure remain untouched. Reset uses the existing time-navigation reset. All six actions remain under All actions. Evidence disclosure retains genuine empty state rather than borrowing another Episode's refs.
- Browser checks: four sections, fact selection, decision drawer, original/sample toggle and source disclosure work. Mobile capture `/private/tmp/episode-sample-mobile.png`: 390 × 844, content width 340, no horizontal page overflow. This is responsive browser inspection, not native iPhone certification. No Vite blocking overlay. Full browser console/native runtime were not recertified.
- Tests: 192 frontend tests passed; check/build and diff check passed. One existing markup assertion updated for the explicitly hidden ledger section; three tests added for opt-in scope preservation, bilingual sections and original data/ownership links. Python/financial modules unchanged; no backend regression rerun.
- No deployment, no commit. Existing online video-loading issue remains separate and unresolved.

## Independent Agent conversation UX — 2026-09-07

- Scope: approved conversation-first revision of the supplied Ask Toujing screenshot, not a new visual identity. Existing glass sphere, video, fonts, icons and account boundaries retained. The side guide is now collapsed; the reading surface is quieter.
- Source: user attachment `codex-clipboard-e0a46b6b-ea63-4d65-8858-b6cffb18be30.png` (2880 × 1780). Evidence: `/tmp/toujing-chat-browser-final.png` and `/tmp/toujing-chat-native-retry.png`. Browser/native captures use different window sizes; this is responsive hierarchy verification, not a same-size pixel-fidelity claim.
- Native verified: whole-account Synthetic scope loads; selecting a question fills the composer; explicit model consent enables sending; welcome disappears after send; backend research/writing phases appear in the transcript; a failed real model answer leaves the original question and an in-place retry button. Composer stays in the conversation frame. No fabricated success answer was used.
- Browser verified: offline label, disabled model sending, existing chart guidance and collapsed help. Existing browser scroll position can leave the page heading above the viewport; no claim of full native trackpad certification.
- Unit verification covers retry-in-place, no mutation of previous turns, rejection of stale/running/completed retries, source-bound chart identity mapping, separate context/model/answer states and closed help by default.
- Found and fixed: packaged cold Synthetic context took about 43 seconds after handshake, exceeding the old 30-second request deadline. Only `review.context` now has a bounded 120-second deadline; other requests remain 30 seconds. Source computations unchanged. Also separated Keychain configuration loading from account context: the old Promise.all kept displaying account loading while macOS credential access was waiting. Security prompts remain user-controlled.
- Regression: Python full 948 passed; latest focused Agent 21 passed; Desktop Node 294 passed; TypeScript/build passed; Rust runtime tests 5 passed and cargo check passed. Existing bundle-size warning remains.
- Acceptance limitation: current live Synthetic model runs still sometimes fail paragraph-level numeric/evidence verification after the allowed single correction. Native final success/linked-chart flow is therefore not certified in this pass. No verification gates were weakened, no real-account data sent, no commit or deployment.

final result: blocked — visual/interactivity revision verified; complete real Agent success-flow acceptance remains open.

final result: passed
