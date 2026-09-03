# 投镜 Desktop Design System v1

## 1. Visual language

**Mirror Glass / Reflective Intelligence** combines calm financial precision
with a restrained sense of spatial depth. Reflection and motion signal that the
system is observing and clarifying evidence; they do not decorate or reinterpret
the evidence itself.

- Data is sharp, stable and aligned to tabular numerals.
- Spectacle belongs to transitions, glass highlights, ambient light and the
  Mirror Orb.
- Cyan-white reflection is the signature accent. It is not a generic neon
  palette and never fills the entire application.
- Surfaces are composed in a few spatial layers rather than nested rounded cards.
- Dark mode is the flagship expression. Light mode retains the same hierarchy,
  contrast and semantic color behavior.

## 2. Surface hierarchy

| Layer | Purpose | Dark treatment | Light treatment |
| --- | --- | --- | --- |
| App background | Spatial canvas and quiet atmosphere | `#090c13` with fixed, low-opacity radial reflections | `#eef2f4` with cool pearl reflections |
| Navigation surface | Persistent orientation | 72% dark glass, 24px blur, edge highlight | 72% white glass, 24px blur, cool edge |
| Primary glass | Main analytical section | 5–7% white overlay, 18px blur, 1px highlight | 66–74% white overlay, 18px blur |
| Floating glass | Ask Twin, command, important transient surface | 8–10% white overlay, 24px blur, deeper shadow | 82–90% white overlay, 24px blur |
| Elevated overlay | Sheet, drawer and dialog | 92% dark neutral, 30px blur, scrim | 95% white, 30px blur, scrim |
| Tooltip/popover | Short readable help | 96% dark neutral, no decorative glow | 98% white, crisp border |

Blur is never applied to the text or chart layer. If a platform cannot support
`backdrop-filter`, each glass token has an opaque background fallback.

## 3. Typography

The stack is the native system sans-serif (`-apple-system` first on macOS) and
the native UI monospace for technical identifiers. No remote font request is
required.

| Token | Size / line height | Weight | Use |
| --- | --- | --- | --- |
| Display | 34 / 40 | 560 | One short flagship statement |
| Page title | 27 / 34 | 560 | Route title |
| Section title | 15 / 22 | 560 | Analytical section label |
| Metric number | 26 / 32 | 580 | Primary financial or evidence value |
| Body | 14 / 21 | 420 | Explanatory copy |
| Caption | 12 / 18 | 450 | Labels and supporting context |
| Metadata | 11 / 16 | 520 | Status, method, date and provenance |
| Mono | 11 / 17 | 450 | Evidence IDs, versions and code lineage |

Numbers use `font-variant-numeric: tabular-nums`. Uppercase is reserved for
short metadata labels and uses increased letter spacing; sentences remain in
normal case.

## 4. Spacing system

The base unit is 4px. Components and pages use only the following tokens:

| Token | Value | Typical use |
| --- | ---: | --- |
| `space-1` | 4px | icon/detail gap |
| `space-2` | 8px | compact control gap |
| `space-3` | 12px | row/content gap |
| `space-4` | 16px | component padding |
| `space-5` | 20px | dense section padding |
| `space-6` | 24px | standard section padding |
| `space-8` | 32px | page rhythm |
| `space-10` | 40px | major group separation |
| `space-12` | 48px | hero separation |
| `space-16` | 64px | rare display spacing |

Desktop page padding is 28px at 1440×900 and 22px at 1280×800. The main
workspace scrolls; navigation and the top context bar remain stable.

## 5. Radius system

| Token | Value | Use |
| --- | ---: | --- |
| `radius-sm` | 6px | tags, inputs, small controls |
| `radius-md` | 10px | rows, popovers, compact groups |
| `radius-lg` | 14px | primary analytical surfaces |
| `radius-xl` | 20px | floating overlays and one hero surface |
| Pill | 999px | statuses and segmented controls only |

Large radius is not the default. Adjacent facts share one surface with dividers
instead of each becoming a separate card.

## 6. Glass system

Every glass surface is composed from the same five parts:

1. **Transparency:** enough canvas is visible to create depth, never enough to
   compromise body-text contrast.
2. **Backdrop:** static blur plus mild saturation; blur values do not animate.
3. **Border highlight:** a 1px cool-white edge, brighter on the top/left to imply
   reflection.
4. **Shadow:** wide, low-opacity depth shadow; floating surfaces add a short
   contact shadow.
5. **Reflection/noise:** a non-interactive highlight pseudo-element and a global
   sub-2% monochrome noise texture prevent flat gradients.

Only the Mirror Orb and primary Ask Twin entry receive an animated highlight.
Evidence rows, numeric labels and charts remain free of glow.

## 7. Motion system

| Token | Duration | Use |
| --- | ---: | --- |
| Fast interaction | 120ms | focus, press, tooltip opacity |
| Standard transition | 220ms | route indicator, row hover, tabs |
| Panel transition | 320ms | sheet, drawer, route content |
| Chart entrance | 520ms | first deterministic chart reveal |
| Slow ambient | 12–18s | background reflection and Orb only |

The standard curve is `cubic-bezier(0.22, 1, 0.36, 1)`. Springs use zero or
near-zero bounce. Hover displacement is at most 2px and scale at most 1.018.
There is no blanket `scale(1.05)`, repeated bounce, or blur animation. A page
transition is opacity plus no more than 8px translation.

`prefers-reduced-motion: reduce` removes ambient loops, number interpolation and
layout travel; content appears through a short opacity change or immediately.

## 8. Financial semantics and accessibility

- Positive uses a restrained mint and explicit `+`, `outperformed`, or
  equivalent text.
- Negative uses coral and explicit `−`, `underperformed`, or equivalent text.
- Neutral/unknown uses foreground or muted text. `insufficient_evidence` is not
  styled as failure; it is an evidence boundary.
- Color is never the only carrier of status. Every status has text and, where
  useful, a shape/icon.
- Focus rings are always visible for keyboard input. Dialogs, sheets, tabs,
  tooltips, dropdowns and command surfaces use mature accessible primitives.
- Decorative lighting is `aria-hidden`; chart containers and Orb states receive
  accessible labels.
- Body text targets WCAG AA contrast against its final composited surface.

## 9. Chart principles

- Precision is more important than visual novelty.
- Every analytical chart uses deterministic fixture data, real axes, unit-aware
  tooltips, readable labels and an explicit Demo/Synthetic context.
- Grid lines are quiet but visible. Series use solid strokes with a restrained
  local shadow; no glowing area obscures values.
- Chart legends and tooltips identify the compared series. A line is never
  presented without its unit or period.
- ECharts is integrated through one lifecycle wrapper that initializes once,
  updates options, observes container resize and disposes on unmount.
- Future evidence drill-down is a separate interaction; chart geometry does not
  invent evidence or run financial calculations.

## 10. Demo-data rule

All v1 workspace values come from one versioned, deterministic TypeScript demo
fixture under `apps/desktop/src/demo/`.

- No `Math.random`, `Date.now`, faker, live market request or generated finance
  value is allowed.
- The fixed user is called **Demo User** and every page shows **Demo / Synthetic**.
- Peer data is called **Demo Cohort** and never described as a population average.
- Structures approximate the existing `EvidenceRecord` field names so the view
  can later consume an adapter without changing the Python contract.
- Empty, error, disconnected and insufficient-evidence examples are explicit UI
  fixtures, not fabricated fallbacks.
- Demo data must never be logged or described as a real account or real market
  history.
