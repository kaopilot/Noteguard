// Test double of the Noteguard API for jsdom tests, built from the repo's golden fixtures and the
// contract route templates. Mirrors the B2 API with the stub engine: 404 before the first run, and
// 501 for bubbles, glance and summary after any decision. It is a double for UI tests only.
import clinic from '../../fixtures/encounters/clinic.json';
import encA1 from '../../fixtures/encounters/ENC-A1.json';
import g1130 from '../../fixtures/expected/ENC-A1_1130.json';
import g1600 from '../../fixtures/expected/ENC-A1_1600.json';
import g1600rerun from '../../fixtures/expected/ENC-A1_1600_rerun.json';
import { CONTRACT } from '../src/api/contract-data.gen';

type Json = any; // eslint-disable-line @typescript-eslint/no-explicit-any
export type Req = { method: string; url: string; headers: Record<string, string>; body: Json };

const GOLDENS: Json[] = [g1130, g1600, g1600rerun];
const ENC: Json = encA1;
export const A1 = ENC.encounter.encounter_id as string;
export const TOKEN = 'tok-TEST-9f8e7d';

function matcher(template: string) {
  return new RegExp('^' + template.replace(/\{(\w+)\}/g, '(?<$1>[^/]+)') + '$');
}
const ROUTES = Object.entries(CONTRACT.routes).map(([k, t]) => [k, matcher(t)] as const);

export function sourceViews(enc: Json) {
  const src = new Map(enc.sources.map((s: Json) => [s.source_id, s]));
  const ext = new Map(enc.extractions.map((e: Json) => [e.source_version_id, e]));
  return enc.versions
    .map((v: Json) => {
      const s: Json = src.get(v.source_id);
      const e: Json = ext.get(v.source_version_id);
      return {
        source_id: s.source_id, note_version_id: v.source_version_id, version: v.version, supersedes_version_id: v.supersedes_version_id,
        title: s.title, source_type: s.source_type, discipline: s.discipline, author_staff_id: s.author_staff_id,
        source_time: s.source_time, version_time: v.version_time, received_at: v.received_at, sha256: v.sha256,
        extraction_status: e.status, extraction_note: e.note, page_count: e.pages.length,
      };
    })
    .sort((a: Json, b: Json) => (a.source_time + a.received_at + a.note_version_id).localeCompare(b.source_time + b.received_at + b.note_version_id));
}

export function textOf(versionId: string): Json {
  return ENC.extractions.find((e: Json) => e.source_version_id === versionId);
}

// jsdom's File has no arrayBuffer(); FileReader is available (browsers have both).
function readBytes(blob: Blob): Promise<Uint8Array> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(new Uint8Array(r.result as ArrayBuffer));
    r.onerror = () => reject(r.error);
    r.readAsArrayBuffer(blob);
  });
}

