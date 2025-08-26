from pathlib import Path

# Assets directory is placed at src/assets in the repository layout.
# Compute it relative to the project `src` directory so both editable installs
# and running from source work.
ASSETS_DIR = Path(__file__).parent.parent / "assets"

__all__ = ["ASSETS_DIR"]
