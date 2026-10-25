"""Run the same native smoke check used by packaged desktop-check builds."""

from videoflow.desktop.smoke import main

if __name__ == "__main__":
    raise SystemExit(main())
