"""Subcommand router for the public workspace tools.

Enables ``python -m prompt2serviceflow.experiments.submission_cli validate ...``
and ``... compile ...`` when the console entry points are not on PATH (the
``bin/`` wrappers inside workspaces try the entry points first).
"""

from __future__ import annotations

import sys

from prompt2serviceflow.experiments.submission import compile_main, validate_main


def main() -> int:
    argv = sys.argv[1:]
    if not argv or argv[0] not in {"validate", "compile"}:
        print("usage: python -m prompt2serviceflow.experiments.submission_cli {validate|compile} ...",
              file=sys.stderr)
        return 2
    command, rest = argv[0], argv[1:]
    if command == "validate":
        return validate_main(rest)
    return compile_main(rest)


if __name__ == "__main__":
    raise SystemExit(main())
