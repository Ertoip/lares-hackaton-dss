import React, { useCallback, useEffect, useState } from 'react';
import OperationalMap from './Map.jsx';
import Chat from './Chat.jsx';
import LeftSidebar from './LeftSidebar.jsx';
import fleet from './drones.json';

export const API_BASE_URL = import.meta.env.VITE_DSS_API_BASE_URL || 'http://localhost:8001';

const emptyState = {
  map: { vehicles: [], events: [], contacts: [], ais: [], zones: [], uncertainty_regions: [] },
  chat_messages: [],
  alerts: [],
  weather: null,
  mothership: null,
  sim_time_sec: null,
};

const WATER_ONLY = new Set(['surface', 'subsurface']);

function generatePattern(mode, lat, lon) {
  if (mode === 'patrol') {
    const R = 0.05, N = 20;
    return Array.from({ length: N + 1 }, (_, i) => {
      const a = (i / N) * 2 * Math.PI;
      return { lat: lat + R * Math.cos(a), lon: lon + R * Math.sin(a) };
    });
  }
  if (mode === 'recon') {
    const lanes = 5, W = 0.09, H = 0.12;
    const pts = [];
    for (let i = 0; i < lanes; i++) {
      const lonOff = -W / 2 + (i / (lanes - 1)) * W;
      const top = { lat: lat + H / 2, lon: lon + lonOff };
      const bot = { lat: lat - H / 2, lon: lon + lonOff };
      pts.push(i % 2 === 0 ? top : bot);
      pts.push(i % 2 === 0 ? bot : top);
    }
    return pts;
  }
  if (mode === 'protect') {
    const R = 0.022, N = 16;
    return Array.from({ length: N + 1 }, (_, i) => {
      const a = (i / N) * 2 * Math.PI;
      return { lat: lat + R * Math.cos(a), lon: lon + R * Math.sin(a) };
    });
  }
  return null;
}

