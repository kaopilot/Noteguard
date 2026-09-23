import type { Tier } from '../api/types';
import { TIER, type TierShape } from '../lib/labels';

// Tier is always a text label plus a distinct shape; colour only reinforces it (Section 13).
function TierIcon({ shape }: { shape: TierShape }) {
  return (
    <svg className="tier-icon" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false" data-shape={shape}>
      {shape === 'octagon' && (
        <>
          <polygon points="4.7,0.5 11.3,0.5 15.5,4.7 15.5,11.3 11.3,15.5 4.7,15.5 0.5,11.3 0.5,4.7" />
          <rect x="3.5" y="6.6" width="9" height="2.8" className="tier-icon-knock" />
        </>
      )}
      {shape === 'triangle' && <polygon points="8,1 15.5,14.8 0.5,14.8" />}
      {shape === 'circle' && <circle cx="8" cy="8" r="5.5" className="tier-icon-ring" />}
    </svg>
  );
}

export function TierBadge({ tier }: { tier: Tier }) {
  const t = TIER[tier];
  return (
    <span className={`tier-badge tier-badge-${tier}`} title={t.hint} data-testid="tier-badge">
      <TierIcon shape={t.shape} />
      <span className="tier-badge-label">{t.label}</span>
    </span>
  );
}
