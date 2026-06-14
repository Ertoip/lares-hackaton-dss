import React, { useEffect, useRef, useState } from 'react';
import { Circle, MapContainer, Marker, Polyline, Popup, TileLayer, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// ── Constants ─────────────────────────────────────────────────────────────────

const linkColors = {
  online:            '#f5f5f5',
  degraded:          '#d6d3d1',
  unstable:          '#a8a29e',
  lost_link:         '#ef4444',
  expected_blackout: '#78716c',
  late_contact:      '#f97316',
};

const statusColors = {
  green:       '#f5f5f5',
  low_battery: '#f97316',
  red:         '#ef4444',
  orange:      '#f97316',
  yellow:      '#eab308',
  blue:        '#38bdf8',
  gray:        '#a8a29e',
};

const severityColors = {
  low:      '#22c55e',
  medium:   '#eab308',
  high:     '#f97316',
  critical: '#ef4444',
};

const WP_COLOR = { checking: '#eab308', valid: '#22c55e', invalid: '#ef4444' };

// ── Map ref capture (exposes Leaflet map instance to parent) ──────────────────

function MapRefCapture({ mapRef }) {
  const map = useMap();
  useEffect(() => { mapRef.current = map; }, [map]);
  return null;
}

// ── Waypoint & mothership icons ───────────────────────────────────────────────

function makeWaypointIcon(status, label) {
  const color  = WP_COLOR[status] || '#a8a29e';
  const symbol = status === 'invalid'  ? '✕'
               : status === 'checking' ? '…'
               : '◎';
  return L.divIcon({
    className: '',
    html: `<div class="wp-pin" style="--wc:${color}">
             <span class="wp-sym">${symbol}</span>
             <span class="wp-lbl">${label}</span>
             <div class="wp-tail"></div>
           </div>`,
    iconSize:    [64, 36],
    iconAnchor:  [32, 42],
    popupAnchor: [0, -44],
  });
}

const MOTHERSHIP_ICON = L.divIcon({
  className: '',
  html: `<div class="ms-wrap">
           <div class="ms-ring"></div>
           <div class="ms-ring ms-ring-2"></div>
           <div class="ms-core"></div>
           <span class="ms-name">CVN-01</span>
         </div>`,
  iconSize:    [48, 56],
  iconAnchor:  [24, 24],
  popupAnchor: [0, -28],
});

// ── Waypoint layer ────────────────────────────────────────────────────────────

function WaypointLayer({ waypoints, onClear, mothershipPos }) {
  const entries = Object.entries(waypoints);

  return (
    <>
      {entries.flatMap(([droneId, wp]) => {
        const wpPos = [wp.lat, wp.lon];
        const color = WP_COLOR[wp.status] || '#a8a29e';

        const routePositions = wp.route
          ? wp.route.map(p => [p.lat, p.lon])
          : [mothershipPos, wpPos];

        return [
          <Polyline
            key={`route-${droneId}`}
            positions={routePositions}
            pathOptions={{ color, weight: 1.8, dashArray: '8 5', opacity: 0.85 }}
          />,
          <Marker
            key={`wp-${droneId}`}
            position={wpPos}
            icon={makeWaypointIcon(wp.status, wp.label ?? droneId)}
          >
            <Popup>
              <strong>{wp.label ?? droneId}</strong><br />
              {wp.status === 'invalid'
                ? <span style={{ color: '#ef4444' }}>Blocked — {wp.reason}</span>
                : wp.status === 'checking'
                ? <span style={{ color: '#eab308' }}>Checking terrain…</span>
                : <span style={{ color: '#22c55e' }}>Waypoint assigned</span>}
              <br />
              {wp.lat.toFixed(5)}, {wp.lon.toFixed(5)}
              <br />
              <button
                style={{ marginTop: '6px', padding: '3px 8px', fontSize: '0.72rem' }}
                onClick={() => onClear(droneId)}
              >
                Clear
              </button>
            </Popup>
          </Marker>,
        ];
      })}
    </>
  );
}

// ── Vehicle / event icons ─────────────────────────────────────────────────────

function vehicleArrowIcon(color, headingDeg) {
  const deg = headingDeg ?? 0;
  return L.divIcon({
    className: '',
    html: `<div style="transform:rotate(${deg}deg);width:18px;height:26px"><div class="vehicle-arrow" style="background:${color}"></div></div>`,
    iconSize:    [18, 26],
    iconAnchor:  [9, 13],
    popupAnchor: [0, -13],
  });
}

function eventMarkerIcon(color) {
  return L.divIcon({
    className: '',
    html: `<div class="event-marker" style="--marker-color:${color}">!</div>`,
    iconSize:    [28, 28],
    iconAnchor:  [14, 14],
    popupAnchor: [0, -12],
  });
}

// ── Main component ────────────────────────────────────────────────────────────

export default function OperationalMap({ mapState, waypoints = {}, mothershipPos, onDropToMap, onClearWaypoint, onMothershipMove }) {
  const mapRef    = useRef(null);
  const paneRef   = useRef(null);
  const [isDragOver, setIsDragOver] = useState(false);

  const vehicles = mapState?.vehicles || [];
  const events   = mapState?.events   || [];
  const regions  = mapState?.uncertainty_regions || [];

  function handleDragOver(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
    setIsDragOver(true);
  }

  function handleDragLeave(e) {
    if (!paneRef.current?.contains(e.relatedTarget)) setIsDragOver(false);
  }

  function handleDrop(e) {
    e.preventDefault();
    setIsDragOver(false);

    let dragData;
    try { dragData = JSON.parse(e.dataTransfer.getData('dss-drag')); } catch { return; }
    if (!dragData || !mapRef.current || !paneRef.current) return;

    const rect   = paneRef.current.getBoundingClientRect();
    const latlng = mapRef.current.containerPointToLatLng([
      e.clientX - rect.left,
      e.clientY - rect.top,
    ]);

    onDropToMap(dragData, latlng.lat, latlng.lng);
  }

  return (
    <div
      className={`map-pane${isDragOver ? ' drop-target' : ''}`}
      ref={paneRef}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <MapContainer
        center={mothershipPos}
        zoom={6}
        className="map-canvas"
        zoomControl={false}
        attributionControl={false}
      >
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          subdomains="abcd"
          maxZoom={19}
        />

        <MapRefCapture mapRef={mapRef} />
        <WaypointLayer waypoints={waypoints} onClear={onClearWaypoint} mothershipPos={mothershipPos} />

        {/* Mothership — draggable */}
        <Marker
          position={mothershipPos}
          icon={MOTHERSHIP_ICON}
          draggable
          eventHandlers={{
            dragend: (e) => {
              const { lat, lng } = e.target.getLatLng();
              onMothershipMove(lat, lng);
            },
          }}
        >
          <Popup>
            <strong>CVN-01 Mothership</strong><br />
            {mothershipPos[0].toFixed(4)}°N, {mothershipPos[1].toFixed(4)}°E<br />
            <span style={{ color: '#22c55e' }}>UNDERWAY</span>
          </Popup>
        </Marker>

        {regions.map(region => (
          <Circle
            key={region.id}
            center={[region.center.lat, region.center.lon]}
            radius={region.radius_m || 100}
            pathOptions={{ color: '#a8a29e', fillColor: '#78716c', fillOpacity: 0.16, weight: 1 }}
          >
            <Popup>
              <strong>{region.vehicle_id}</strong><br />
              {region.reason}<br />
              Radius: {region.radius_m || 100} m
            </Popup>
          </Circle>
        ))}

        {vehicles.map(vehicle => {
          const color = statusColors[vehicle.display?.color_status] || linkColors[vehicle.link_status] || '#a8a29e';
          return (
            <Marker
              key={vehicle.id}
              position={[vehicle.position.lat, vehicle.position.lon]}
              icon={vehicleArrowIcon(color, vehicle.heading_deg)}
            >
              <Popup>
                <strong>{vehicle.id}</strong><br />
                {vehicle.domain}<br />
                Link: {vehicle.link_status || 'unknown'}<br />
                Battery: {vehicle.battery_percentage ?? 'n/a'}%
              </Popup>
            </Marker>
          );
        })}

        {events.map(event => (
          <Marker
            key={event.id}
            position={[event.position.lat, event.position.lon]}
            icon={eventMarkerIcon(severityColors[event.severity] || '#f5f5f5')}
          >
            <Popup>
              <strong>{event.event_kind}</strong><br />
              {event.description}<br />
              Severity: {event.severity}<br />
              Vehicle: {event.vehicle_id || 'n/a'}
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
}