export default function App() {
  const [state, setState]         = useState(emptyState);
  const [error, setError]         = useState(null);

  // Teams & assignments (lifted here so map drop handler can read them)
  const [teams, setTeams]             = useState([]);
  const [assignments, setAssignments] = useState({}); // droneId → teamId | null

  // Waypoints: droneId → { lat, lon, label, status, route? }
  const [waypoints, setWaypoints] = useState({});

  // Mothership position (movable)
  const [mothershipPos, setMothershipPos] = useState([51.0, 1.5]);

  // Active mission mode
  const [missionMode, setMissionMode] = useState('waypoint');

  // ── DSS polling ───────────────────────────────────────────────────────
  async function load() {
    try {
      const res = await fetch(`${API_BASE_URL}/dss/operator-state`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setState({ ...emptyState, ...data });
      setError(null);

      // Sync mothership position from simulation when available
      if (data.mothership?.lat != null && data.mothership?.lon != null) {
        setMothershipPos(prev => {
          const [pLat, pLon] = prev;
          const { lat, lon } = data.mothership;
          // Only update if moved more than ~10m (avoids jitter overriding manual drags)
          if (Math.abs(lat - pLat) > 0.0001 || Math.abs(lon - pLon) > 0.0001) {
            return [lat, lon];
          }
          return prev;
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Connection failed');
    }
  }

  useEffect(() => {
    load();
    const t = setInterval(load, 1000);
    return () => clearInterval(t);
  }, []);

  // ── Team CRUD ─────────────────────────────────────────────────────────
  const onCreateTeam = useCallback((name) => {
    setTeams(prev => [...prev, { id: `t_${Date.now()}`, name }]);
  }, []);

  const onDeleteTeam = useCallback((teamId) => {
    setTeams(prev => prev.filter(t => t.id !== teamId));
    setAssignments(prev => {
      const next = { ...prev };
      for (const k of Object.keys(next)) if (next[k] === teamId) next[k] = null;
      return next;
    });
  }, []);

  const onAssignDrone = useCallback((droneId, teamId) => {
    setAssignments(prev => ({ ...prev, [droneId]: teamId }));
  }, []);

  const onUnassignDrone = useCallback((droneId) => {
    setAssignments(prev => ({ ...prev, [droneId]: null }));
  }, []);

  // ── Map drop ──────────────────────────────────────────────────────────
  const onDropToMap = useCallback(async (dragData, lat, lon) => {
    const { droneId, teamId } = dragData;

    // Build list of drones + their slightly-spread waypoint positions
    let droneWps = [];
    if (droneId) {
      const d = fleet.find(f => f.id === droneId);
      droneWps = [{ droneId, wpLat: lat, wpLon: lon, type: d?.type, label: d?.label ?? droneId }];
    } else if (teamId) {
      const members = fleet.filter(f => assignments[f.id] === teamId);
      droneWps = members.map((d, i) => {
        const spread = 0.004;
        const offset = (i - (members.length - 1) / 2) * spread;
        return { droneId: d.id, wpLat: lat + offset, wpLon: lon, type: d.type, label: d.label };
      });
    }

    if (droneWps.length === 0) return;

    // Terrain check before any assignment
    let isLand = false;
    try {
      const res = await fetch(`${API_BASE_URL}/dss/terrain?lat=${lat}&lon=${lon}`);
      const data = await res.json();
      isLand = data.is_land;
    } catch { /* permissive on failure */ }

    // Filter out water-only vehicles if drop is on land
    const allowed = droneWps.filter(({ type }) => !(isLand && WATER_ONLY.has(type)));
    if (allowed.length === 0) return;

    const TASK_LABEL = { waypoint: 'Waypoint nav', patrol: 'Patrol orbit', recon: 'Recon sweep', protect: 'Escort / protect' };

    // Assign waypoints with current mission mode and pattern
    setWaypoints(prev => {
      const next = { ...prev };
      for (const { droneId, wpLat, wpLon, label, type } of allowed) {
        next[droneId] = {
          lat: wpLat, lon: wpLon, label, type, status: 'valid',
          mode: missionMode,
          pattern: generatePattern(missionMode, wpLat, wpLon),
        };
      }
      return next;
    });

    // Send reroute commands to the simulation for each assigned vehicle
    for (const { droneId, wpLat, wpLon } of allowed) {
      fetch(`${API_BASE_URL}/dss/sim/command`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          vehicle_id: droneId,
          action: 'reroute',
          params: { lat: wpLat, lon: wpLon, task: TASK_LABEL[missionMode] || missionMode },
        }),
      }).catch(() => {});
    }

    // Fetch maritime routes for water-only vehicles (avoids land masses)
    const [msLat, msLon] = mothershipPos;
    const waterVehicles = allowed.filter(({ type }) => WATER_ONLY.has(type));
    for (const { droneId, wpLat, wpLon } of waterVehicles) {
      fetch(
        `${API_BASE_URL}/dss/maritime-route` +
        `?start_lat=${msLat}&start_lon=${msLon}` +
        `&end_lat=${wpLat}&end_lon=${wpLon}`
      )
        .then(r => r.json())
        .then(data => {
          if (!data.waypoints?.length) return;
          setWaypoints(prev => {
            if (!prev[droneId]) return prev;
            return { ...prev, [droneId]: { ...prev[droneId], route: data.waypoints } };
          });
        })
        .catch(() => { /* keep direct line on failure */ });
    }
  }, [assignments, mothershipPos, missionMode]);

  // ── Mothership move ───────────────────────────────────────────────────
  const onMothershipMove = useCallback((lat, lon) => {
    setMothershipPos([lat, lon]);

    // Re-fetch routes for any water-only vehicles that already have waypoints
    setWaypoints(prev => {
      const waterEntries = Object.entries(prev).filter(([droneId]) => {
        const d = fleet.find(f => f.id === droneId);
        return d && WATER_ONLY.has(d.type);
      });
      if (waterEntries.length === 0) return prev;

      // Clear stale routes while re-fetching
      const next = { ...prev };
      for (const [droneId, wp] of waterEntries) {
        next[droneId] = { ...wp, route: null };
        fetch(
          `${API_BASE_URL}/dss/maritime-route` +
          `?start_lat=${lat}&start_lon=${lon}` +
          `&end_lat=${wp.lat}&end_lon=${wp.lon}`
        )
          .then(r => r.json())
          .then(data => {
            if (!data.waypoints?.length) return;
            setWaypoints(p => {
              if (!p[droneId]) return p;
              return { ...p, [droneId]: { ...p[droneId], route: data.waypoints } };
            });
          })
          .catch(() => {});
      }
      return next;
    });
  }, []);

  const onClearWaypoint = useCallback((droneId) => {
    setWaypoints(prev => { const n = { ...prev }; delete n[droneId]; return n; });
  }, []);

  return (
    <main className="app-shell">
      <LeftSidebar
        mapVehicles={state.map?.vehicles || []}
        teams={teams}
        assignments={assignments}
        alerts={state.alerts || []}
        weather={state.weather}
        onCreateTeam={onCreateTeam}
        onDeleteTeam={onDeleteTeam}
        onAssignDrone={onAssignDrone}
        onUnassignDrone={onUnassignDrone}
      />
      <OperationalMap
        mapState={state.map}
        waypoints={waypoints}
        mothershipPos={mothershipPos}
        missionMode={missionMode}
        onDropToMap={onDropToMap}
        onClearWaypoint={onClearWaypoint}
        onMothershipMove={onMothershipMove}
        onMissionModeChange={setMissionMode}
      />
      <Chat messages={state.chat_messages} error={error} onRefresh={load} />
    </main>
  );
}
