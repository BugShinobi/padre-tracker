export function fmtMc(v: number | null | undefined): string {
	if (v == null) return '—';
	if (v >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
	if (v >= 1e6) return `$${(v / 1e6).toFixed(2)}M`;
	if (v >= 1e3) return `$${(v / 1e3).toFixed(1)}K`;
	return `$${v.toFixed(0)}`;
}

export function fmtPct(v: number | null | undefined): string {
	if (v == null) return '—';
	const sign = v >= 0 ? '+' : '';
	return `${sign}${v.toFixed(1)}%`;
}

export function fmtPrice(v: number | null | undefined): string {
	if (v == null) return '—';
	if (v >= 1) return `$${v.toFixed(3)}`;
	if (v >= 0.001) return `$${v.toFixed(5)}`;
	return `$${v.toExponential(2)}`;
}

export function fmtNum(v: number | null | undefined): string {
	if (v == null) return '—';
	return v.toLocaleString('en-US');
}

export function shortCa(ca: string): string {
	return ca.length > 10 ? `${ca.slice(0, 4)}…${ca.slice(-4)}` : ca;
}

export function fmtAge(creationTs: number | null | undefined, nowMs: number = Date.now()): string {
	if (!creationTs) return '—';
	const ageSec = Math.max(0, Math.floor(nowMs / 1000) - creationTs);
	const days = Math.floor(ageSec / 86400);
	const hours = Math.floor((ageSec % 86400) / 3600);
	const mins = Math.floor((ageSec % 3600) / 60);
	if (days >= 1) return `${days}d ${hours}h`;
	if (hours >= 1) return `${hours}h ${mins}m`;
	return `${mins}m`;
}

// Backend writes naive `datetime.now().isoformat()` on a server set to Etc/UTC.
// So timestamps are UTC moments without a tz marker — append 'Z' before parsing.
function parseUtcIso(iso: string): Date | null {
	if (!iso) return null;
	const s = iso.includes('T') ? iso : iso.replace(' ', 'T');
	const withTz = /[Zz]|[+-]\d{2}:?\d{2}$/.test(s) ? s : s + 'Z';
	const d = new Date(withTz);
	return isNaN(d.getTime()) ? null : d;
}

const ROME_TIME = new Intl.DateTimeFormat('en-GB', {
	timeZone: 'Europe/Rome',
	hour: '2-digit',
	minute: '2-digit',
	hour12: false
});

const ROME_DATETIME = new Intl.DateTimeFormat('en-GB', {
	timeZone: 'Europe/Rome',
	month: '2-digit',
	day: '2-digit',
	hour: '2-digit',
	minute: '2-digit',
	hour12: false
});

export function fmtTime(iso: string): string {
	const d = parseUtcIso(iso);
	return d ? ROME_TIME.format(d) : iso;
}

export function fmtDateTime(iso: string): string {
	const d = parseUtcIso(iso);
	if (!d) return iso;
	const parts = ROME_DATETIME.formatToParts(d);
	const get = (t: string) => parts.find((p) => p.type === t)?.value ?? '';
	return `${get('month')}-${get('day')} ${get('hour')}:${get('minute')}`;
}

export function todayIso(): string {
	return toIso(new Date());
}

export function daysAgoIso(days: number): string {
	const dt = new Date();
	dt.setDate(dt.getDate() - days);
	return toIso(dt);
}

function toIso(dt: Date): string {
	const y = dt.getFullYear();
	const m = String(dt.getMonth() + 1).padStart(2, '0');
	const d = String(dt.getDate()).padStart(2, '0');
	return `${y}-${m}-${d}`;
}
