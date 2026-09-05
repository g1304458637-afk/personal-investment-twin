# Episode Review · Optical Intelligence Workspace v1

## Boundary / baseline

Visual direction experiment on top of `c4cbbd1`. This does not assert a new
Agent freeze or change its acceptance state. Default Episode Review is retained.
No route registry, account state, financial data, tool, Agent, comparison,
Evidence validation, Python, sidecar or Tauri source changes.

The only page integration is a route-local `visual=optical-v1` query parameter,
optical CSS classes and small presentation components. No persisted flag and
no second Episode page, data adapter, renderer or business state machine.

## Phase 1 — inspected implementation

```text
WorkspaceShell / InspectorProvider (unchanged)
└─ PositionEpisodePage — single account-owned entry + existing selection state
   ├─ title / authoritative Outcome / backend-selected factual story
   ├─ PositionEpisodeTimeline ──┐
   ├─ PositionQuantityTimeline ┴─ shared useDailyTimeNavigation / EChart
   ├─ DecisionAnalysisWorkspace (existing real-account gate)
   │  ├─ analysis / permitted same-stock comparison / self-history
   │  └─ explicit model consent / original request guard and tools
   ├─ selected factual interval / disclosure of historical hypotheses
   ├─ executions / context / Evidence disclosures
   └─ DecisionDrawer → existing Radix Sheet / Evidence links
```

Installed versions: React 19.2.8, Motion 13.1.1, ECharts 6.1.0, Vite 8.2.2,
Tauri JS 2.11.1, Rust Tauri 2.11.5 / Wry 0.55.1. Tailwind 3.4.17 utilities
combine with CSS custom properties and `src/index.css`; the new stylesheet is
separate and scoped. Existing `motion/react` is already configured with
`reducedMotion="user"`. No animation dependency was added.

`EChart` uses CanvasRenderer, ResizeObserver and a single shared time-domain
store. Wheel, ctrl-wheel, WebKit gesture events, keyboard and dataZoom ownership
remain in their original modules. No optical overlay receives chart gestures.

The macOS app uses the system WKWebView, not Chromium. Tested host: macOS
26.6.1. Existing app minimum is 1180×720. Default chart series have a fixed dark
palette; the experimental light mode retains a dark plotting surface rather
than recoloring or distorting those series.

Safe insertion points: header, explicit experiment toggle, selected-decision
Sheet header, existing disclosure containers, existing mode controls. Not safe:
chart canvas, series builders, canonical data adapters, account ownership,
Agent inputs or comparison permissions.

## Phase 2 — reference decisions

Source inspection was limited to official individual components, not a clone
or CLI installation. React Bits currently declares **MIT + Commons Clause**,
not unqualified MIT. No component source or brand asset was copied. The effects
below are original, smaller implementations of general interaction principles.

