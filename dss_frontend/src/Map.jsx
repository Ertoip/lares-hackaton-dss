import React, { useEffect, useRef, useState } from 'react';
import { Circle, MapContainer, Marker, Polygon, Polyline, Popup, TileLayer, useMap } from 'react-leaflet';
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

const WP_COLOR    = { checking: '#eab308', valid: '#22c55e', invalid: '#ef4444' };
const TYPE_COLOR  = { air: '#38bdf8', surface: '#22c55e', subsurface: '#a855f7' };

// ── Map ref capture ───────────────────────────────────────────────────────────

function MapRefCapture({ mapRef }) {
  const map = useMap();
  useEffect(() => { mapRef.current = map; }, [map]);
  return null;
}

// ── Uncertainty ellipse ───────────────────────────────────────────────────────

function makeEllipsePositions(lat, lon, semiAlong, semiCross, headingDeg, n = 36) {
  const mPerDegLat = 111320;
  const mPerDegLon = 111320 * Math.cos(lat * Math.PI / 180);
  // heading 0=N CW → math angle 0=E CCW → theta = -heading
  const theta = -(headingDeg ?? 0) * Math.PI / 180;
  return Array.from({ length: n + 1 }, (_, i) => {
    const t = (i / n) * 2 * Math.PI;
    const lx = semiCross * Math.cos(t);
    const ly = semiAlong * Math.sin(t);
    const eM = lx * Math.cos(theta) - ly * Math.sin(theta);
    const nM = lx * Math.sin(theta) + ly * Math.cos(theta);
    return [lat + nM / mPerDegLat, lon + eM / mPerDegLon];
  });
}

// ── Waypoint & mothership icons ───────────────────────────────────────────────

