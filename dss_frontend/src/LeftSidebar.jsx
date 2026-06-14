import React, { useState } from 'react';
import Teams from './Teams.jsx';
import Tracking from './Tracking.jsx';

const TABS = ['Teams', 'Tracking'];

export default function LeftSidebar({ mapVehicles, teams, assignments, onCreateTeam, onDeleteTeam, onAssignDrone, onUnassignDrone }) {
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
          </button>
        ))}
      </nav>

      <div className="left-sidebar-content">
        {active === 'Teams' && (
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
      </div>
    </aside>
  );
}
