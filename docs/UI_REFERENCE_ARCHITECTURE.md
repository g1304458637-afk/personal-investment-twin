# UI Reference Architecture

## Study scope

This study precedes the Desktop UI Foundation implementation. The five source
repositories below were cloned as shallow, read-only references under
`~/Projects/ui-references/`; they are outside this repository, are not Git
submodules, and are not runtime dependencies of Personal Investment Twin.

Study snapshot: 2026-09-03

| Reference Project | GitHub URL | License | Relevant Module | What We Borrow | What We Do Not Borrow | Reason |
| --- | --- | --- | --- | --- | --- | --- |
| Tauri 2 | [tauri-apps/tauri](https://github.com/tauri-apps/tauri) | MIT OR Apache-2.0 | Core process, WebView window, capabilities, packaging | A single native core process, a single workspace window, a narrow command/event boundary, platform-aware window configuration, and least-privilege capabilities | A custom plugin system, updater, sidecars, tray-first lifecycle, or cross-platform transparent companion windows in v1 | Tauri is the desktop shell; the current milestone needs a reliable workspace, not a desktop platform |
| Jan (`9e12b2a`) | [janhq/jan](https://github.com/janhq/jan) | Apache-2.0 at repository root | `src-tauri/`, `web-app/`, `core/`, settings and platform build configs | Separation of React UI, shared typed application boundary, and Rust-owned native lifecycle; close/hide/quit cleanup as distinct concepts; platform-specific packaging config | Jan's model engines, extensions, large native `AppState`, broad asset scopes, local API server, or platform build pipeline | The boundary is mature and relevant, while the AI/model platform is far beyond this UI milestone |
| OpenPets (`a0df374`) | [alvinunreal/openpets](https://github.com/alvinunreal/openpets) | MIT | `apps/desktop/src/pet-window.ts`, lifecycle, display and motion engine | Orthogonal visual state and motion state, one owner for animation state, visibility-aware work, stable positioning rules, non-focus-stealing ambient presence | Pet sprites, Electron runtime, MCP/CLI/plugin platform, platform-specific click-through workarounds, or forced X11 behavior | The Mirror Orb benefits from calm state transitions; a financial workspace should not inherit pet-platform complexity |
| shadcn/ui | [shadcn-ui/ui](https://github.com/shadcn-ui/ui) | MIT | Sidebar, Dialog/Sheet, Tabs, Tooltip, Command, Table, Dropdown and form controls | Accessible, composable control patterns with project-owned styling; one consistent Radix primitive stack | A second UI framework, mixed Base UI/Radix primitives, or untouched default visual styling | Controls should be mature and keyboard-safe while the visual system remains 投镜-specific |
| assistant-ui (`60ae973`) | [assistant-ui/assistant-ui](https://github.com/assistant-ui/assistant-ui) | MIT | Core runtime types, React primitives, streaming transport and tool UI | A future Agent Panel boundary that separates presentation, conversation state, transport and backend; explicit message/run/tool states; cancellation and stable event identity | Its full monorepo, cloud/persistence layer, HTTP transport, arbitrary generative components, or an Agent runtime in this milestone | The current shell needs a stable panel slot, not a partially connected chat product |
| Magic UI (`2d671cc`) | [magicuidesign/magicui](https://github.com/magicuidesign/magicui) | MIT | `magic-card`, `glare-hover`, `shine-border`, `number-ticker` | Pointer-safe decorative layers, a restrained local glare, tabular number reveal, and `motion-safe` ambient treatment | WebGL backgrounds, particle fields, neon card systems, permanent border beams, or effects on every surface | Small accents can create reflective depth; repeated marketing effects would reduce data legibility and increase GPU cost |
| Motion Primitives (`92586e6`) | [ibelick/motion-primitives](https://github.com/ibelick/motion-primitives) | MIT (`LICENCE.md`) | Animated number, transition panel, animated background, spotlight and disclosure patterns | `AnimatePresence` for panel/page changes, shared-layout active indicators, spring-smoothed numbers, and explicit controlled state | Copying the component library, hover-only semantics, infinite glow defaults, per-digit animation for every metric, or implicit parent-style mutation | Its minimal patterns are useful, but accessibility and reduced-motion policy must be owned by the product |
| Motion | [motiondivision/motion](https://github.com/motiondivision/motion) | MIT | `motion/react` | Composited page/panel transitions, presence, layout indicators, motion values and user reduced-motion preference | A custom animation engine, bounce-heavy springs, scale-on-every-hover, or animation of high-frequency chart data | One mature motion runtime gives consistent timing and interruption without bespoke infrastructure |
| Apache ECharts | [apache/echarts](https://github.com/apache/echarts) | Apache-2.0 | Tree-shakeable core, line charts, tooltip and resize lifecycle | A thin React lifecycle wrapper: initialize once, update options, resize with the container and dispose on unmount; expose an accessible labelled chart container | Decorative SVG charts, re-creating the chart on every render, importing every chart type/theme, or presenting random values | Financial charts need real axes, tooltips and deterministic data with a proven renderer |

## Source-review findings

### Jan: desktop boundary and lifecycle

Jan is a Yarn workspace split into `core`, `web-app`, and extensions, with the
Tauri/Rust shell kept under `src-tauri`. Its Rust entry point centralizes
commands and application lifecycle, while the React application consumes typed
native services. Closing, hiding, reopening, and quitting are separate paths;
quit performs settings flush and native-resource cleanup. Platform build files
are also separated from the common Tauri configuration.

For 投镜 v1, that becomes a much smaller rule: React owns presentation and
temporary UI state; Rust owns only native window lifecycle and future privileged
operations. No financial calculation moves into either layer, and no large
global native state is introduced.

### OpenPets: ambient companion mechanics

OpenPets uses transparent, always-on-top companion windows and a main-process
lifecycle with tray, IPC, plugins, and cleanup. Its useful idea is not the pet
window itself but the separation of reaction, motion, visibility, and
interaction state. Motion work is shared and stops when inactive; click-through
and focusability are platform-aware.

The workspace Mirror Orb therefore uses four explicit presentation states
(`idle`, `hover`, `thinking`, `active`) inside the normal workspace window.
There is no floating desktop window, click-through layer, sprite engine, or
always-on-top behavior in this milestone.

### assistant-ui: future Agent Panel seam

assistant-ui separates frontend primitives, runtime state, transport adapters,
and the actual agent backend. Messages and tools have explicit running,
complete, incomplete, approval, error, and cancellation states. Streaming
updates are locally subscribed rather than forcing the entire UI tree to render.

The current implementation reserves an `AgentPanel` presentation boundary only.
A future integration can supply a versioned controller and event stream without
changing the workspace layout. Model execution, tools, persistence, approvals,
and transport are intentionally absent from v1. Arbitrary model-generated UI is
never rendered without a fixed component allowlist and schema validation.

### Magic UI and Motion Primitives: selective motion

The source review found reusable small patterns: pointer coordinates smoothed by
Motion values, decorative layers marked non-interactive, shared-layout active
backgrounds, number springs with tabular numerals, and presence-based panel
transitions. It also found patterns unsuitable for this product: canvas/WebGL
ambient grids, continuous particle systems, numerous blur layers, infinite beams
on every card, and components without complete keyboard or reduced-motion
semantics.

投镜 borrows the implementation ideas, not the components or their styling.
Ambient animation is concentrated in the Mirror Orb and background reflection;
financial surfaces use short opacity/translation transitions and stable
typography.

## Resulting v1 architecture

```text
Tauri 2 core process
  └─ main workspace WebView (1440×900 target, 1280×800 supported)
      └─ React + TypeScript + Vite
          ├─ Workspace shell (navigation, title area, theme, command surface)
          ├─ Route pages backed only by deterministic demo fixtures
          ├─ shadcn-style controls on one Radix primitive stack
          ├─ ECharts lifecycle wrapper for deterministic charts
          ├─ Motion policy (presence, shared indicator, number reveal)
          └─ Agent Panel presentation seam (no runtime/backend)
```

### Native boundary

- Start as one normal, resizable workspace window with native decorations and a
  transparent title-bar treatment where supported.
- Use Tauri capabilities as an allowlist. v1 exposes no filesystem, shell,
  network, secret, database, or financial commands.
- Tray, auto-update, sidecars, floating companion windows, and persistent
  settings are deferred until a product requirement justifies them.
- Production distribution will require platform signing/notarization; a local
  unsigned build is a development artifact only.

### UI state boundary

- Route, theme, drawer, filter, and demo-form state stay local to React.
- No global state library is introduced because there is no shared remote or
  streaming state in this milestone.
- Deterministic fixtures approximate the existing `EvidenceRecord` names and
  preserve explicit `demo` / `synthetic` provenance; they never call or alter
  Python financial code.

### Motion and performance policy

- Motion is limited to opacity, translation, layout indicators, and the Orb's
  low-amplitude transform/opacity effects.
- `prefers-reduced-motion` removes ambient loops and reduces transitions to
  short fades. Financial meaning never depends on motion.
- Large blur regions are static. Pointer spotlights are local and
  `pointer-events: none`; they are not attached to every card.
- Charts initialize once, resize through `ResizeObserver`, update in place, and
  dispose on unmount. Tooltip and axis text remain sharp and unblurred.

### Accessibility policy

- Controls use mature primitives with keyboard focus, escape handling, labelled
  dialogs, tab semantics, tooltips and visible focus rings.
- Hover presentation always has a keyboard or persistent-text equivalent.
- Positive/negative values include wording or signs; color is supplementary.
- Decorative reflection and Orb layers are hidden from assistive technology;
  the Orb's current state has an accessible text label.

## License and provenance policy

No source file or brand asset from the five cloned reference repositories is
copied into this implementation. The clones are research material only. Runtime
packages are installed from their official package registries and their licenses
are documented with the desktop dependency set. If a future change copies a
substantial MIT- or Apache-licensed implementation, its notice and source commit
must be recorded in the repository at that time.
