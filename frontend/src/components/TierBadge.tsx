import type { Tier } from '../api/types';
import { TIER, type TierShape } from '../lib/labels';

// Tier is always a text label plus a distinct shape; colour only reinforces it (Section 13).
function TierIcon({ shape }: { shape: TierShape }) {
  return (
    <svg className="tier-icon" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false" data-shape={shape}>
      {shape === 'octagon' && <polygon points="5,1 11,1 15,5 15,11 11,15 5,15 1,11 1,5" />}
      {shape === 'triangle' && <polygon points="8,1.5 15,14.5 1,14.5" />}
      {shape === 'circle' && <circle cx="8" cy="8" r="6" />}
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
