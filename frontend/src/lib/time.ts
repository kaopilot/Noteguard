// Times arrive as UTC ISO-8601 and are displayed in Asia/Singapore (Section 18.3). Singapore has a
// fixed UTC+08:00 offset (no daylight saving), which the cutoff input relies on.
const TZ = 'Asia/Singapore';
const timeFmt = new Intl.DateTimeFormat('en-SG', { timeZone: TZ, hour: '2-digit', minute: '2-digit', hour12: false });
const dateFmt = new Intl.DateTimeFormat('en-SG', { timeZone: TZ, day: 'numeric', month: 'short' });
const partsFmt = new Intl.DateTimeFormat('en-CA', {
  timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
});

export function sgtTime(iso: string): string {
  return timeFmt.format(new Date(iso));
}

export function sgtDateTime(iso: string): string {
  const d = new Date(iso);
  return `${sgtTime(iso)}, ${dateFmt.format(d)}`;
}

/** 'YYYY-MM-DDTHH:MM' in Singapore time, for <input type="datetime-local">. */
export function toSgtInput(iso: string): string {
  const p = Object.fromEntries(partsFmt.formatToParts(new Date(iso)).map((x) => [x.type, x.value]));
  const hour = p.hour === '24' ? '00' : p.hour;
  return `${p.year}-${p.month}-${p.day}T${hour}:${p.minute}`;
}

/** Singapore wall-clock input -> UTC ISO string with 'Z', or null if unparseable. */
export function sgtInputToUtc(value: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) return null;
  const d = new Date(`${value}:00+08:00`);
  return Number.isNaN(d.getTime()) ? null : d.toISOString().replace('.000Z', 'Z');
}

/** Human age such as "2 d 3 h" or "45 min" between `iso` and `now`. */
export function age(iso: string, now: number = Date.now()): string {
  const mins = Math.max(0, Math.floor((now - new Date(iso).getTime()) / 60000));
  if (mins < 60) return `${mins} min`;
  const h = Math.floor(mins / 60);
  if (h < 24) return `${h} h ${mins % 60} min`;
  return `${Math.floor(h / 24)} d ${h % 24} h`;
}
