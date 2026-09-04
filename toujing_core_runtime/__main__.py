"""Run the persistent Toujing core runtime over newline-delimited JSON."""

from .protocol import run


if __name__ == "__main__":
    raise SystemExit(run())
