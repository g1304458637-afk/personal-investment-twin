"""Python-owned local persistence for canonical user facts."""

from .repository import LocalRepository, RepositoryError

__all__ = ["LocalRepository", "RepositoryError"]
