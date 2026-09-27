"""Allow running the toolkit with ``python -m helpdesk_toolkit``."""

from helpdesk_toolkit.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
