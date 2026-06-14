import React from 'react';

export function UAVIcon({ size = 24, color = 'currentColor' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="9.5" y="9.5" width="5" height="5" rx="1.5" fill={color} />
      <line x1="9.5" y1="9.5" x2="5"   y2="5"   stroke={color} strokeWidth="1.8" strokeLinecap="round" />
      <line x1="14.5" y1="9.5" x2="19" y2="5"   stroke={color} strokeWidth="1.8" strokeLinecap="round" />
      <line x1="9.5" y1="14.5" x2="5"  y2="19"  stroke={color} strokeWidth="1.8" strokeLinecap="round" />
      <line x1="14.5" y1="14.5" x2="19" y2="19" stroke={color} strokeWidth="1.8" strokeLinecap="round" />
      <circle cx="4"  cy="4"  r="2.5" stroke={color} strokeWidth="1.4" />
      <circle cx="20" cy="4"  r="2.5" stroke={color} strokeWidth="1.4" />
      <circle cx="4"  cy="20" r="2.5" stroke={color} strokeWidth="1.4" />
      <circle cx="20" cy="20" r="2.5" stroke={color} strokeWidth="1.4" />
    </svg>
  );
}

export function USVIcon({ size = 24, color = 'currentColor' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M2 15 L5 10 L19 10 L22 15 Q12 20 2 15 Z" stroke={color} strokeWidth="1.5" strokeLinejoin="round" fill={color} fillOpacity="0.15" />
      <rect x="8.5" y="7" width="7" height="3.5" rx="1" stroke={color} strokeWidth="1.4" />
      <line x1="12" y1="7" x2="12" y2="4" stroke={color} strokeWidth="1.4" strokeLinecap="round" />
      <line x1="12" y1="4" x2="15" y2="6" stroke={color} strokeWidth="1" strokeLinecap="round" />
    </svg>
  );
}

export function UUVIcon({ size = 24, color = 'currentColor' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <ellipse cx="11" cy="12" rx="8" ry="4.5" stroke={color} strokeWidth="1.5" fill={color} fillOpacity="0.15" />
      <path d="M19 12 L23 12" stroke={color} strokeWidth="1.4" strokeLinecap="round" />
      <path d="M3 12 L1 8.5 L1 15.5 Z" fill={color} />
      <path d="M6.5 7.5 L9 7.5 L9 12" stroke={color} strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M6.5 16.5 L9 16.5 L9 12" stroke={color} strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function DroneIcon({ type, ...props }) {
  if (type === 'air')        return <UAVIcon {...props} />;
  if (type === 'surface')    return <USVIcon {...props} />;
  if (type === 'subsurface') return <UUVIcon {...props} />;
  return null;
}
