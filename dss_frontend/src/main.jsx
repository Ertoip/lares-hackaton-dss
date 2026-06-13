import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Circle, MapContainer, Marker, Popup, TileLayer, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import './styles.css';

const API_BASE_URL = import.meta.env.VITE_DSS_API_BASE_URL || 'http://localhost:8001';

const emptyOperatorState = {
  map: { vehicles: [], events: [], contacts: [], zones: [], uncertainty_regions: [] },
  chat_messages: [],
};

const linkColors = {
  online: '#f5f5f5',
  degraded: '#d6d3d1',
  unstable: '#a8a29e',
  lost_link: '#ef4444',
  expected_blackout: '#78716c',
  late_contact: '#f97316',
};

const severityColors = {
  low: '#d6d3d1',
  medium: '#eab308',
  high: '#f97316',
  critical: '#ef4444',
};

function markerIcon(label, color, className = 'vehicle-marker') {
  return L.divIcon({
    className: '',
    html: `<div class="${className}" style="--marker-color:${color}">${label}</div>`,
    iconSize: [30, 30],
    iconAnchor: [15, 15],
    popupAnchor: [0, -12],
  });
}

function formatTime(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function useOperatorState() {
  const [state, setState] = useState(emptyOperatorState);
  const [error, setError] = useState(null);

  async function load() {
    try {
      const response = await fetch(`${API_BASE_URL}/dss/operator-state`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      setState({ ...emptyOperatorState, ...data });
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch DSS state');
    }
  }

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 1000);
    return () => window.clearInterval(timer);
  }, []);

  return { state, error, refresh: load };
}

function FitBounds({ vehicles, events }) {
  const map = useMap();

  useEffect(() => {
    const points = [];
    for (const item of vehicles || []) {
      if (item.position?.lat !== undefined && item.position?.lon !== undefined) {
        points.push([item.position.lat, item.position.lon]);
      }
    }
    for (const item of events || []) {
      if (item.position?.lat !== undefined && item.position?.lon !== undefined) {
        points.push([item.position.lat, item.position.lon]);
      }
    }

    if (points.length === 1) {
      map.setView(points[0], 14, { animate: true });
    }
    if (points.length > 1) {
      map.fitBounds(points, { padding: [28, 28], maxZoom: 15, animate: true });
    }
  }, [map, vehicles, events]);

  return null;
}

function OperationalMap({ mapState }) {
  const vehicles = mapState?.vehicles || [];
  const events = mapState?.events || [];
  const regions = mapState?.uncertainty_regions || [];
  const center = vehicles[0]?.position || events[0]?.position || { lat: 41.9028, lon: 12.4964 };

  return (
    <div className="map-pane">
      <MapContainer center={[center.lat, center.lon]} zoom={12} className="map-canvas" zoomControl={false} attributionControl={false}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          subdomains="abcd"
          maxZoom={19}
        />
        <FitBounds vehicles={vehicles} events={events} />
        {regions.map((region) => (
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
        {vehicles.map((vehicle) => {
          const color = linkColors[vehicle.link_status] || '#a8a29e';
          const label = vehicle.marker === 'uav' ? 'A' : vehicle.marker === 'usv' ? 'S' : 'U';
          return (
            <Marker
              key={vehicle.id}
              position={[vehicle.position.lat, vehicle.position.lon]}
              icon={markerIcon(label, color)}
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
        {events.map((event) => (
          <Marker
            key={event.id}
            position={[event.position.lat, event.position.lon]}
            icon={markerIcon('!', severityColors[event.severity] || '#f5f5f5', 'event-marker')}
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

function ChatPane({ messages, error, onSend, sending }) {
  const [draft, setDraft] = useState('');
  const orderedMessages = [...(messages || [])].sort((a, b) => new Date(a.timestamp || 0) - new Date(b.timestamp || 0));

  async function handleSubmit(event) {
    event.preventDefault();
    const message = draft.trim();
    if (!message || sending) return;
    setDraft('');
    await onSend(message);
  }

  return (
    <aside className="chat-pane">
      <div className="chat-header">
        <span>LLM Chat</span>
        {error && <small>API {error}</small>}
      </div>

      <div className="chat-stream">
        {orderedMessages.length === 0 && (
          <div className="empty-chat">
            <p>Ask about current vehicles, events, reports, or map state.</p>
          </div>
        )}

        {orderedMessages.map((message) => (
          <article className={`chat-message ${message.sender === 'operator' ? 'operator' : 'assistant'}`} key={message.message_id}>
            <div className="message-meta">
              <span>{message.sender === 'operator' ? 'You' : 'DSS LLM'}</span>
              <time>{formatTime(message.timestamp)}</time>
            </div>
            {message.sender !== 'operator' && <h2>{message.title}</h2>}
            <p>{message.body}</p>

            {message.details?.situation?.length > 0 && (
              <ul>
                {message.details.situation.map((item) => <li key={item}>{item}</li>)}
              </ul>
            )}

            {message.linked_event_ids?.length > 0 && (
              <div className="linked-events">
                {message.linked_event_ids.map((id) => <code key={id}>{id}</code>)}
              </div>
            )}

            {message.message_type === 'anomaly_report' && !message.acknowledged && <span className="unacked">unacknowledged report</span>}
          </article>
        ))}
      </div>

      <form className="chat-input" onSubmit={handleSubmit}>
        <textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Ask the DSS LLM..."
          rows={3}
        />
        <button type="submit" disabled={sending || !draft.trim()}>{sending ? 'Thinking' : 'Send'}</button>
      </form>
    </aside>
  );
}

function App() {
  const { state, error, refresh } = useOperatorState();
  const [sending, setSending] = useState(false);

  async function sendMessage(message) {
    setSending(true);
    try {
      await fetch(`${API_BASE_URL}/dss/chat/send`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }),
      });
      refresh();
    } finally {
      setSending(false);
    }
  }

  return (
    <main className="app-shell">
      <OperationalMap mapState={state.map || emptyOperatorState.map} />
      <ChatPane messages={state.chat_messages || []} error={error} onSend={sendMessage} sending={sending} />
    </main>
  );
}

createRoot(document.getElementById('root')).render(<App />);
