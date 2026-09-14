"""review_pack.v1 — deterministic post-trade review pack for one account.

Public entry point::

    from src.review_pack import build_review_pack

    pack = build_review_pack(repo, subject_id, account_id)

The pack is a pure dict in the fixed ``review_pack.v1`` schema.  All financial
values are computed deterministically from canonical facts in the repository;
every section documents its limitations; insufficient evidence yields null or
empty sections, never a score; only observable facts are described.
"""

from src.review_pack.builder import SCHEMA_VERSION, build_review_pack

__all__ = ["SCHEMA_VERSION", "build_review_pack"]
