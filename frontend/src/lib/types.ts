export type DayCount = { tokens: number; total_calls: number };

export type Delta = { str: string; class: 'pos' | 'neg' | 'flat' };

export type WeekDay = { date: string; tokens: number; total_calls: number };

export type WeekTotals = { tokens: number; total_calls: number };

export type GroupRow = { name?: string; group?: string; tokens: number; calls: number };

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
	top_tokens?: EnrichedRow[];
	top_tokens_today?: EnrichedRow[];
	latest_calls?: EnrichedRow[];
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
export type DaySortField =
	| 'call_count'
	| 'first_seen_at'
	| 'last_seen_at'
	| 'ticker'
	| 'launchpad'
	| 'market_cap'
	| 'price_change_h24'
	| 'holder_count';
export type RangeSortField =
	| 'call_count'
	| 'days_active'
	| 'first_seen_at'
	| 'last_seen_at'
	| 'ticker'
	| 'launchpad'
	| 'market_cap'
	| 'price_change_h24'
	| 'holder_count';

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

export type AlertType = 'whale' | 'kol' | 'kol_newpair';

export type TelegramAlert = {
	id: number;
	source_channel: string;
	msg_id: number;
	msg_date: string;
	msg_text: string;
	alert_type: AlertType | null;
	actor: string | null;
	target_ticker: string | null;
	amount_usd: number | null;
	market_cap_usd: number | null;
	parse_status: 'matched' | 'unmatched';
};

export type AlertsResponse = {
	ready: boolean;
	data: TelegramAlert[];
	rowCount: number;
	pageCount: number;
	page: number;
	pageSize: number;
	filters: {
		type: string;
		ticker: string;
		actor: string;
		source: string;
		min_usd: number | null;
		max_usd: number | null;
		min_mc: number | null;
		max_mc: number | null;
		from: string;
		to: string;
	};
};

export type AlertsStatsResponse = {
	alerts_today: number;
	top_actors_7d: { actor: string; hits: number }[];
	top_tickers_7d: { target_ticker: string; hits: number }[];
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
