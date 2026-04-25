import type { OverviewResponse, DayResponse } from './types';

class ApiError extends Error {
	constructor(
		message: string,
		readonly status: number
	) {
		super(message);
	}
}

async function getJson<T>(url: string): Promise<T> {
	const res = await fetch(url);
	if (!res.ok) throw new ApiError(`${url} → ${res.status}`, res.status);
	return res.json();
}

export const api = {
	overview: () => getJson<OverviewResponse>('/api/overview'),
	day: (params: { d?: string; page?: number; pageSize?: number; sort?: string }) => {
		const q = new URLSearchParams();
		if (params.d) q.set('d', params.d);
		if (params.page) q.set('page', String(params.page));
		if (params.pageSize) q.set('page_size', String(params.pageSize));
		if (params.sort) q.set('sort', params.sort);
		return getJson<DayResponse>(`/api/day?${q}`);
	}
};

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

export function shortCa(ca: string): string {
	return ca.length > 10 ? `${ca.slice(0, 4)}…${ca.slice(-4)}` : ca;
}
