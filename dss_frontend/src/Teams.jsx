import React, { useState } from 'react';
import { DroneIcon } from './icons.jsx';
import fleet from './drones.json';

const TYPE_COLOR = { air: '#38bdf8', surface: '#22c55e', subsurface: '#a855f7' };

function setDrag(e, data) {
  e.dataTransfer.setData('dss-drag', JSON.stringify(data));
  e.dataTransfer.effectAllowed = 'copy';
}

export default function Teams({ teams, assignments, onCreateTeam, onDeleteTeam, onAssignDrone, onUnassignDrone }) {
  const [newName, setNewName]   = useState('');
  const [creating, setCreating] = useState(false);
  const [dragOver, setDragOver] = useState(null); // teamId being hovered

  function handleCreate(e) {
    e.preventDefault();
    const name = newName.trim();
    if (!name) return;
    onCreateTeam(name);
    setNewName('');
    setCreating(false);
  }

  function onDropOnTeam(e, teamId) {
    e.preventDefault();
    let data;
    try { data = JSON.parse(e.dataTransfer.getData('dss-drag')); } catch { return; }
    if (data?.droneId) onAssignDrone(data.droneId, teamId);
    setDragOver(null);
  }

  return (
    <div className="panel-body">

      {/* ── Teams list ─────────────────────────────────────────────── */}
      <div className="panel-header">
        <span>Teams</span>
        <button className="btn-xs" onClick={() => setCreating(true)}>+ New</button>
      </div>

      {creating && (
        <form className="new-mission-form" onSubmit={handleCreate}>
          <input
            autoFocus
            value={newName}
            onChange={e => setNewName(e.target.value)}
            placeholder="Team name…"
          />
          <button type="submit">Create</button>
          <button type="button" className="btn-ghost" onClick={() => { setCreating(false); setNewName(''); }}>✕</button>
        </form>
      )}

      {teams.length === 0 && !creating && (
        <p className="panel-empty">No teams yet.</p>
      )}

      {teams.map(team => {
        const assigned = fleet.filter(d => assignments[d.id] === team.id);
        return (
          <div
            key={team.id}
            className={`team-card${dragOver === team.id ? ' drag-over' : ''}`}
            draggable
            onDragStart={e => setDrag(e, { teamId: team.id })}
            onDragOver={e => { e.preventDefault(); setDragOver(team.id); }}
            onDragLeave={() => setDragOver(null)}
            onDrop={e => onDropOnTeam(e, team.id)}
          >
            <div className="team-card-head">
              <span className="team-name">{team.name}</span>
              <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                <span className="team-drag-hint">⠿</span>
                <button className="btn-delete" onClick={() => onDeleteTeam(team.id)}>×</button>
              </div>
            </div>
            <div className="team-drones">
              {assigned.length === 0 && <span className="drop-hint">Drop drones here</span>}
              {assigned.map(d => (
                <div key={d.id} className="team-drone-tag" style={{ '--tc': TYPE_COLOR[d.type] }}>
                  <DroneIcon type={d.type} size={13} color={TYPE_COLOR[d.type]} />
                  <span>{d.label}</span>
                  <button className="tag-remove" onClick={() => onUnassignDrone(d.id)}>×</button>
                </div>
              ))}
            </div>
          </div>
        );
      })}

      {/* ── Fleet pool ─────────────────────────────────────────────── */}
      <div className="panel-header" style={{ marginTop: '1rem' }}>
        <span>Fleet</span>
      </div>

      <div className="fleet-grid">
        {fleet.map(drone => {
          const color    = TYPE_COLOR[drone.type];
          const teamId   = assignments[drone.id];
          const teamName = teamId ? teams.find(t => t.id === teamId)?.name : null;
          return (
            <div
              key={drone.id}
              className={`drone-card${teamId ? ' assigned' : ''}`}
              draggable
              onDragStart={e => setDrag(e, { droneId: drone.id })}
              style={{ '--dc': color }}
            >
              <div className="drone-card-icon">
                <DroneIcon type={drone.type} size={22} color={color} />
              </div>
              <div className="drone-card-info">
                <span className="drone-label">{drone.label}</span>
                <span className="drone-sensors">{drone.sensors.join(' · ')}</span>
                {teamName && <span className="drone-team-badge">{teamName}</span>}
              </div>
            </div>
          );
        })}
      </div>

    </div>
  );
}
