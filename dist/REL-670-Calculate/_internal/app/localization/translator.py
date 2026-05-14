from __future__ import annotations

import json
from pathlib import Path

from app.core.config import DEFAULT_LANGUAGE, LOCALIZATION_ROOT


class Translator:
    def __init__(self, language: str = DEFAULT_LANGUAGE, root: Path = LOCALIZATION_ROOT) -> None:
        self._root = root
        self._language = language
        self._messages = self._load(language)

    @property
    def language(self) -> str:
        return self._language

    def set_language(self, language: str) -> None:
        self._messages = self._load(language)
        self._language = language

    def text(self, key: str, **kwargs: object) -> str:
        template = self._messages.get(key, key)
        return template.format(**kwargs)

    def available_languages(self) -> list[str]:
        return sorted(path.stem for path in self._root.glob("*.json"))

    def _load(self, language: str) -> dict[str, str]:
        path = self._root / f"{language}.json"
        if not path.exists():
            path = self._root / f"{DEFAULT_LANGUAGE}.json"
        with path.open("r", encoding="utf-8") as file:
            raw = json.load(file)
        if not isinstance(raw, dict):
            msg = f"Localization file {path} must contain a JSON object."
            raise ValueError(msg)
        return {str(key): str(value) for key, value in raw.items()}
