# Unified product showcase v1

## Product purpose

One fictional investment account supplies the normal example experience across Investments, Episode review, Self vs Past, same-stock comparison, allocation/look-through, pre-trade checks, and the existing Agent context. It replaces disconnected presentation examples, not regression fixtures.

The architectural reference is Portfolio Performance's [sample portfolio onboarding](https://help.portfolio-performance.info/en/reference/help/welcome/) and its [performance walkthrough](https://help.portfolio-performance.info/en/getting-started/measure-performance/): reuse a complete portfolio throughout different views. No implementation or visual assets were copied.

## Authoritative inputs

- Source: `src/demo/showcase.py`, version `toujing_showcase_v1`.
- Main subject/account: `SYN_STUDY_SHOWCASE`; opening cash CNY 100,000.
- Period: 2025-01-02 through 2025-12-31; 20 canonical executions, each with a CNY 5 recorded fee.
- Three fictional held instruments: 辰光科技 (growth stock), 远川制造 (industrial stock), 均衡组合基金 (fund).
- 260 explicitly synthetic weekday observations. This is **not an actual exchange calendar**. OHLC, volume, prices, names and trades are all simulated. No actual stock quotes are joined to fictional executions.
- Daily bars and replay share the same closes; execution prices lie within their corresponding bars. Amount/turnover is not invented from volume.
- Synthetic market and industry benchmarks support existing comparison/Selection contracts. Selection's frozen CSI300 provider slot receives a clearly named simulated benchmark; it is not real CSI300 data.
- The dated synthetic fund disclosure is 40% growth stock, 35% industrial stock, 25% other industrial holdings. Existing look-through code derives exposure from that disclosure.

## Investment story and independently checked amounts

| Episode | Period | State at year-end | Existing-engine result (CNY) |
| --- | --- | --- | ---: |
| 远川制造, first investment | Jan 2–Jun 13 | Closed | +3,980 |
| 辰光科技, first investment | Jan 13–Jun 6 | Closed | −630 |
| 均衡组合基金 | Jan 2–Dec 31 | Open, 2,900 units | +5,810 marked total |
| 辰光科技, second investment | Jul 11–Dec 31 | Open, 900 shares | +3,880 marked total |
| 远川制造, second investment | Aug 1–Dec 31 | Open, 300 shares | +1,290 marked total |

The first growth episode is the default review: entry, two additions, two reductions, and full exit. Its ledger is CNY 11,640 sale proceeds minus 12,240 purchase outlay minus 30 fees = −630. The first industrial episode is 20,200 − 16,200 − 20 = +3,980. These inputs were chosen to illustrate different recorded paths, not to establish a psychological diagnosis or a superior strategy.

At year-end: cash 58,170; fund value 34,800; growth holding 12,960; industrial holding 8,400; total portfolio value **114,330**. Open-episode amounts include the remaining position valued at the dated market mark; they are not final realized proceeds.

The registered pre-trade example buys 300 growth shares at CNY 14.40, with CNY 5 fees: cash 58,170 → 53,845; quantity 900 → 1,200; portfolio value 114,330 → 114,325. Existing replay and concentration builders generate the weights and HHI; the UI does not calculate an alternative portfolio.

## Feature coverage

| Surface | Shared inputs and output |
| --- | --- |
| Investments / Episode | Five episodes, complete simulated K-line/volume data, cost and quantity paths, exact execution markers, open versus closed results |
| Review | Existing deterministic Path/Outcome and registered historical comparisons; first growth episode has consecutive additions and reductions |
| Behavior / Twin | Existing eight Evidence builders, real dates, rebuildable HHI/turnover history; early insufficient history remains insufficient |
| Self vs Past | Two periods of the same full account, not different dummy accounts |
| Same-stock | First growth episode versus the same period of the registered reference account |
| Full-account comparison | Full main/reference accounts using the same market, benchmark and period contracts |
| Pre-trade / allocation | Main year-end holdings, cash and fund composition; one explicit hypothetical order |
| Agent | Every main Episode resolves to its own canonical records; paired analysis binds both account sources. Existing consent, model configuration, receipt audit and claim validation remain required |

The second subject, `SYN_STUDY_SHOWCASE_REFERENCE`, is a supporting **simulated reference**, not another example-account selector or a verified professional. Its first growth episode result is +525; the main account's corresponding result is −630. Both explicitly enter on Jan 13 at 10:02 and exit on Jun 6 at 10:10; the two source schedules therefore support the full same-stock observation window without truncating either exit. It is not optimized, ranked, or presented as a strategy to copy. No 72-account historical peer distribution is manufactured for this year-long dataset; pre-trade peer context is absent.

## Rebuild and boundaries

Run `.venv/bin/python scripts/export_showcase_demo.py` from the repository root. This generates `apps/desktop/src/generated/showcase-demo.json` as one deterministic artifact. `src/demo/showcase_comparison.py` and `src/demo/showcase_runtime.py` bind these inputs to existing engines. All payloads retain `synthetic` data tier and source identity.

Normal frontend imports no longer assemble `backend-demo-evidence.json`, `comparison-research-demo.json`, or `standard-chart-demo.json`. Their source builders, files and specialized fixtures remain for regression/QA and historical reproducibility; removing them is not necessary to remove the extra product examples.

This dataset does not claim real broker integration, actual professional account authorization, real exchange holidays, live market availability, predictive investment advice, or pre-generated model answers. Browser mode stays explicitly offline/demo; live Agent runs require the configured desktop runtime and consent. No live external model call is part of this showcase-data verification.

## Verification

`tests/test_showcase_demo.py`, `tests/test_showcase_runtime.py`, `tests/test_showcase_comparison.py`, and Desktop `showcaseDemo.test.mjs` cover deterministic source/export, independent ledger amounts, account isolation, paired source invalidation, matching OHLCV/replay prices, all five Episode mappings, and shared comparison/pre-trade amounts. Existing financial and legacy fixture regressions remain in place.
