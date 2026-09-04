"""PyInstaller entry point for the Toujing persistent core runtime."""

from toujing_core_runtime.protocol import run


if __name__ == "__main__":
    raise SystemExit(run())
