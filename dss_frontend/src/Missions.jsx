import React, { useState } from 'react';
import fleet from './drones.json';

const TYPE_LABEL = { air: 'UAV', surface: 'USV', subsurface: 'UUV' };

export default function Missions() {
  const [missions, setMissions]       = useState([]);
  const [assignments, setAssignments] = useState({});   // droneId → missionId | null
  const [newName, setNewName]         = useState('');
  const [creating, setCreating]       = useState(false);

  function createMission(e) {
    e.preventDefault();
    const name = newName.trim();
    if (!name) return;
    const id = `m_${Date.now()}`;
    setMissions(prev => [...prev, { id, name }]);
    setNewName('');
    setCreating(false);
  }

  function deleteMission(missionId) {
    setMissions(prev => prev.filter(m => m.id !== missionId));
    setAssignments(prev => {
      const next = { ...prev };
      for (const k of Object.keys(next)) {
        if (next[k] === missionId) next[k] = null;
      }
      return next;
    });
  }

  function assign(droneId, missionId) {
    setAssignments(prev => ({ ...prev, [droneId]: missionId || null }));
  }

  return (
    <aside className="missions-sidebar">
    <div className="missions-panel">

      {/* ── Mission list ───────────────────────────── */}
      <div className="panel-header">
        <span>Missions</span>
        <button className="btn-xs" onClick={() => setCreating(true)}>+ New</button>
      </div>

      {creating && (
        <form className="new-mission-form" onSubmit={createMission}>
          <input
            autoFocus
            value={newName}
            onChange={e => setNewName(e.target.value)}
            placeholder="Mission name…"
          />
          <button type="submit">Create</button>
          <button type="button" className="btn-ghost" onClick={() => { setCreating(false); setNewName(''); }}>
            Cancel
          </button>
        </form>
      )}

      {missions.length === 0 && !creating && (
        <p className="panel-empty">No missions yet.</p>
      )}

      {missions.map(mission => {
        const assigned = fleet.filter(d => assignments[d.id] === mission.id);
        const byType = { air: [], surface: [], subsurface: [] };
        assigned.forEach(d => byType[d.type]?.push(d));

        return (
          <div key={mission.id} className="mission-card">
            <div className="mission-card-head">
              <span className="mission-name">{mission.name}</span>
              <button className="btn-delete" onClick={() => deleteMission(mission.id)}>×</button>
            </div>
            <div className="mission-types">
              {Object.entries(byType).map(([type, drones]) => drones.length > 0 && (
                <span key={type} className={`type-badge type-${type}`}>
                  {TYPE_LABEL[type]} ×{drones.length}
                </span>
              ))}
              {assigned.length === 0 && <span className="dim">No drones assigned</span>}
            </div>
          </div>
        );
      })}

      {/* ── Fleet pool ─────────────────────────────── */}
      <div className="panel-header" style={{ marginTop: '1rem' }}>
        <span>Fleet</span>
      </div>

      {fleet.map(drone => (
        <div key={drone.id} className="drone-row">
          <div className="drone-info">
            <span className={`type-dot type-${drone.type}`} />
            <div>
              <span className="drone-label">{drone.label}</span>
              <span className="drone-sensors">{drone.sensors.join(' · ')}</span>
            </div>
          </div>
          <select
            className="mission-select"
            value={assignments[drone.id] || ''}
            onChange={e => assign(drone.id, e.target.value || null)}
          >
            <option value="">—</option>
            {missions.map(m => (
              <option key={m.id} value={m.id}>{m.name}</option>
            ))}
          </select>
        </div>
      ))}

    </div>
    </aside>
  );
}
