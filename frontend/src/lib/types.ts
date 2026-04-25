export type DayCount = { tokens: number; total_calls: number };

export type Delta = { str: string; class: 'pos' | 'neg' | 'flat' };

export type WeekDay = { date: string; tokens: number; total_calls: number };

export type WeekTotals = { tokens: number; total_calls: number };

export type TopToken = {
	contract_address: string;
	ticker: string | null;
	launchpad: string | null;
	call_count: number;
	groups_concat: string | null;
	first_seen_at?: string;
	last_seen_at?: string;
	price_usd?: number | null;
	market_cap?: number | null;
	change_24h?: number | null;
	market_cap_ath?: number | null;
	description?: string | null;
	image_url?: string | null;
	name?: string | null;
	holders?: number | null;
	top10_holders_pct?: number | null;
	age_str?: string | null;
};

export type GroupRow = { name: string; tokens: number; calls: number };

export type HourlyBucket = { hour: number; total_calls: number; tokens: number };

export type OverviewResponse = {
	ready: boolean;
	date?: string;
	today?: DayCount;
	yesterday?: DayCount;
	delta?: { tokens: Delta; calls: Delta };
	week?: WeekDay[];
	week_totals?: WeekTotals;
	hourly_today?: HourlyBucket[];
	top_tokens?: TopToken[];
	groups?: GroupRow[];
};

export type DayCall = TopToken & {
	chain: string | null;
	groups_mentioned: string | null;
};

export type DayResponse = {
	ready: boolean;
	data: DayCall[];
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
