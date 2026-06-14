import React, { useState } from 'react';
import Teams from './Teams.jsx';
import Tracking from './Tracking.jsx';

const TABS = ['Teams', 'Tracking', 'Alerts'];

const ALERT_COLOR = {
  threat_contact:   '#ef4444',
  sensor_failure:   '#f97316',
  bingo_warning:    '#f97316',
  prebingo_warning: '#eab308',
  acoustic_loss:    '#a855f7',
  acoustic_regain:  '#22c55e',
  vehicle_docked:   '#38bdf8',
  sim_start:        '#a8a29e',
};

function AlertsPanel({ alerts }) {
  if (!alerts.length) {
    return <div className="alerts-empty">No active alerts</div>;
  }
  return (
    <div className="alerts-list">
      {[...alerts].reverse().map((a, i) => {
        const color = ALERT_COLOR[a.type] || '#a8a29e';
        return (
          <div key={i} className="alert-row" style={{ borderLeftColor: color }}>
            <span className="alert-type" style={{ color }}>{(a.type || '').replace(/_/g, ' ').toUpperCase()}</span>
            {a.vehicle && <span className="alert-vehicle"> · {a.vehicle}</span>}
            <p className="alert-msg">{a.message}</p>
          </div>
        );
      })}
    </div>
  );
}

function WeatherStrip({ weather }) {
  if (!weather || weather.error) return null;
  return (
    <div className="weather-strip">
      <span className="weather-label">SEA STATE {weather.sea_state ?? '–'}</span>
      <span className="weather-val">{weather.sea_state_label || ''}</span>
      <span className="weather-sep">·</span>
      <span className="weather-val">↑ {weather.wave_height_m?.toFixed(1) ?? '–'}m</span>
      <span className="weather-sep">·</span>
      <span className="weather-val">💨 {weather.wind_speed_kn?.toFixed(0) ?? '–'}kn</span>
      <span className="weather-sep">·</span>
      <span className="weather-val">{weather.air_temp_c?.toFixed(0) ?? '–'}°C</span>
    </div>
  );
}

export default function LeftSidebar({
  mapVehicles, teams, assignments, alerts, weather,
  onCreateTeam, onDeleteTeam, onAssignDrone, onUnassignDrone,
}) {
  const [active, setActive] = useState('Teams');

  return (
    <aside className="left-sidebar">
      <nav className="sidebar-tabs">
        {TABS.map(tab => (
          <button
            key={tab}
            className={`tab-btn${active === tab ? ' active' : ''}`}
            onClick={() => setActive(tab)}
          >
            {tab}
            {tab === 'Alerts' && alerts.length > 0 && (
              <span className="alert-badge">{alerts.length}</span>
            )}
          </button>
        ))}
      </nav>

      <div className="left-sidebar-content">
        {active === 'Teams'    && (
          <Teams
            teams={teams}
            assignments={assignments}
            onCreateTeam={onCreateTeam}
            onDeleteTeam={onDeleteTeam}
            onAssignDrone={onAssignDrone}
            onUnassignDrone={onUnassignDrone}
          />
        )}
        {active === 'Tracking' && <Tracking mapVehicles={mapVehicles} />}
        {active === 'Alerts'   && <AlertsPanel alerts={alerts} />}
      </div>

      <WeatherStrip weather={weather} />
    </aside>
  );
}
