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

export function fmtTime(iso: string): string {
	return iso.length >= 16 ? iso.slice(11, 16) : iso;
}

export function todayIso(): string {
	const now = new Date();
	const y = now.getFullYear();
	const m = String(now.getMonth() + 1).padStart(2, '0');
	const d = String(now.getDate()).padStart(2, '0');
	return `${y}-${m}-${d}`;
}