function makeWaypointIcon(status, label, color) {
  color = color || WP_COLOR[status] || '#a8a29e';
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

const MODES = [
  { id: 'waypoint', label: 'WPT',    icon: '◎' },
  { id: 'patrol',   label: 'Patrol', icon: '↻' },
  { id: 'recon',    label: 'Recon',  icon: '⊞' },
  { id: 'protect',  label: 'Escort', icon: '⬡' },
];

const MODE_LABEL = { waypoint: 'Waypoint', patrol: 'Patrol orbit', recon: 'Recon sweep', protect: 'Escort / protect' };

function WaypointLayer({ waypoints, onClear, mothershipPos, vehiclePositions }) {
  const entries = Object.entries(waypoints);

  return (
    <>
      {entries.flatMap(([droneId, wp]) => {
        const wpPos = [wp.lat, wp.lon];
        const color = TYPE_COLOR[wp.type] || WP_COLOR[wp.status] || '#a8a29e';

        // Start the route from the drone's live position (fallback: mothership)
        const dronePos = vehiclePositions?.[droneId];
        const startPos = dronePos || mothershipPos;

        const routePositions = wp.route
          ? [startPos, ...wp.route.slice(1).map(p => [p.lat, p.lon])]
          : [startPos, wpPos];

        return [
          <Polyline
            key={`route-${droneId}`}
            positions={routePositions}
            pathOptions={{ color, weight: 1.8, dashArray: '8 5', opacity: 0.85 }}
          />,

          wp.mode === 'patrol' && (
            <Circle
              key={`zone-${droneId}`}
              center={wpPos}
              radius={5500}
              pathOptions={{ color, weight: 1, dashArray: '7 4', fillOpacity: 0 }}
            />
          ),

          wp.mode === 'protect' && (
            <Circle
              key={`zone-${droneId}`}
              center={wpPos}
              radius={2400}
              pathOptions={{ color, weight: 1.5, fillColor: color, fillOpacity: 0.07 }}
            />
          ),

          wp.pattern && (
            <Polyline
              key={`pattern-${droneId}`}
              positions={wp.pattern.map(p => [p.lat, p.lon])}
              pathOptions={{ color, weight: 1.4, dashArray: wp.mode === 'recon' ? '5 3' : null, opacity: 0.75 }}
            />
          ),

          <Marker
            key={`wp-${droneId}`}
            position={wpPos}
            icon={makeWaypointIcon(wp.status, wp.label ?? droneId, color)}
          >
            <Popup>
              <strong>{wp.label ?? droneId}</strong><br />
              <span style={{ color, textTransform: 'uppercase', fontSize: '0.7rem', fontWeight: 700 }}>
                {MODE_LABEL[wp.mode] || 'Waypoint'}
              </span><br />
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

// ── Mission mode toolbar ──────────────────────────────────────────────────────

function ModeToolbar({ mode, onChange }) {
  return (
    <div className="mode-toolbar">
      {MODES.map(m => (
        <button
          key={m.id}
          className={`mode-btn${mode === m.id ? ' active' : ''}`}
          onClick={() => onChange(m.id)}
        >
          <span className="mode-icon">{m.icon}</span>
          <span className="mode-label">{m.label}</span>
        </button>
      ))}
    </div>
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

function contactMarkerIcon(behavior) {
  const hostile = (behavior || '').toLowerCase() === 'hostile';
  return L.divIcon({
    className: '',
    html: `<div class="contact-marker${hostile ? ' hostile' : ''}">⬥</div>`,
    iconSize:    [22, 22],
    iconAnchor:  [11, 11],
    popupAnchor: [0, -14],
  });
}

function aisVesselIcon(headingDeg) {
  return L.divIcon({
    className: '',
    html: `<div style="transform:rotate(${headingDeg ?? 0}deg);width:14px;height:20px"><div class="vehicle-arrow" style="background:#78716c;opacity:0.7"></div></div>`,
    iconSize:    [14, 20],
    iconAnchor:  [7, 10],
    popupAnchor: [0, -12],
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

export default function OperationalMap({
  mapState, waypoints = {}, mothershipPos, missionMode,
  onDropToMap, onClearWaypoint, onMothershipMove, onMissionModeChange,
}) {
  const mapRef  = useRef(null);
  const paneRef = useRef(null);
  const [isDragOver, setIsDragOver] = useState(false);

  const vehicles  = mapState?.vehicles   || [];
  const events    = mapState?.events     || [];
  const regions   = mapState?.uncertainty_regions || [];
  const contacts  = mapState?.contacts   || [];
  const aisVessels = mapState?.ais       || [];

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
      <ModeToolbar mode={missionMode} onChange={onMissionModeChange} />

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
        <WaypointLayer
          waypoints={waypoints}
          onClear={onClearWaypoint}
          mothershipPos={mothershipPos}
          vehiclePositions={Object.fromEntries(
            vehicles.filter(v => v.position).map(v => [v.id, [v.position.lat, v.position.lon]])
          )}
        />

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

        {/* Uncertainty ellipses */}
        {regions.map(region => {
          const hasEllipse = region.sigma_along_m && region.sigma_cross_m;
          if (hasEllipse) {
            const positions = makeEllipsePositions(
              region.center.lat, region.center.lon,
              region.sigma_along_m, region.sigma_cross_m,
              region.uncertainty_heading_deg,
            );
            return (
              <Polygon
                key={region.id}
                positions={positions}
                pathOptions={{ color: '#eab308', fillColor: '#eab308', fillOpacity: 0.05, weight: 1.2, dashArray: '6 4' }}
              >
                <Popup>
                  <strong>{region.vehicle_id}</strong><br />
                  {region.reason}<br />
                  ±{Math.round(region.sigma_along_m)}m × ±{Math.round(region.sigma_cross_m)}m
                </Popup>
              </Polygon>
            );
          }
          return (
            <Circle
              key={region.id}
              center={[region.center.lat, region.center.lon]}
              radius={region.radius_m || 100}
              pathOptions={{ color: '#eab308', fillColor: '#eab308', fillOpacity: 0.05, weight: 1.2, dashArray: '6 4' }}
            >
              <Popup>
                <strong>{region.vehicle_id}</strong><br />
                {region.reason}<br />
                Radius: {region.radius_m || 100} m
              </Popup>
            </Circle>
          );
        })}

        {/* Vehicles */}
        {vehicles.map(vehicle => {
          const color = statusColors[vehicle.display?.color_status] || linkColors[vehicle.link_status] || '#a8a29e';
          return (
            <React.Fragment key={vehicle.id}>
              <Marker
                position={[vehicle.position.lat, vehicle.position.lon]}
                icon={vehicleArrowIcon(color, vehicle.heading_deg)}
              >
                <Popup>
                  <strong>{vehicle.id}</strong><br />
                  {vehicle.domain} · {vehicle.status}<br />
                  Link: {vehicle.link_status || 'unknown'}<br />
                  Battery: {vehicle.battery_percentage ?? 'n/a'}%<br />
                  {vehicle.age_sec > 0 && <span>No fix: {Math.round(vehicle.age_sec)}s</span>}
                  {vehicle.rtb && <><br /><span style={{ color: '#f97316' }}>RTB in progress</span></>}
                  {vehicle.submerged && <><br /><span style={{ color: '#a855f7' }}>SUBMERGED</span></>}
                </Popup>
              </Marker>
              {/* RTB dashed line to mothership */}
              {vehicle.rtb && (
                <Polyline
                  positions={[[vehicle.position.lat, vehicle.position.lon], mothershipPos]}
                  pathOptions={{ color: '#f97316', weight: 1, dashArray: '6 4', opacity: 0.7 }}
                />
              )}
            </React.Fragment>
          );
        })}

        {/* Threat contacts */}
        {contacts.map(contact => (
          <Marker
            key={contact.id}
            position={[contact.position.lat, contact.position.lon]}
            icon={contactMarkerIcon(contact.behavior)}
          >
            <Popup>
              <strong>{contact.id}</strong><br />
              Behavior: <span style={{ color: '#ef4444', textTransform: 'uppercase', fontWeight: 700 }}>{contact.behavior}</span><br />
              Speed: {contact.speed_knots?.toFixed(1)} kn · Hdg: {Math.round(contact.heading)}°<br />
              {!contact.ais && <span style={{ color: '#f97316' }}>AIS dark — no transponder</span>}
            </Popup>
          </Marker>
        ))}

        {/* AIS vessel traffic */}
        {aisVessels.map((vessel, i) => (
          <Marker
            key={vessel.mmsi || i}
            position={[vessel.position.lat, vessel.position.lon]}
            icon={aisVesselIcon(vessel.heading)}
          >
            <Popup>
              <strong>{vessel.name || vessel.mmsi}</strong><br />
              SOG: {vessel.sog_knots?.toFixed(1)} kn · Hdg: {Math.round(vessel.heading)}°
            </Popup>
          </Marker>
        ))}

        {/* DSS events */}
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
