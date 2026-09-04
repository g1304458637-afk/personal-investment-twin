"""Run the persistent Toujing core runtime over newline-delimited JSON."""

import argparse

from .protocol import run


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path")
    args = parser.parse_args()
    return run(db_path=args.db_path)


if __name__ == "__main__":
    raise SystemExit(main())
