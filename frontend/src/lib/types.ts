export type DayCount = { tokens: number; total_calls: number };

export type Delta = { str: string; class: 'pos' | 'neg' | 'flat' };

export type WeekDay = { date: string; tokens: number; total_calls: number };

export type WeekTotals = { tokens: number; total_calls: number };

export type GroupRow = { name?: string; group?: string; tokens: number; calls: number };

export type HourlyBucket = { hour: number; total_calls: number; tokens: number };

export type EnrichedRow = {
	contract_address: string;
	ticker: string | null;
	chain?: string | null;
	launchpad: string | null;
	call_count: number;
	first_seen_at: string;
	last_seen_at: string;
	groups_mentioned?: string | null;
	groups_concat?: string | null;

	price_usd: number | null;
	price_change_h24: number | null;
	market_cap: number | null;
	market_cap_ath: number | null;
	market_cap_ath_at: number | null;
	price_ath: number | null;
	price_ath_at: number | null;
	liquidity_usd: number | null;
	volume_h24: number | null;

	holder_count: number | null;
	top10_pct: number | null;
	renounced: number | null;
	renounced_mint: number | null;
	renounced_freeze: number | null;
	burn_status: string | null;
	burn_ratio: number | null;
	swaps_5m: number | null;
	swaps_1h: number | null;
	swaps_24h: number | null;
	creation_timestamp: number | null;

	name: string | null;
	description: string | null;
	image_url: string | null;
};

export type OverviewResponse = {
	ready: boolean;
	date?: string;
	today?: DayCount;
	yesterday?: DayCount;
	delta?: { tokens: Delta; calls: Delta };
	week?: WeekDay[];
	week_totals?: WeekTotals;
	hourly_today?: HourlyBucket[];
	top_tokens?: EnrichedRow[];
	groups?: GroupRow[];
};

export type DayResponse = {
	ready: boolean;
	data: EnrichedRow[];
	rowCount: number;
	pageCount: number;
	page: number;
	pageSize: number;
	date: string;
	filters: {
		search: string;
		launchpad: string[];
		groups: string[];
		sort: string;
	};
};

export type SortDir = 'asc' | 'desc';
export type DaySortField = 'call_count' | 'first_seen_at' | 'last_seen_at' | 'ticker' | 'launchpad';
export type RangeSortField =
	| 'call_count'
	| 'days_active'
	| 'first_seen_at'
	| 'last_seen_at'
	| 'ticker'
	| 'launchpad';

export type RangeRow = EnrichedRow & { days_active: number };

export type TokenDetail = EnrichedRow & { days_active: number };

export type TokenTimelineEntry = {
	call_date: string;
	call_count: number;
	first_seen_at: string;
	last_seen_at: string;
	groups_mentioned: string | null;
};

export type TokenResponse = {
	ready: boolean;
	token: TokenDetail;
	timeline: TokenTimelineEntry[];
};

export type RangeResponse = {
	ready: boolean;
	data: RangeRow[];
	rowCount: number;
	pageCount: number;
	page: number;
	pageSize: number;
	from: string;
	to: string;
	filters: {
		search: string;
		launchpad: string[];
		groups: string[];
		sort: string;
	};
};
