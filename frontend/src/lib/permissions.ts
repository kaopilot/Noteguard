// Hide-only permission helper (Section 18.4 rule 4). It reads the frozen permission matrix and
// transition table from the generated contract data to decide which controls to SHOW. The server
// re-checks everything (route and store layers); a hidden control is a convenience, never security.
import { CONTRACT } from '../api/contract-data.gen';
import type { DecisionAction, EncounterView, Flag, SessionView } from '../api/types';

type PermissionRow = (typeof CONTRACT.permissions)[number];
type Relation = PermissionRow['relations_any'][number];

function relationsOf(me: SessionView, view: EncounterView, flag?: Flag): Set<Relation> {
  const out = new Set<Relation>();
  const member = view.memberships.some((m) => m.staff_id === me.staff_id);
  if (member) out.add('care_team_member');
  if (view.encounter.responsible_clinician_id === me.staff_id) out.add('responsible_clinician');
  if (flag && flag.owner_staff_id === me.staff_id) out.add('flag_owner');
  return out;
}

function allowed(action: string, me: SessionView, view: EncounterView, tier: number | null, flag?: Flag): boolean {
  const rel = relationsOf(me, view, flag);
  return CONTRACT.permissions.some((row) => {
    if (row.action !== action) return false;
    if (!(row.roles as readonly string[]).includes(me.role)) return false;
    if (row.tiers !== null && (tier === null || !(row.tiers as readonly number[]).includes(tier))) return false;
    return row.relations_any.length === 0 || row.relations_any.some((r) => rel.has(r));
  });
}

/** Whether the contract's transition table has a move for `action` from the flag's current state. */
export function hasTransition(action: DecisionAction, flag: Flag): boolean {
  const table = CONTRACT.decisions.transitions as Record<string, Record<string, string>>;
  return table[action]?.[flag.state] !== undefined;
}

/** Decision actions to offer on this flag (hide-only). */
export function offeredActions(me: SessionView, view: EncounterView, flag: Flag, all: readonly DecisionAction[]): DecisionAction[] {
  return all.filter((a) => hasTransition(a, flag) && allowed(`decide_${a}`, me, view, flag.tier, flag));
}

export function mayCloseEncounter(me: SessionView, view: EncounterView): boolean {
  return allowed('close_encounter', me, view, null);
}
