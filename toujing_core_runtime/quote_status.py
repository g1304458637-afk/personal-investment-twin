"""Offline readiness probe for the narrow AKShare quote surface.

This module deliberately has no dependency on the Agent or financial-analysis
runtime.  The probe imports the exact AKShare entry points used by public
research, which is a stronger and more truthful check than package discovery
while still making no provider request.
"""

from __future__ import annotations

import os


def quotes_status() -> dict[str, object]:
    """Report whether the bundled quote entry points can be imported offline."""

    try:
        from akshare.stock.stock_info import stock_info_a_code_name  # noqa: F401
        from akshare.stock_feature.stock_hist_em import stock_zh_a_hist  # noqa: F401
    except Exception as exc:
        payload: dict[str, object] = {
            "available": False,
            "provider": "akshare",
            "license": "MIT",
            "disclaimer": "research_background_not_sla",
            "reason": type(exc).__name__,
        }
        missing = getattr(exc, "filename", None) or getattr(exc, "name", None)
        if isinstance(missing, str) and missing.isascii() and 1 <= len(missing) <= 240:
            payload["missing"] = os.path.basename(missing)[:80]
        return payload
    return {
        "available": True,
        "provider": "akshare",
        "license": "MIT",
        "disclaimer": "research_background_not_sla",
    }
