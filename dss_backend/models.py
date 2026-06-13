from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Domain = Literal["air", "surface", "subsurface"]
MessageType = Literal["heartbeat", "telemetry", "event", "link_state"]
CommunicationMode = Literal["radio", "acoustic", "satellite", "cellular"]
VehicleStatus = Literal["active", "idle", "standby", "fault", "returning", "offline"]
SensorStatus = Literal["ok", "degraded", "fault", "unavailable"]
EventSeverity = Literal["low", "medium", "high", "critical"]
LinkStateStatus = Literal[
    "online",
    "degraded",
    "unstable",
    "lost_link",
    "expected_blackout",
    "late_contact",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Position(StrictModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    alt: float | None = None
    depth: float | None = Field(default=None, ge=0)


class Velocity(StrictModel):
    speed_mps: float = Field(ge=0)
    heading_deg: float = Field(ge=0, lt=360)


class Battery(StrictModel):
    percentage: float = Field(ge=0, le=100)
    bingo_threshold: float = Field(ge=0, le=100)


class Sensors(StrictModel):
    camera: SensorStatus
    radar: SensorStatus
    sonar: SensorStatus


class Capabilities(StrictModel):
    visual_isr: bool
    radar_scan: bool
    sonar_scan: bool
    relay_comms: bool


class ContactWindow(StrictModel):
    start: datetime
    end: datetime

    @field_validator("end")
    @classmethod
    def end_must_be_after_start(cls, value: datetime, info: Any) -> datetime:
        start = info.data.get("start")
        if start is not None and value <= start:
            raise ValueError("expected_next_contact_window.end must be after start")
        return value


class VehicleMessage(StrictModel):
    message_type: MessageType
    vehicle_id: str
    timestamp: datetime
    domain: Domain


class HeartbeatMessage(VehicleMessage):
    message_type: Literal["heartbeat"]
    sequence: int = Field(ge=0)
    communication_mode: CommunicationMode
    expected_interval_ms: int = Field(gt=0)

    @model_validator(mode="after")
    def expected_interval_must_match_domain(self) -> "HeartbeatMessage":
        expected_by_domain = {
            "air": 1000,
            "surface": 3000,
            "subsurface": 30000,
        }
        expected = expected_by_domain[self.domain]
        if self.expected_interval_ms != expected:
            raise ValueError(
                f"expected_interval_ms for {self.domain} must be {expected}"
            )
        return self


class TelemetryMessage(VehicleMessage):
    message_type: Literal["telemetry"]
    status: VehicleStatus
    position: Position
    velocity: Velocity
    battery: Battery
    sensors: Sensors
    capabilities: Capabilities
    current_task_id: str | None = None


class VehicleEventMessage(VehicleMessage):
    message_type: Literal["event"]
    event_id: str = Field(min_length=1)
    event_kind: str = Field(min_length=1)
    severity: EventSeverity
    position: Position | None = None
    description: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LinkStateMessage(VehicleMessage):
    message_type: Literal["link_state"]
    communication_mode: CommunicationMode
    status: LinkStateStatus
    last_contact_at: datetime | None = None
    expected_next_contact_window: ContactWindow | None = None

    @field_validator("expected_next_contact_window")
    @classmethod
    def blackout_requires_contact_window(
        cls, value: ContactWindow | None, info: Any
    ) -> ContactWindow | None:
        status = info.data.get("status")
        if status == "expected_blackout" and value is None:
            raise ValueError("expected_blackout requires expected_next_contact_window")
        return value


MESSAGE_MODELS: dict[str, type[VehicleMessage]] = {
    "heartbeat": HeartbeatMessage,
    "telemetry": TelemetryMessage,
    "event": VehicleEventMessage,
    "link_state": LinkStateMessage,
}


def validate_message(payload: dict[str, Any]) -> VehicleMessage:
    message_type = payload.get("message_type")
    if not isinstance(message_type, str):
        raise ValueError("Invalid message_type")

    model = MESSAGE_MODELS.get(message_type)
    if model is None:
        raise ValueError("Invalid message_type")
    return model.model_validate(payload)
