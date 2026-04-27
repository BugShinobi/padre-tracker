import type {
	OverviewResponse,
	DayResponse,
	RangeResponse,
	TokenResponse
} from './types';

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
	deleteToken: async (ca: string) => {
		const res = await fetch(`/api/token/${encodeURIComponent(ca)}`, { method: 'DELETE' });
		if (!res.ok) throw new ApiError(`delete ${ca} → ${res.status}`, res.status);
		return res.json() as Promise<{ ok: boolean; contract_address: string; deleted_rows: number }>;
	}
};

export {
	fmtMc,
	fmtPct,
	fmtPrice,
	fmtNum,
	shortCa,
	fmtAge,
	fmtTime,
	parseMc,
	todayIso,
	daysAgoIso
} from './format';
