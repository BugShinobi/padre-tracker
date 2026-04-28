import type {
	OverviewResponse,
	DayResponse,
	RangeResponse,
	TokenResponse,
	EnrichedRow,
	AlertsResponse,
	AlertsStatsResponse,
	AlertsSummaryResponse
} from './types';

export type TopGroupsResponse = {
	ready: boolean;
	groups: { name: string; count: number }[];
	windowDays: number;
};

export type TokenNoteResponse = {
	note: string;
	updated_at: string | null;
};

export type WatchlistCasResponse = { cas: string[] };
export type WatchlistResponse = { ready: boolean; data: EnrichedRow[] };

export type AlertsParams = {
	page?: number;
	pageSize?: number;
	type?: string;
	ticker?: string;
	actor?: string;
	source?: string;
	minUsd?: number;
	maxUsd?: number;
	minMc?: number;
	maxMc?: number;
	from?: string;
	to?: string;
};

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

type ListBaseParams = {
	page?: number;
	pageSize?: number;
	search?: string;
	sort?: string;
	launchpad?: string[];
	groups?: string[];
	minHolders?: number;
	mcMin?: number;
	mcMax?: number;
};

export type DayParams = ListBaseParams & { d?: string };
export type RangeParams = ListBaseParams & { from?: string; to?: string };

function buildList(q: URLSearchParams, p: ListBaseParams) {
	if (p.page) q.set('page', String(p.page));
	if (p.pageSize) q.set('page_size', String(p.pageSize));
	if (p.search) q.set('search', p.search);
	if (p.sort) q.set('sort', p.sort);
	if (p.launchpad?.length) q.set('launchpad', p.launchpad.join(','));
	if (p.groups?.length) q.set('groups', p.groups.join(','));
	if (p.minHolders && p.minHolders > 0) q.set('min_holders', String(p.minHolders));
	if (p.mcMin && p.mcMin > 0) q.set('mc_min', String(p.mcMin));
	if (p.mcMax && p.mcMax > 0) q.set('mc_max', String(p.mcMax));
}

export const api = {
	overview: () => getJson<OverviewResponse>('/api/overview'),
	day: (params: DayParams = {}) => {
		const q = new URLSearchParams();
		if (params.d) q.set('d', params.d);
		buildList(q, params);
		return getJson<DayResponse>(`/api/day?${q}`);
	},
	range: (params: RangeParams = {}) => {
		const q = new URLSearchParams();
		if (params.from) q.set('from', params.from);
		if (params.to) q.set('to', params.to);
		buildList(q, params);
		return getJson<RangeResponse>(`/api/range?${q}`);
	},
	token: (ca: string) => getJson<TokenResponse>(`/api/token/${encodeURIComponent(ca)}`),
	topGroups: (days = 1, limit = 15) =>
		getJson<TopGroupsResponse>(`/api/groups/top?days=${days}&limit=${limit}`),
	deleteToken: async (ca: string) => {
		const res = await fetch(`/api/token/${encodeURIComponent(ca)}`, { method: 'DELETE' });
		if (!res.ok) throw new ApiError(`delete ${ca} → ${res.status}`, res.status);
		return res.json() as Promise<{ ok: boolean; contract_address: string; deleted_rows: number }>;
	},
	getNote: (ca: string) =>
		getJson<TokenNoteResponse>(`/api/token/${encodeURIComponent(ca)}/note`),
	saveNote: async (ca: string, note: string) => {
		const res = await fetch(`/api/token/${encodeURIComponent(ca)}/note`, {
			method: 'PUT',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ note })
		});
		if (!res.ok) throw new ApiError(`save note ${ca} → ${res.status}`, res.status);
		return res.json() as Promise<TokenNoteResponse>;
	},
	watchlist: () => getJson<WatchlistResponse>('/api/watchlist'),
	getWatchlistCas: () => getJson<WatchlistCasResponse>('/api/watchlist/cas'),
	addToWatchlist: async (ca: string) => {
		const res = await fetch(`/api/watchlist/${encodeURIComponent(ca)}`, { method: 'POST' });
		if (!res.ok) throw new ApiError(`watchlist add ${ca} → ${res.status}`, res.status);
		return res.json();
	},
	removeFromWatchlist: async (ca: string) => {
		const res = await fetch(`/api/watchlist/${encodeURIComponent(ca)}`, { method: 'DELETE' });
		if (!res.ok) throw new ApiError(`watchlist remove ${ca} → ${res.status}`, res.status);
		return res.json();
	},
	alerts: (params: AlertsParams = {}) => {
		const q = new URLSearchParams();
		if (params.page) q.set('page', String(params.page));
		if (params.pageSize) q.set('page_size', String(params.pageSize));
		if (params.type && params.type !== 'all') q.set('type', params.type);
		if (params.ticker) q.set('ticker', params.ticker);
		if (params.actor) q.set('actor', params.actor);
		if (params.source) q.set('source', params.source);
		if (params.minUsd != null) q.set('min_usd', String(params.minUsd));
		if (params.maxUsd != null) q.set('max_usd', String(params.maxUsd));
		if (params.minMc != null) q.set('min_mc', String(params.minMc));
		if (params.maxMc != null) q.set('max_mc', String(params.maxMc));
		if (params.from) q.set('from', params.from);
		if (params.to) q.set('to', params.to);
		return getJson<AlertsResponse>(`/api/alerts?${q}`);
	},
	alertsSummary: (params: AlertsParams = {}) => {
		const q = new URLSearchParams();
		if (params.type && params.type !== 'all') q.set('type', params.type);
		if (params.ticker) q.set('ticker', params.ticker);
		if (params.actor) q.set('actor', params.actor);
		if (params.source) q.set('source', params.source);
		if (params.minUsd != null) q.set('min_usd', String(params.minUsd));
		if (params.maxUsd != null) q.set('max_usd', String(params.maxUsd));
		if (params.minMc != null) q.set('min_mc', String(params.minMc));
		if (params.maxMc != null) q.set('max_mc', String(params.maxMc));
		if (params.from) q.set('from', params.from);
		if (params.to) q.set('to', params.to);
		return getJson<AlertsSummaryResponse>(`/api/alerts/summary?${q}`);
	},
	alertsStats: () => getJson<AlertsStatsResponse>('/api/alerts/stats')
};

export {
	fmtMc,
	fmtPct,
	fmtPrice,
	fmtNum,
	shortCa,
	fmtAge,
	fmtTime,
	fmtDateTime,
	parseMc,
	todayIso,
	daysAgoIso
} from './format';
