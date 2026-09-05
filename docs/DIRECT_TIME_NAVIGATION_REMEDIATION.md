# Direct Time Navigation remediation

## Sources actually inspected

- Installed ECharts 6.1.0 `coord/cartesian/Grid.js`: an `xAxisIndex` finder accepts a scalar pixel coordinate; the former `[x, y]` argument produces `NaN`.
- [ECharts #21588](https://github.com/apache/echarts/pull/21588): native wheel axes and non-matching gesture passthrough. Read the proposed source diff; no unpublished API is used.
- [ECharts #17286](https://github.com/apache/echarts/issues/17286): Mac trackpad pan/zoom separation.
- [ECharts #21655](https://github.com/apache/echarts/pull/21655): separate movement and actual pinch scale, capture boundaries. Read the proposed source diff; no dependency upgrade.
- [zrender #1162](https://github.com/ecomfe/zrender/pull/1162): native delta fields and deltaMode; no node_modules patch.
- [Lightweight Charts chart-widget.ts](https://github.com/tradingview/lightweight-charts/blob/master/src/gui/chart-widget.ts): production wheel normalization, independent horizontal scroll and pointer-anchored zoom. No sensitivity constants or chart implementation copied.

## Corrected implementation

One shared visible-domain store owns both charts. ECharts renders the data and supplies coordinate conversion; `connect()` does not also propagate dataZoom. Horizontal pans preserve the selected span, including edge clamping. Valid continuous bounds are not snapped to observation dates. A pan into a sparse gap that cannot retain five observations is rejected rather than resized. Five observations remain a presentation policy.

Ctrl/meta wheel and native gesture scale zoom around the pointer. Native gesture events suppress duplicate modified-wheel zoom. Ordinary vertical wheel is left to page scrolling. High-frequency pan and zoom update logical bounds immediately but dispatch at most once per animation frame. Mouse drag and slider remain available; keyboard arrows, +/- and Home provide additional accessible controls. Pending frames are cancelled on teardown/store replacement.

Full bounds cover real daily observations, canonical execution timestamps and the authoritative as-of position-state endpoint. Those extra boundaries are not market observations. Cost/quantity endpoints are copied from replay state; prices are not filled, sampled or interpolated. Axis labels are pure calendar formatters rather than stateful last-label caches.

## Automated evidence

`timeNavigationIntegration.test.mjs` uses the installed real ECharts renderer/coordinate system, not a mocked pixel conversion: noncentral anchor position, shared dataZoom dispatch, intraday endpoint inclusion, bounded RAF updates and generated Open snapshot equality. Pure-domain tests cover span preservation, left/centre/right anchors, calendar labels, minimum observations and reset. Adapter tests reject mismatched path-state values and missing references. Serialized payload measurement includes arrays, not the size of object keys.

These tests do **not** certify physical Mac trackpad behaviour or WKWebView event delivery. See the final remediation report for actual product QA and explicit UNVERIFIED items.
