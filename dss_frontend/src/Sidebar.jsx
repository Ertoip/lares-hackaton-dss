import React, { useState } from 'react';
import Chat from './Chat.jsx';
import Missions from './Missions.jsx';

const TABS = ['Missions'];

export default function Sidebar({ messages, error, onRefresh }) {
  const [activeTab, setActiveTab] = useState('Missions');

  return (
    <aside className="sidebar">
      <nav className="sidebar-tabs">
        {TABS.map(tab => (
          <button
            key={tab}
            className={`tab-btn${activeTab === tab ? ' active' : ''}`}
            onClick={() => setActiveTab(tab)}
          >
            {tab}
          </button>
        ))}
      </nav>

      <div className="sidebar-section">
        {activeTab === 'Missions' && <Missions />}
      </div>

      <Chat messages={messages} error={error} onRefresh={onRefresh} />
    </aside>
  );
}
