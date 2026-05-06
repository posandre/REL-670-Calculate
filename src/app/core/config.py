from __future__ import annotations

from pathlib import Path


APP_NAME = "REL-PSD"
DEFAULT_LANGUAGE = "uk"
PROJECT_SCHEMA_VERSION = 1
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
RESOURCES_ROOT = PACKAGE_ROOT.parent.parent / "resources"
LOCALIZATION_ROOT = PACKAGE_ROOT / "localization" / "translations"
