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

export type DayParams = {
	d?: string;
	page?: number;
	pageSize?: number;
	search?: string;
	sort?: string;
	launchpad?: string[];
	groups?: string[];
};

export const api = {
	overview: () => getJson<OverviewResponse>('/api/overview'),
	day: (params: DayParams = {}) => {
		const q = new URLSearchParams();
		if (params.d) q.set('d', params.d);
		if (params.page) q.set('page', String(params.page));
		if (params.pageSize) q.set('page_size', String(params.pageSize));
		if (params.search) q.set('search', params.search);
		if (params.sort) q.set('sort', params.sort);
		if (params.launchpad?.length) q.set('launchpad', params.launchpad.join(','));
		if (params.groups?.length) q.set('groups', params.groups.join(','));
		return getJson<DayResponse>(`/api/day?${q}`);
	}
};

export { fmtMc, fmtPct, fmtPrice, fmtNum, shortCa, fmtAge, fmtTime, todayIso } from './format';
