import { createContext, useContext } from 'react';
import type { Evidence, EncounterView, Flag, SessionView, SourceView } from '../api/types';

/** What the source viewer should open: one version, plus the evidence spans to highlight in it. */
export type SourceTarget = { versionId: string; evidence: readonly Evidence[]; heading?: string };

export interface EncounterCtxValue {
  me: SessionView;
  view: EncounterView;
  staffName: (id: string | null | undefined) => string;
  source: (versionId: string | null | undefined) => SourceView | undefined;
  /** Newest version of the same logical source, when it is not `versionId` itself. */
  newerVersion: (versionId: string) => SourceView | undefined;
  openSource: (target: SourceTarget) => void;
  openFlag: (flagId: string) => void;
  flagById: (flagId: string) => Flag | undefined;
}

export const EncounterCtx = createContext<EncounterCtxValue | null>(null);

export function useEnc(): EncounterCtxValue {
  const v = useContext(EncounterCtx);
  if (!v) throw new Error('EncounterCtx is not provided');
  return v;
}
