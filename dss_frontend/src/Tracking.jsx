import React, { useState } from 'react';
import { DroneIcon } from './icons.jsx';
import fleet from './drones.json';
import { API_BASE_URL } from './App.jsx';

const TYPE_COLOR   = { air: '#38bdf8', surface: '#22c55e', subsurface: '#a855f7' };
const LINK_COLOR   = { online: '#22c55e', degraded: '#eab308', unstable: '#f97316', lost_link: '#ef4444', late_contact: '#f97316', expected_blackout: '#6b7280' };
const STATUS_LABEL = { online: 'ONLINE', degraded: 'DEGRADED', unstable: 'UNSTABLE', lost_link: 'LOST', late_contact: 'LATE', expected_blackout: 'BLACKOUT' };

async function sendCommand(vehicleId, action, params = {}) {
  try {
    await fetch(`${API_BASE_URL}/dss/sim/command`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ vehicle_id: vehicleId, action, params }),
    });
  } catch { /* ignore — best-effort */ }
}

function formatCoord(val) {
  return val != null ? val.toFixed(4) : '—';
}

export default function Tracking({ mapVehicles }) {
  const byId = Object.fromEntries((mapVehicles || []).map(v => [v.id, v]));
  const [pending, setPending] = useState({});

  async function doCommand(vehicleId, action, params) {
    setPending(p => ({ ...p, [vehicleId]: action }));
    await sendCommand(vehicleId, action, params);
    setTimeout(() => setPending(p => { const n = { ...p }; delete n[vehicleId]; return n; }), 1200);
  }

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
        const isRtb = live?.rtb;
        const isBusy = !!pending[drone.id];

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
              <>
                <div className="tracking-details">
                  <div className="tracking-row">
                    <span className="td-key">Battery</span>
                    <span className="td-val" style={{ color: batteryLow ? '#f97316' : 'inherit' }}>
                      {battery != null ? `${battery}%` : '—'}
                    </span>
                  </div>
                  <div className="tracking-row">
                    <span className="td-key">Heading</span>
                    <span className="td-val">{live.heading_deg != null ? `${Math.round(live.heading_deg)}°` : '—'}</span>
                  </div>
                  <div className="tracking-row">
                    <span className="td-key">Position</span>
                    <span className="td-val">
                      {live.position ? `${formatCoord(live.position.lat)}, ${formatCoord(live.position.lon)}` : '—'}
                    </span>
                  </div>
                  {live.current_task_id && (
                    <div className="tracking-row">
                      <span className="td-key">Task</span>
                      <span className="td-val">{live.current_task_id}</span>
                    </div>
                  )}
                </div>

                <div className="tracking-actions">
                  {isRtb ? (
                    <span className="tracking-rtb-badge">RTB IN PROGRESS</span>
                  ) : (
                    <button
                      className="tracking-cmd-btn rtb"
                      disabled={isBusy}
                      onClick={() => doCommand(drone.id, 'rtb')}
                    >
                      {isBusy && pending[drone.id] === 'rtb' ? 'Sending…' : 'Return to Base'}
                    </button>
                  )}
                </div>
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}
