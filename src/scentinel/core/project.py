"""`.scentinel` project files: JSON round-trip of geometry, scenario, sensors."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from scentinel.core.geometry import BinGeometry
from scentinel.core.scenario import Scenario

FORMAT_VERSION = 1
SUFFIX = ".scentinel"
FILE_FILTER = f"Scentinel project (*{SUFFIX});;All files (*)"


@dataclass
class Sensor:
    """A candidate sensor inlet position in bin coordinates (metres)."""

    sensor_id: str
    x: float
    y: float


@dataclass
class Project:
    """Everything the app needs to reproduce a run."""

    name: str = "Untitled"
    geometry: BinGeometry = field(default_factory=BinGeometry)
    scenario: Scenario = field(default_factory=Scenario)
    sensors: list[Sensor] = field(default_factory=list)


def save_project(project: Project, path: Path) -> None:
    payload = {
        "format_version": FORMAT_VERSION,
        "name": project.name,
        "geometry": asdict(project.geometry),
        "scenario": asdict(project.scenario),
        "sensors": [asdict(sensor) for sensor in project.sensors],
    }
    Path(path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_project(path: Path) -> Project:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    version = payload.get("format_version")
    if version != FORMAT_VERSION:
        raise ValueError(
            f"unsupported project format_version {version!r}, expected {FORMAT_VERSION}"
        )
    return Project(
        name=payload["name"],
        geometry=BinGeometry(**payload["geometry"]),
        scenario=Scenario(**payload["scenario"]),
        sensors=[Sensor(**sensor) for sensor in payload["sensors"]],
    )
