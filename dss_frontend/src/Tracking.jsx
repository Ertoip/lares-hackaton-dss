import React from 'react';
import { DroneIcon } from './icons.jsx';
import fleet from './drones.json';

const TYPE_COLOR  = { air: '#38bdf8', surface: '#22c55e', subsurface: '#a855f7' };
const LINK_COLOR  = { online: '#22c55e', degraded: '#eab308', unstable: '#f97316', lost_link: '#ef4444', late_contact: '#f97316', expected_blackout: '#6b7280' };
const STATUS_LABEL = { online: 'ONLINE', degraded: 'DEGRADED', unstable: 'UNSTABLE', lost_link: 'LOST', late_contact: 'LATE', expected_blackout: 'BLACKOUT' };

function formatCoord(val) {
  return val != null ? val.toFixed(4) : '—';
}

export default function Tracking({ mapVehicles }) {
  const byId = Object.fromEntries((mapVehicles || []).map(v => [v.id, v]));

  return (
    <div className="panel-body">
      <div className="panel-header"><span>Live Tracking</span></div>

      {fleet.map(drone => {
        const live = byId[drone.id];
        const color = TYPE_COLOR[drone.type];
        const linkStatus = live?.link_status;
        const linkColor = LINK_COLOR[linkStatus] || '#6b7280';
        const battery = live?.battery_percentage;
        const batteryLow = battery != null && battery <= 20;

        return (
          <div key={drone.id} className={`tracking-card${!live ? ' offline' : ''}`}>
            <div className="tracking-card-head">
              <div className="tracking-icon">
                <DroneIcon type={drone.type} size={18} color={live ? color : '#4a5570'} />
              </div>
              <span className="tracking-label">{drone.label}</span>
              <span className="tracking-status" style={{ color: linkColor }}>
                {live ? (STATUS_LABEL[linkStatus] || 'ONLINE') : 'NO SIGNAL'}
              </span>
            </div>

            {live && (
              <div className="tracking-details">
                <div className="tracking-row">
                  <span className="td-key">Battery</span>
                  <span className="td-val" style={{ color: batteryLow ? '#f97316' : 'inherit' }}>
                    {battery != null ? `${battery}%` : '—'}
                  </span>
                </div>
                <div className="tracking-row">
                  <span className="td-key">Heading</span>
                  <span className="td-val">{live.heading_deg != null ? `${live.heading_deg}°` : '—'}</span>
                </div>
                <div className="tracking-row">
                  <span className="td-key">Position</span>
                  <span className="td-val">
                    {live.position ? `${formatCoord(live.position.lat)}, ${formatCoord(live.position.lon)}` : '—'}
                  </span>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
