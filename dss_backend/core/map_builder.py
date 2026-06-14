from datetime import datetime
from typing import Any

from dss_backend.core.state_manager import seconds_since


MARKERS_BY_DOMAIN = {
    "air": "uav",
    "surface": "usv",
    "subsurface": "uuv",
}


def _vehicle_label(vehicle_id: str) -> str:
    return vehicle_id.replace("_", " ").upper()


def _color_status(vehicle: dict[str, Any]) -> str:
    link_status = (vehicle.get("link") or {}).get("status")
    battery = vehicle.get("battery") or {}
    battery_percentage = battery.get("percentage")
    bingo_threshold = battery.get("bingo_threshold")

    if vehicle.get("status") == "fault":
        return "red"
    if battery_percentage is not None and bingo_threshold is not None:
        if battery_percentage <= bingo_threshold:
            return "low_battery"
    if link_status == "lost_link":
        return "red"
    if link_status == "unstable":
        return "orange"
    if link_status == "degraded":
        return "yellow"
    if link_status == "expected_blackout":
        return "blue"
    if link_status == "late_contact":
        return "orange"
    return "green" if link_status == "online" else "gray"


def _vehicle_marker(vehicle: dict[str, Any]) -> dict[str, Any] | None:
    position = vehicle.get("position")
    if not position:
        return None

    velocity = vehicle.get("velocity") or {}
    battery = vehicle.get("battery") or {}
    link = vehicle.get("link") or {}
    domain = vehicle.get("domain")
    vehicle_id = vehicle["vehicle_id"]
    raw = vehicle.get("raw") or {}  # full raw dict including sim uncertainty fields

    return {
        "id": vehicle_id,
        "type": "vehicle",
        "domain": domain,
        "marker": MARKERS_BY_DOMAIN.get(domain, "vehicle"),
        "position": position,
        "heading_deg": velocity.get("heading_deg"),
        "status": vehicle.get("status"),
        "link_status": link.get("status"),
        "battery_percentage": battery.get("percentage"),
        "current_task_id": vehicle.get("current_task_id"),
        "display": {
            "label": _vehicle_label(vehicle_id),
            "color_status": _color_status(vehicle),
        },
        # Simulation uncertainty cone (rendered as ellipse in the UI)
        "sigma_m": raw.get("sigma_m") or 0,
        "sigma_along_m": raw.get("sigma_along_m"),
        "sigma_cross_m": raw.get("sigma_cross_m"),
        "uncertainty_heading_deg": raw.get("uncertainty_heading_deg"),
        "in_blackout": link.get("in_blackout", False),
        "submerged": raw.get("submerged", False),
        "rtb": raw.get("rtb", False),
        "waypoint": raw.get("waypoint"),
        "age_sec": raw.get("age_sec", 0),
    }


def _event_marker(event: dict[str, Any]) -> dict[str, Any] | None:
    position = event.get("position")
    if not position:
        return None

    return {
        "id": event.get("event_id"),
        "type": "event",
        "event_kind": event.get("event_kind"),
        "severity": event.get("severity"),
        "vehicle_id": event.get("vehicle_id"),
        "domain": event.get("domain"),
        "position": position,
        "description": event.get("description"),
        "created_by": event.get("created_by", "vehicle"),
    }


def _contact_marker(contact: dict[str, Any]) -> dict[str, Any] | None:
    lat = contact.get("lat")
    lon = contact.get("lon")
    if lat is None or lon is None:
        return None
    return {
        "id": contact.get("id", "unknown"),
        "type": "contact",
        "position": {"lat": lat, "lon": lon},
        "heading": contact.get("heading", 0),
        "speed_knots": contact.get("speed_knots", 0),
        "behavior": contact.get("behavior", "unknown"),
        "ais": contact.get("ais", True),
        "detected_ts": contact.get("detected_ts"),
    }


def _ais_vessel(vessel: dict[str, Any]) -> dict[str, Any] | None:
    lat = vessel.get("lat")
    lon = vessel.get("lon")
    if lat is None or lon is None:
        return None
    return {
        "mmsi": vessel.get("mmsi"),
        "name": vessel.get("name", ""),
        "position": {"lat": lat, "lon": lon},
        "heading": vessel.get("heading", 0),
        "sog_knots": vessel.get("sog_knots", 0),
    }


def _uncertainty_region(vehicle: dict[str, Any], now: datetime) -> dict[str, Any] | None:
    position = vehicle.get("position")
    if not position:
        return None

    link_status = (vehicle.get("link") or {}).get("status")
    freshness = vehicle.get("telemetry_freshness") or {}
    raw = vehicle.get("raw") or {}
    sigma_m = raw.get("sigma_m") or 0

    should_show = (
        link_status in {"lost_link", "late_contact", "expected_blackout"}
        or freshness.get("status") == "very_stale"
        or sigma_m > 300
    )
    if not should_show:
        return None

    domain = vehicle.get("domain")
    vehicle_id = vehicle["vehicle_id"]
    velocity = vehicle.get("velocity") or {}
    speed = velocity.get("speed_mps")
    age = freshness.get("seconds_since_last_telemetry")
    if age is None:
        age = seconds_since(freshness.get("last_telemetry_received_at"), now) or 0

    if sigma_m > 0:
        radius = sigma_m
    elif speed is None:
        radius = 500 if domain == "subsurface" else 100
    else:
        radius = speed * age
        if domain == "subsurface":
            radius = max(100, radius)

    return {
        "id": f"uncertainty_{vehicle_id}",
        "type": "uncertainty",
        "vehicle_id": vehicle_id,
        "domain": domain,
        "center": position,
        "radius_m": min(10000, round(radius, 1)),
        "sigma_along_m": raw.get("sigma_along_m"),
        "sigma_cross_m": raw.get("sigma_cross_m"),
        "uncertainty_heading_deg": raw.get("uncertainty_heading_deg"),
        "reason": link_status if link_status in {"lost_link", "late_contact", "expected_blackout"} else "very_stale_telemetry",
    }


def build_map_state(
    normalized_vehicles: dict[str, dict[str, Any]],
    active_events: list[dict[str, Any]],
    now: datetime,
) -> dict[str, Any]:
    from dss_backend.state import sim_raw  # late import avoids circular at module load

    vehicle_markers = [
        m for m in (_vehicle_marker(v) for v in normalized_vehicles.values()) if m
    ]
    event_markers = [m for m in (_event_marker(e) for e in active_events) if m]
    uncertainty_regions = [
        r for r in (_uncertainty_region(v, now) for v in normalized_vehicles.values()) if r
    ]
    contacts = [m for m in (_contact_marker(c) for c in sim_raw.get("contacts", [])) if m]
    ais = [m for m in (_ais_vessel(v) for v in sim_raw.get("ais", [])) if m]

    return {
        "vehicles": vehicle_markers,
        "events": event_markers,
        "contacts": contacts,
        "ais": ais,
        "zones": [],
        "uncertainty_regions": uncertainty_regions,
    }
