from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Project:
    root: Path
    config: dict[str, Any]

    @property
    def slug(self) -> str:
        return str(self.config.get("slug") or self.root.name)

    @property
    def tts_base_url(self) -> str:
        return str(self.config.get("tts", {}).get("base_url", "http://localhost:50021"))

    @property
    def tts_speaker(self) -> int:
        return int(self.config.get("tts", {}).get("speaker", 1))

    def path(self, *parts: str) -> Path:
        return self.root.joinpath(*parts)


def load_project(project_dir: Path) -> Project:
    project_dir = project_dir.resolve()
    config_path = project_dir / "project.json"
    if not config_path.exists():
        raise FileNotFoundError(f"project.json not found: {config_path}")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    return Project(root=project_dir, config=config)

