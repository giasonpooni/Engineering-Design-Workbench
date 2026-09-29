"""Enable python -m tbrt with the same boundary as the installed command."""
from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