export function createFakeApi() {
  const requests: Req[] = [];
  let session: Json = null;
  let current: Json = null;
  let flags: Json[] = [];
  const decisions: Json[] = [];
  const outage = { on: false, status: 503 };
  const network = { failNextPosts: 0 };
  const added: { view: Json; text: string; key: string }[] = [];
  const allSources = () => [...sourceViews(ENC), ...added.map((a) => a.view)];
  const members = new Set(ENC.memberships.map((m: Json) => m.staff_id));

  // Mirrors B2's intake rules (store._check_source_meta / _add_version) closely enough for UI tests.
  const addSource = (body: Json, type: string, bytes: Uint8Array | null): Response => {
    if (!members.has(body.author_staff_id)) return reply(422, { error_code: 'validation_failed' });
    if (type === 'pdf' && !(bytes && String.fromCharCode(...bytes.slice(0, 5)) === '%PDF-')) return reply(415, { error_code: 'pdf_not_a_pdf' });
    const content = type === 'pdf' ? `pdf:${bytes?.length}` : body.text;
    const replay = added.find((a) => a.key === body.idempotency_key);
    if (replay) return replay.text === content ? reply(200, replay.view) : reply(409, { error_code: 'idempotency_conflict' });
    let version = 1;
    let sourceId = `added-${added.length + 1}`;
    let supersedes: string | null = null;
    if (body.source_id) {
      const versions = allSources().filter((s: Json) => s.source_id === body.source_id);
      if (versions.length === 0) return reply(404, { error_code: 'not_found' });
      const cur = versions.sort((a: Json, b: Json) => b.version - a.version)[0];
      const same = cur.title === body.title && cur.author_staff_id === body.author_staff_id && cur.discipline === body.discipline
        && new Date(cur.source_time).getTime() === new Date(body.source_time).getTime() && cur.source_type === type;
      if (!same || body.identifier_namespace !== undefined) return reply(422, { error_code: 'validation_failed' });
      version = cur.version + 1;
      sourceId = cur.source_id;
      supersedes = cur.note_version_id;
    }
    const now = new Date(Date.now() - 1).toISOString(); // B2 keeps sub-second precision
    const slow = type === 'pdf' && String(body.file_name).includes('slow');
    const view = { source_id: sourceId, note_version_id: `added-v${added.length + 1}`, version, supersedes_version_id: supersedes,
      title: body.title, source_type: type, discipline: body.discipline, author_staff_id: body.author_staff_id,
      source_time: body.source_time, version_time: now, received_at: now, sha256: 'test',
      extraction_status: type === 'pdf' ? (slow ? 'failed' : 'complete') : 'not_applicable',
      extraction_note: slow ? 'extraction timed out' : null, page_count: type === 'pdf' ? 1 : 0 };
    added.push({ view, text: content, key: body.idempotency_key });
    return slow ? reply(422, { error_code: 'pdf_extraction_timeout' }) : reply(201, view);
  };

  const reply = (status: number, body?: Json) =>
    new Response(body === undefined ? null : JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'private, no-store' } });

  const handle = (method: string, path: string, body: Json): Response => {
    const hit = ROUTES.map(([k, re]) => [k, re.exec(path)] as const).find(([, m]) => m !== null);
    if (!hit) return reply(404, { error_code: 'not_found' });
    const [route, m] = hit;
    const p = m?.groups ?? {};
    if (route === 'SESSION') {
      if (method === 'POST') {
        const s: Json = clinic.staff.find((x: Json) => x.staff_id === body.staff_id);
        session = { staff_id: s.staff_id, display_name: s.display_name, role: s.role, discipline: s.discipline };
        return reply(200, session);
      }
      if (method === 'DELETE') { session = null; return reply(204); }
      return session ? reply(200, session) : reply(401, { error_code: 'unauthenticated' });
    }
    if (!session) return reply(401, { error_code: 'unauthenticated' });
    if (outage.on && method === 'GET' && route !== 'ENCOUNTER') return reply(outage.status, outage.status === 403 ? { error_code: 'forbidden_role' } : null);
    if (route === 'WORKSPACES') return reply(200, { workspace_token: TOKEN, encounter_ids: [A1], expires_at: '2026-09-23T12:00:00Z', single_process_store: true });
    if (route === 'WORKSPACE_CURRENT') { current = null; flags = []; decisions.length = 0; return reply(204); }
    if (route === 'ENCOUNTERS') {
      return reply(200, [{ encounter_id: A1, encounter_ref: ENC.encounter.encounter_ref, patient_label: ENC.patient.display_label, setting: ENC.encounter.setting, responsible_clinician_id: ENC.encounter.responsible_clinician_id }]);
    }
    if (p.encounter_id && p.encounter_id !== A1) return reply(404, { error_code: 'not_found' });
    if (route === 'ENCOUNTER') {
      return reply(200, { encounter: ENC.encounter, patient_label: ENC.patient.display_label, staff: ENC.staff, memberships: ENC.memberships, sources: allSources() });
    }
    if (route === 'SOURCES') return addSource(body, 'pasted_text', null);
    if (route === 'SOURCES_PDF') return addSource(body, 'pdf', body.file_bytes);
    if (route === 'SOURCE_TEXT') {
      const e = textOf(p.source_version_id ?? '');
      return e ? reply(200, { note_version_id: e.source_version_id, extraction_status: e.status, text: e.text, pages: e.pages }) : reply(404, { error_code: 'not_found' });
    }
    if (route === 'CHECK_RUNS') {
      const prior = current ? current.scenario : null;
      current = GOLDENS.find((g) => g.cutoff === body.cutoff && (g.prior_scenario ?? null) === prior);
      if (!current) return reply(501, { error_code: 'not_implemented' });
      flags = current.flags.map((f: Json) => ({ ...f }));
      decisions.length = 0;
      return reply(200, { run: current.run, flags, changes: current.required_changes });
    }
    if (!current) return reply(404, { error_code: 'not_found' });
    const decided = decisions.length > 0;
    switch (route) {
      case 'CHECK_RUN_LATEST': return reply(200, { run: current.run, flags, changes: current.required_changes });
      case 'FLAGS': return reply(200, flags);
      case 'BUBBLES': return decided ? reply(501, { error_code: 'not_implemented' }) : reply(200, { cutoff: current.cutoff, bubbles: current.bubbles, ai_status: 'disabled' });
      case 'GLANCE': return decided ? reply(501, { error_code: 'not_implemented' }) : reply(200, current.glance);
      case 'SUMMARY': return decided ? reply(501, { error_code: 'not_implemented' }) : reply(200, current.summary);
      case 'CLOSURE':
        if (method === 'POST') return reply(409, { error_code: 'closure_blocked' });
        return reply(200, { ...current.closure, decisions });
      case 'FLAG_DECISIONS': {
        const f = flags.find((x) => x.flag_id === p.flag_id);
        if (!f) return reply(404, { error_code: 'not_found' });
        if (body.expected_revision !== f.revision) {
          const last = decisions[decisions.length - 1];
          return reply(409, { error_code: 'stale_revision', current_revision: f.revision, current_state: f.state,
            last_decision_action: last?.action ?? null, last_decision_actor_staff_id: last?.actor_staff_id ?? null, last_decision_at: last?.at ?? null });
        }
        const to = (CONTRACT.decisions.transitions as Json)[body.action]?.[f.state];
        if (!to) return reply(409, { error_code: 'invalid_transition' });
        const d = { decision_id: `dec-${decisions.length + 1}`, flag_id: f.flag_id, encounter_id: A1, expected_revision: f.revision,
          resulting_revision: f.revision + 1, action: body.action, actor_staff_id: session.staff_id, actor_role: session.role,
          reason_code: body.reason_code ?? null, rationale_text: null, new_owner_staff_id: null, edit_field: null, prepared_check: null,
          adjudicated_evidence: [], from_state: f.state, to_state: to, at: '2026-09-21T08:05:00Z' };
        decisions.push(d);
        Object.assign(f, { state: to, revision: f.revision + 1 });
        return reply(200, { flag: f, revisions: [], decisions: [d] });
      }
      default: return reply(501, { error_code: 'not_implemented' });
    }
  };

  const fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const method = (init?.method ?? 'GET').toUpperCase();
    const headers = Object.fromEntries(Object.entries((init?.headers ?? {}) as Record<string, string>).map(([k, v]) => [k.toLowerCase(), v]));
    let body: Json = typeof init?.body === 'string' ? JSON.parse(init.body) : null;
    if (typeof FormData !== 'undefined' && init?.body instanceof FormData) {
      body = {};
      for (const [k, v] of init.body.entries()) {
        if (typeof v === 'string') body[k] = v;
        else { body.file_name = v.name; body.file_bytes = await readBytes(v); }
      }
    }
    requests.push({ method, url, headers, body });
    if (method === 'POST' && network.failNextPosts > 0) {
      network.failNextPosts -= 1;
      throw new TypeError('network down');
    }
    return handle(method, new URL(url, 'http://ng.test').pathname, body);
  };
  return { fetch, requests, outage, network, added };
}
