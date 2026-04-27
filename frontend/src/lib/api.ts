import type {
	OverviewResponse,
	DayResponse,
	RangeResponse,
	TokenResponse,
	TokenStatus,
	StatusView
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
	status?: StatusView;
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
	if (p.status && p.status !== 'active') q.set('status', p.status);
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
	setTokenStatus: async (ca: string, status: TokenStatus) => {
		const res = await fetch(`/api/token/${encodeURIComponent(ca)}/status`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ status })
		});
		if (!res.ok) throw new ApiError(`set status ${ca} → ${res.status}`, res.status);
		return res.json() as Promise<{ ok: boolean; contract_address: string; status: TokenStatus }>;
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
	todayIso,
	daysAgoIso
} from './format';
