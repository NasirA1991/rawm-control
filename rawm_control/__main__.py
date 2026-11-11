"""Headless-safe source-tree entry point.

CLI commands must work without importing GTK so `python3 -m rawm_control
status` behaves like `rawmctl` on a server or over SSH.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    from . import cli, config

    argv = list(sys.argv if argv is None else argv)
    args = argv[1:]
    if args and args[0] == "--cli":
        return cli.run(args[1:])
    if args and args[0] in cli.CLI_COMMANDS:
        return cli.run(args)
    if args and args[0] in ("--version", "-V"):
        print(f"rawm-control {config.VERSION}")
        return 0
    if args and args[0] in ("help", "-h", "--help"):
        cli.build_parser().print_help()
        return 0
    if args and not args[0].startswith("-"):
        print(f"rawm-control: unknown command {args[0]!r}", file=sys.stderr)
        print("Try 'rawm-control --help' or 'rawmctl --help'.", file=sys.stderr)
        return 2

    from .app import main as app_main

    return app_main(argv)


if __name__ == "__main__":
    sys.exit(main())
