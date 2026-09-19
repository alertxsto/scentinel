"""`.scentinel` project files: JSON round-trip of geometry, scenario, sensors."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from scentinel.core.geometry import BinGeometry
from scentinel.core.scenario import Scenario
from scentinel.core.virtual_sensor import VirtualSensorConfig

FORMAT_VERSION = 2
#: Version 1 files predate the bin width. They load by taking the default,
#: because the width only scales the emission flux and every other field is
#: unchanged; refusing them would discard working projects for no data reason.
_MIGRATABLE_VERSIONS = (1,)
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
    sensor_lab: VirtualSensorConfig = field(default_factory=VirtualSensorConfig)


def save_project(project: Project, path: Path) -> None:
    payload = {
        "format_version": FORMAT_VERSION,
        "name": project.name,
        "geometry": asdict(project.geometry),
        "scenario": asdict(project.scenario),
        "sensors": [asdict(sensor) for sensor in project.sensors],
        "sensor_lab": asdict(project.sensor_lab),
    }
    Path(path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_project(path: Path) -> Project:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    version = payload.get("format_version")
    if version != FORMAT_VERSION and version not in _MIGRATABLE_VERSIONS:
        raise ValueError(
            f"unsupported project format_version {version!r}, expected {FORMAT_VERSION}"
        )
    return Project(
        name=payload["name"],
        geometry=_load_geometry(payload["geometry"]),
        scenario=_load_scenario(payload["scenario"]),
        sensors=[Sensor(**sensor) for sensor in payload["sensors"]],
        sensor_lab=_load_sensor_lab(payload.get("sensor_lab")),
    )


def _load_geometry(payload: dict) -> BinGeometry:
    """Geometry, tolerant of a v1 file that has no ``width_m``."""
    allowed = {item.name for item in fields(BinGeometry)}
    return BinGeometry(**{key: value for key, value in payload.items() if key in allowed})


def _load_scenario(payload: dict) -> Scenario:
    allowed = {item.name for item in fields(Scenario)}
    return Scenario(**{key: value for key, value in payload.items() if key in allowed})


def _load_sensor_lab(payload: object) -> VirtualSensorConfig:
    if not isinstance(payload, dict):
        return VirtualSensorConfig()
    allowed = {item.name for item in fields(VirtualSensorConfig)}
    return VirtualSensorConfig(**{key: payload[key] for key in allowed if key in payload})
