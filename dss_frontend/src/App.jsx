import React, { useCallback, useEffect, useState } from 'react';
import OperationalMap from './Map.jsx';
import Chat from './Chat.jsx';
import LeftSidebar from './LeftSidebar.jsx';
import fleet from './drones.json';

export const API_BASE_URL = import.meta.env.VITE_DSS_API_BASE_URL || 'http://localhost:8001';

const emptyState = {
  map: { vehicles: [], events: [], contacts: [], zones: [], uncertainty_regions: [] },
  chat_messages: [],
};

const WATER_ONLY = new Set(['surface', 'subsurface']);

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

  // ── DSS polling ───────────────────────────────────────────────────────
  async function load() {
    try {
      const res = await fetch(`${API_BASE_URL}/dss/operator-state`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setState({ ...emptyState, ...data });
      setError(null);
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

    // Assign waypoints only for allowed vehicles
    setWaypoints(prev => {
      const next = { ...prev };
      for (const { droneId, wpLat, wpLon, label } of allowed) {
        next[droneId] = { lat: wpLat, lon: wpLon, label, status: 'valid' };
      }
      return next;
    });

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
  }, [assignments, mothershipPos]);

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
        onCreateTeam={onCreateTeam}
        onDeleteTeam={onDeleteTeam}
        onAssignDrone={onAssignDrone}
        onUnassignDrone={onUnassignDrone}
      />
      <OperationalMap
        mapState={state.map}
        waypoints={waypoints}
        mothershipPos={mothershipPos}
        onDropToMap={onDropToMap}
        onClearWaypoint={onClearWaypoint}
        onMothershipMove={onMothershipMove}
      />
      <Chat messages={state.chat_messages} error={error} onRefresh={load} />
    </main>
  );
}
