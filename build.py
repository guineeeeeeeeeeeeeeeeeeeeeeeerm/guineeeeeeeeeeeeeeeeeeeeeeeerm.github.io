#!/usr/bin/env python3
"""Build the site by delegating to the package entry point."""

from sitegen.output import main


if __name__ == "__main__":
    raise SystemExit(main())
