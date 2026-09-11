# Vendored execution core

Source: https://github.com/ZhuLinsen/daily_stock_analysis
Revision: 089d9d26d68f8b839ea5a74a3784e4402925f8b7
License: MIT (see LICENSE).

Copied: src/agent/runner.py, tools/registry.py, tools/execution.py,
stream_events.py. Extracted StageFailureReason from protocols.py.

Local patches: package-relative imports; adapter/scope annotations are structural;
removed unused dashboard parsing/JSON repair helpers and DSA database telemetry.
No upstream financial signals, pricing, stock research, credentials, provider
fallbacks, or dashboard renderer are enabled. Stock normalization's lazy upstream
imports are not used by Toujing tools (which have no stock_code parameter).

The runner and tool deadline/cache/order behavior are upstream code. Toujing's
Responses transport, receipt audit, account scope, and final validation are adapters.
Do not modify this directory without recording the upstream/local difference.

Original upstream SHA-256:

- runner.py: a08ae57bd451bbdeacb659dfd8c63f855076d8bda4f43d47828f53d84fcbd98a
- tools/registry.py: df2f9342f82ea4d925ada5102634959abda82d6b4866ede2503f65ba4645479f
- tools/execution.py: d0d711f2521818f19771d07b0ca9b73b2b3f30dfc62bfbd349970edf8ac3331e
- stream_events.py: 5ccdb3e34fda770e3090e929c63000f069b6042b11ac34a8f65fea6f9cc6a95d