| Pattern / official reference | Decision | Purpose / restriction |
| --- | --- | --- |
| [LightRays](https://github.com/DavidHDev/react-bits/blob/main/src/ts-default/Backgrounds/LightRays/LightRays.tsx) | REFERENCE ONLY; reject direct integration | Its OGL shader and visible-state render loop are unnecessary. One faint, finite CSS light arrival is confined above the plot; then static. |
| [FluidGlass](https://github.com/DavidHDev/react-bits/blob/main/src/ts-default/Components/FluidGlass/FluidGlass.tsx) | REFERENCE ONLY; reject Three/Fiber/FBO implementation | Borrow the idea of an optical focus object. The Lens sits in the header and accompanies the actually selected Decision in the existing modal, never the pointer or the chart. |
| [GlassSurface](https://github.com/DavidHDev/react-bits/blob/main/src/ts-default/Components/GlassSurface/GlassSurface.tsx) | ADAPT principle only | Fine rim, weak chromatic separation, local translucent controls. Its SVG backdrop path explicitly falls back on Safari/Firefox; do not rely on it in WKWebView. |
| [AnimatedContent](https://github.com/DavidHDev/react-bits/blob/main/src/ts-default/Animations/AnimatedContent/AnimatedContent.tsx) | ADAPT principle only | Opacity + 4px reveal for selected/disclosed context. No GSAP/ScrollTrigger, scroll hijack, bounce or hidden content awaiting an observer. |

Sources: [React Bits license](https://github.com/DavidHDev/react-bits/blob/main/LICENSE.md),
[Tauri WebView versions](https://v2.tauri.app/reference/webview-versions/).

Four roles, not a collection of effects: spatial orientation, selected-decision
Lens, context reveal, a small mode-control surface. No WebGL, external asset,
continuous animation, mouse tracking, new requestAnimationFrame or new dependency.

## Phase 3 — implemented visual direction

- Graphite, warm-neutral typography and precise outcomes; no global recoloring.
- One quiet continuous page, thin separators and a matte 2D plotting area.
- The existing sidebar and Mirror Orb are unchanged. This is deliberately not
  a shell redesign or all-app theme.
- The title, dates, result, story and two chart panes remain the first screen.
  First visual review found a separate Lens row too tall; it was moved into
  the header so both panes fit at 1440×900.
- Selecting a real chart execution still opens the same modal, same selected
  ID, same source-linked facts. An active Lens and timestamp accompany it.
- The original modal scrim stays modal and keeps its focus trap/Escape behavior.
  In optical mode only, the chart behind it is dimmed, not blurred.
- Technical details/counterfactuals remain behind the existing disclosures.
  No story, ranking, result or explanation was invented for the visual.
- Existing analysis/compare/self controls receive scoped surface styling; their
  requests, consent and permissions remain unchanged.

### Lens / performance honesty

The Lens is a small transparent optical illustration, **not a physical 3D glass
simulation or a magnifier of financial data**. A fixed SVG displacement affects
only decorative etched lines inside its own aperture. CSS draws thin reflective
rims and local chromatic edges. The text, numbers, chart and axes are never
passed through the filter. This works without SVG `backdrop-filter:url(...)`.
CSS backdrop blur is progressive enhancement on the empty Lens surface and
small mode strip only; borders/background remain as the fallback.

### Motion tokens (experiment scope)

| Token | Value | Role |
| --- | --- | --- |
| Fast | 130ms | focus/hover, Lens reticle |
| Reveal | 240ms | context and decision panel |
| Ambient arrival | 700ms, once | faint header light, then static |
| Easing | cubic-bezier(.22, 1, .36, 1) | shared, non-spring |
| Travel | 4px maximum | reveal, not chart transformation |
| Entry opacity | .65 → 1 | transient context |
| Content blur | 0px | no blur-to-sharp on financial text |

`prefers-reduced-motion: reduce` removes all new animation/transition/travel.
The experiment does not alter existing chart animation policy or other pages.

### No invented comparison / Agent content

Existing generated Episode accounts are not the separate SYN_COMPARE_A/B pair.
It would be a scope error to attach those comparison numbers to an unrelated
Episode for a prettier screenshot. In demo Episodes only, a clearly unavailable
capability strip explains the boundary and links to the **separate** existing
A/B Synthetic example. It does not invoke a model or fabricate an answer.
Real-account review still uses the existing permitted sharing/analysis path.

## Phase 4 — verification

- Before implementation: 158 Desktop Node tests passed.
- After implementation: 165 Desktop Node tests passed (7 new boundary tests).
- TypeScript `npm run check`, `npm run build`, `cargo check`: passed.
- Existing Vite large-chunk warning remains; no dependencies/chunk framework
  were changed to hide it. Optical page CSS is approximately 2.5kB gzip.
- `git diff --check`: passed.
- Backend, Agent, generated JSON, financial adapters, chart modules, comparison
  modules, Tauri source and dependency manifests: unchanged by diff inspection.
- Python regression was not re-run for this frontend-only experiment.

25 isolated Chrome/CDP checks passed against actual Synthetic UI, including:

1. Exact ECharts series, values, visible dates and instance IDs unchanged when
   enabling the experiment (not merely an assertion that the page loads).
2. Actual canvas marker click opens the exact Decision ID; active Lens,
   execution tooltip, focus trap, Escape and unblurred modal backdrop verified.
3. Keyboard zoom, horizontal wheel pan, ctrl-wheel zoom, vertical page scroll,
   two-pane synchronization, factual interval selection, returning to original.
4. 1440×900 chart + quantity pane, no horizontal overflow at 1180×720 and
   960×720 browser fallback, real Settings language switch, light theme.
5. Reduced motion disables new CSS animation; settled experiment has no running
   animations. A 1.5s reduced-motion idle sample used about 1–3ms JS task time.
   This is not a GPU/power benchmark or proof for every device.
6. Demo analysis buttons disabled; no model request; no blocking browser errors
   on fresh navigation. An old dev-tab LocaleProvider HMR context required a
   full reload; no provider code was modified to work around it.

Native smoke: existing Tauri dev binary launched with a temporary CLI config
and isolated identifier `com.personal-investment-twin.optical-qa`; fixed 1420
server reused. Existing Synthetic Episode and experiment rendered in real
WKWebView. Native resize to 1180×720 and restoration were checked. This did not
import real data, call the Agent, alter permissions or change Tauri source.

Physical multi-finger trackpad feel is **not certified** by browser wheel
simulation. Dedicated hardware GPU profiling and full live-model/sharing QA
are outside this visual experiment. Existing consent paths are untouched.

## View / compare / remove

1. Open `http://127.0.0.1:1420/#/investments`.
2. Choose an existing Example account (Synthetic), then open an investment.
   The long-held closed example gives the densest useful chart test.
3. Click **体验 Optical 视觉实验**. It adds `?visual=optical-v1` inside the
   hash-route URL. Click **视觉实验中 · 返回原版** to return immediately.
4. The same switch works for an already available native real-account Episode,
   without changing ownership, inputs or requesting any analysis.

No automatic account selection from a URL. Deep links still enforce the
currently selected account. Refresh starts with the existing real-first policy.

Dev server remains at `http://127.0.0.1:1420` with strict port enabled.
Normal Tauri usage remains `npm run tauri -- dev`; with the server already
running use `npm run tauri -- dev --no-watch --config
'{"build":{"beforeDevCommand":""}}'` to avoid a duplicate server start.

Local/ignored screenshots under `artifacts/ui/optical-review-v1/`:

- `baseline-1440.png` — original before this change.
- `episode-review-optical-zh-dark-1440.png` — final main screen.
- `episode-review-optical-decision-focus-1440.png` — selected Decision Lens.
- `episode-review-optical-evidence-boundary-1440.png` — disclosure/boundary.
- `episode-review-optical-zh-small.png` — 1180×720.
- `episode-review-optical-en-dark-1440.png`, `episode-review-optical-en-light-1440.png`.
- `episode-review-optical-wkwebview.png` — native window, display-resolution PNG.
- `browser-qa.json` — names of 25 checks and an empty exception list.

All experiment production code lives under `src/experiments/optical-review/`,
plus small page/locale integration. The independent visual checkpoint can be
removed in full later without a backend migration. No reset/revert was used in
this task. Stop here for visual-direction acceptance; do not spread to the app.
