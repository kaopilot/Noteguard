// Tier is a text label plus a distinct shape, never colour alone (Section 13; B3 owned test
// test_tier_labels_not_colour_only). Mutation spot-check: remove the tier-badge-label span, or give
// two tiers the same shape -> these cases fail.
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { render, screen, within } from '@testing-library/react';
import { expect, test } from 'vitest';
import g1600 from '../../fixtures/expected/ENC-A1_1600.json';
import type { EncounterView, Flag, SessionView } from '../src/api/types';
import { EncounterCtx, type EncounterCtxValue } from '../src/components/ctx';
import { FlagCard } from '../src/components/FlagCard';
import { TierBadge } from '../src/components/TierBadge';
import { A1, sourceViews } from './fakeApi';
import encA1 from '../../fixtures/encounters/ENC-A1.json';

test('each tier badge shows its tier as visible text with a distinct shape', () => {
  const shapes = new Set<string>();
  for (const tier of [1, 2, 3] as const) {
    const { container, unmount } = render(<TierBadge tier={tier} />);
    const label = screen.getByText(`Tier ${tier}`);
    expect(label.closest('[aria-hidden="true"]')).toBeNull();
    expect(label.className).not.toMatch(/sr-only|visually-hidden/);
    const icon = container.querySelector('svg.tier-icon');
    expect(icon?.getAttribute('aria-hidden')).toBe('true');
    shapes.add(icon?.getAttribute('data-shape') ?? '');
    unmount();
  }
  expect(shapes.size).toBe(3);
  const css = readFileSync(resolve(__dirname, '..', 'src', 'styles.css'), 'utf-8');
  expect(css).not.toMatch(/\.tier-badge-label[^{]*\{[^}]*(display:\s*none|visibility:\s*hidden|font-size:\s*0)/);
});

test('flag cards carry the tier label in their header for every tier', () => {
  const enc = encA1 as unknown as { encounter: EncounterView['encounter']; staff: EncounterView['staff']; memberships: EncounterView['memberships']; patient: { display_label: string } };
  const view = { encounter: enc.encounter, patient_label: enc.patient.display_label, staff: enc.staff, memberships: enc.memberships, sources: sourceViews(encA1) } as EncounterView;
  const me: SessionView = { staff_id: enc.encounter.responsible_clinician_id ?? '', display_name: 'Dr Lim', role: 'clinician', discipline: 'clinician' };
  const ctx: EncounterCtxValue = {
    me, view, staffName: () => 'Someone', source: () => undefined, newerVersion: () => undefined,
    openSource: () => undefined, openFlag: () => undefined, flagById: () => undefined,
  };
  const flags = (g1600 as unknown as { flags: Flag[] }).flags;
  expect(view.encounter.encounter_id).toBe(A1);
  for (const tier of [1, 2, 3] as const) {
    const flag = flags.find((f) => f.tier === tier);
    expect(flag).toBeDefined();
    const { unmount } = render(
      <EncounterCtx.Provider value={ctx}>
        <FlagCard flag={flag as Flag} blocksClosure={false} canDecide={false} onDecide={() => undefined} focused={false} />
      </EncounterCtx.Provider>,
    );
    const card = screen.getByRole('article', { name: (flag as Flag).title });
    expect(within(card.querySelector('header') as HTMLElement).getByText(`Tier ${tier}`)).toBeTruthy();
    unmount();
  }
});
