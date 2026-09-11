# Decision preparation: allocation comparison

## References studied

- Portfolio Performance `TaxonomyDonutBrowser.java`: classification colours, selection opening holding detail, explicit unclassified categories. Architecture ideas only; no Java, assets or manual text copied. Project EPL-1.0; documentation CC BY-NC-SA. https://help.portfolio-performance.info/en/reference/view/taxonomies/
- Apache ECharts doughnut documentation and local `test/pie-animation.html` (Apache-2.0): concentric radii, item interaction and animation. Uses the already installed ECharts, no new dependency. https://echarts.apache.org/handbook/en/how-to/chart-types/pie/doughnut/

## Data boundary

The existing pretrade replay exposes final cash and each security's marked asset value. `AllocationComponent` projects those values and the existing HHI builder's `weight_components`. Account weights have the same total-account denominator as the existing target-symbol weight. Security weights are copied from HHI, excluding cash. No accounting, price inference or HHI formula is added.

The two rings use identical identities/colours. Clicking either ring or its keyboard-accessible legend selects the same holding in both. Missing before/after holdings have no slice, not a fabricated market observation. Missing allocation metadata from an older runtime produces an unavailable state, not inferred weights.

This is direct-holding allocation, **not completed fund look-through**. No source for dated fund constituents or industry classification is currently connected. No sector names, constituent weights, overlap percentages or coverage score are fabricated. A true underlying-exposure layer remains a separate data integration, not a frontend calculation.

## Runtime scope

The existing narrow pretrade bridge still accepts only its fixed synthetic subject. The page identifies it as an independent example account. Browser mode displays only the generated fixed scenario; changed inputs require the desktop runtime. Original executions, financial methods, evidence contracts and Agent policies are unchanged.
