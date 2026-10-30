"""Console-script entry point for ``fastn``.

The CLI needs the optional ``[cli]`` extra (click, rich). Without it, print how
to install it instead of failing with a ModuleNotFoundError traceback.
"""
from __future__ import annotations

import sys


def main() -> None:
    try:
        from fastn.cli import main as cli_main
    except ModuleNotFoundError as exc:
        if exc.name in ("click", "rich"):
            sys.stderr.write(
                "The fastn CLI needs the [cli] extra. Install it with:\n\n"
                '    pip install "fastn-ai[cli]"\n'
            )
            sys.exit(1)
        raise
    cli_main()
