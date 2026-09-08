# SPDX-License-Identifier: MIT
# Copyright (c) 2026 TeslaNeuro
"""Allow ``python -m plantos`` as well as the ``plantos`` console script."""

from plantos.cli import app


def main() -> None:
    app()


if __name__ == "__main__":
    main()
