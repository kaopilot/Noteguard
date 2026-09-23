import { useState, type ReactNode } from 'react';
import { CONTRACT } from '../api/contract-data.gen';
import { decisionActionValues, tierValues } from '../api/schema.gen';
import type { ClosureView, Flag } from '../api/types';
import { offeredActions } from '../lib/permissions';
import { TIER } from '../lib/labels';
import { useEnc } from './ctx';
import { FlagCard } from './FlagCard';

// A flag is "decided" when the contract's transition table offers no further move from its state
// (read from contract data, not hand-listed). Decided flags sit behind the history toggle (L14).
const MOVABLE_STATES = new Set(
  Object.values(CONTRACT.decisions.transitions as Record<string, Record<string, string>>).flatMap((m) => Object.keys(m)),
);

export function FlagList({ flags, closure, focusFlagId, onDecide, decideSlot }: {
  flags: readonly Flag[];
  closure: ClosureView | null;
  focusFlagId: string | null;
  onDecide: (f: Flag) => void;
  /** Wide screens: the decision form renders inside the card being decided (inline, Section 13). */
  decideSlot?: (f: Flag) => ReactNode;
}) {
  const { me, view } = useEnc();
  const [showDecided, setShowDecided] = useState(false);
  const blockers = new Set(closure?.tier1_blockers.map((b) => b.flag_id) ?? []);
  const decidedIds = new Set(closure?.decisions.map((d) => d.flag_id) ?? []);
  const active = flags.filter((f) => MOVABLE_STATES.has(f.state));
  const decided = flags.filter((f) => !MOVABLE_STATES.has(f.state));
  const shown = showDecided ? flags : active;

  return (
    <section className="flag-list" aria-label="Flags">
      {tierValues.map((tier) => {
        const group = shown.filter((f) => f.tier === tier);
        if (group.length === 0) return null;
        return (
          <section key={tier} className={`tier-group tier-group-${tier}`} id={`tier-group-${tier}`}>
            <h2 className="tier-group-title">{TIER[tier].label}: {TIER[tier].hint.toLowerCase()}</h2>
            {group.map((f) => (
              <FlagCard
                key={f.flag_id}
                flag={f}
                blocksClosure={blockers.has(f.flag_id)}
                canDecide={offeredActions(me, view, f, decisionActionValues).length > 0}
                onDecide={onDecide}
                focused={f.flag_id === focusFlagId}
                slot={decideSlot?.(f)}
                decided={decidedIds.has(f.flag_id)}
              />
            ))}
          </section>
        );
      })}
      {active.length === 0 && !showDecided && <p className="note note-quiet">No flags need a decision at this cutoff.</p>}
      {decided.length > 0 && (
        <button type="button" className="btn btn-quiet history-toggle" aria-pressed={showDecided} onClick={() => setShowDecided(!showDecided)}>
          {showDecided ? 'Hide decided flags' : `Show decided flags (${decided.length})`}
        </button>
      )}
    </section>
  );
}
