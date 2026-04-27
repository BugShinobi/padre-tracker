<script lang="ts">
	import { page as pageStore } from '$app/state';
	import { goto } from '$app/navigation';
	import { createQuery, keepPreviousData } from '@tanstack/svelte-query';
	import { api, fmtNum, todayIso, daysAgoIso } from '$lib/api';
	import type { RangeSortField, SortDir } from '$lib/types';
	import FilterBar from '$lib/components/FilterBar.svelte';
	import FilterChip from '$lib/components/FilterChip.svelte';
	import TokenRow from '$lib/components/TokenRow.svelte';

	const KNOWN_LAUNCHPADS = ['pump.fun', 'BAGS', 'bonk.fun', 'moon.it', 'printr.brrr'];
	const KNOWN_GROUPS = [
		'Prosperity', 'Pastel Alpha', 'Cryptic', 'Serenity', 'Incognito',
		'TAG', 'Potion', 'Pumpfun Trenches', 'Minted', 'Digi World'
	];
	const params = pageStore.url.searchParams;

	let dFrom = $state(params.get('from') || daysAgoIso(6));
	let dTo = $state(params.get('to') || todayIso());
	let pageNum = $state(Number(params.get('page')) || 1);
	let pageSize = $state(Number(params.get('pageSize')) || 50);
	let searchInput = $state(params.get('search') || '');
	let search = $state(params.get('search') || '');
	let sortField = $state<RangeSortField>(
		(params.get('sortField') as RangeSortField) || 'call_count'
	);
	let sortDir = $state<SortDir>((params.get('sortDir') as SortDir) || 'desc');
	let launchpads = $state<string[]>(
		params.get('lp') ? params.get('lp')!.split(',').filter(Boolean) : []
	);
	let groups = $state<string[]>(
		params.get('g') ? params.get('g')!.split(',').filter(Boolean) : []
	);
	let minHolders = $state<number>(
		params.has('mh') ? Number(params.get('mh')) || 0 : 100
	);

	let debounceTimer: ReturnType<typeof setTimeout> | null = null;
	$effect(() => {
		const v = searchInput;
		if (debounceTimer) clearTimeout(debounceTimer);
		debounceTimer = setTimeout(() => {
			search = v;
			pageNum = 1;
		}, 300);
	});

	$effect(() => {
		const sp = new URLSearchParams();
		sp.set('from', dFrom);
		sp.set('to', dTo);
		if (pageNum > 1) sp.set('page', String(pageNum));
		if (pageSize !== 50) sp.set('pageSize', String(pageSize));
		if (search) sp.set('search', search);
		if (sortField !== 'call_count') sp.set('sortField', sortField);
		if (sortDir !== 'desc') sp.set('sortDir', sortDir);
		if (launchpads.length > 0) sp.set('lp', launchpads.join(','));
		if (groups.length > 0) sp.set('g', groups.join(','));
		if (minHolders !== 100) sp.set('mh', String(minHolders));
		goto(`?${sp}`, { replaceState: true, noScroll: true, keepFocus: true });
	});

	const rangeQuery = createQuery(() => ({
		queryKey: [
			'range',
			dFrom,
			dTo,
			pageNum,
			pageSize,
			search,
			sortField,
			sortDir,
			launchpads.join(','),
			groups.join(','),
			minHolders
		],
		queryFn: () =>
			api.range({
				from: dFrom,
				to: dTo,
				page: pageNum,
				pageSize,
				search,
				sort: `${sortField}:${sortDir}`,
				launchpad: launchpads.length > 0 ? launchpads : undefined,
				groups: groups.length > 0 ? groups : undefined,
				minHolders
			}),
		placeholderData: keepPreviousData,
		refetchInterval: 60_000
	}));

	function toggleSort(field: RangeSortField) {
		if (sortField === field) {
			sortDir = sortDir === 'asc' ? 'desc' : 'asc';
		} else {
			sortField = field;
			const ascByDefault: RangeSortField[] = ['ticker', 'launchpad'];
			sortDir = ascByDefault.includes(field) ? 'asc' : 'desc';
		}
		pageNum = 1;
	}

	function setRange(days: number) {
		dFrom = daysAgoIso(days - 1);
		dTo = todayIso();
		pageNum = 1;
	}

	function toggleLaunchpad(lp: string) {
		launchpads = launchpads.includes(lp)
			? launchpads.filter((x) => x !== lp)
			: [...launchpads, lp];
		pageNum = 1;
	}

	function toggleGroup(g: string) {
		groups = groups.includes(g) ? groups.filter((x) => x !== g) : [...groups, g];
		pageNum = 1;
	}

	function resetFilters() {
		searchInput = '';
		search = '';
		launchpads = [];
		groups = [];
		minHolders = 100;
		sortField = 'call_count';
		sortDir = 'desc';
		pageNum = 1;
	}

	const arrow = (field: RangeSortField) =>
		sortField === field ? (sortDir === 'desc' ? '↓' : '↑') : '';

	const hasFilters = $derived(
		search !== '' ||
			launchpads.length > 0 ||
			groups.length > 0 ||
			minHolders !== 100 ||
			sortField !== 'call_count' ||
			sortDir !== 'desc'
	);
</script>

<section>
	<header class="mb-4 flex items-end justify-between gap-4 flex-wrap">
		<div>
			<h1 class="text-3xl font-semibold tracking-tight">Range</h1>
			<div class="flex items-center gap-2 mt-1 flex-wrap">
				<input
					id="from"
					type="date"
					bind:value={dFrom}
					oninput={() => (pageNum = 1)}
					max={dTo}
					class="bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-sm focus:outline-none focus:border-zinc-500"
				/>
				<span class="text-zinc-500 text-sm">→</span>
				<input
					id="to"
					type="date"
					bind:value={dTo}
					oninput={() => (pageNum = 1)}
					min={dFrom}
					max={todayIso()}
					class="bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-sm focus:outline-none focus:border-zinc-500"
				/>
				<div class="flex gap-1 ml-1">
					{#each [7, 14, 30] as days}
						<button
							type="button"
							onclick={() => setRange(days)}
							class="px-2 py-1 rounded border border-zinc-700 text-xs text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200 transition-colors"
						>{days}d</button>
					{/each}
				</div>
				<select
					id="psize"
					bind:value={pageSize}
					onchange={() => (pageNum = 1)}
					class="bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-sm focus:outline-none focus:border-zinc-500 ml-2"
				>
					<option value={25}>25/page</option>
					<option value={50}>50/page</option>
					<option value={100}>100/page</option>
					<option value={200}>200/page</option>
				</select>
			</div>
		</div>
		<div class="text-sm text-zinc-500 text-right">
			{#if rangeQuery.isFetching}
				<span class="text-zinc-400">refreshing…</span>
			{:else if rangeQuery.data?.ready}
				<div class="text-zinc-300 tabular-nums">{fmtNum(rangeQuery.data.rowCount)} unique tokens</div>
				<div class="text-xs">page {rangeQuery.data.page} of {rangeQuery.data.pageCount}</div>
			{/if}
		</div>
	</header>

	<FilterBar hasActiveFilters={hasFilters} onreset={resetFilters}>
		<input
			type="text"
			bind:value={searchInput}
			placeholder="Search ticker or CA…"
			class="bg-zinc-900/60 border border-zinc-700 rounded-full px-3 py-1 text-sm w-56 focus:outline-none focus:border-zinc-500"
		/>
		<div class="flex items-center gap-1.5 flex-wrap">
			<span class="text-[10px] uppercase tracking-wider text-zinc-500 mr-1">LP</span>
			{#each KNOWN_LAUNCHPADS as lp}
				<FilterChip
					active={launchpads.includes(lp)}
					label={lp.split('.')[0]}
					variant="launchpad"
					color={lp}
					onclick={() => toggleLaunchpad(lp)}
				/>
			{/each}
		</div>
		<div class="flex items-center gap-1.5 flex-wrap">
			<span class="text-[10px] uppercase tracking-wider text-zinc-500 mr-1">Group</span>
			{#each KNOWN_GROUPS as g}
				<FilterChip
					active={groups.includes(g)}
					label={g}
					onclick={() => toggleGroup(g)}
				/>
			{/each}
		</div>
		<label class="flex items-center gap-2 text-xs text-zinc-400">
			<span class="uppercase tracking-wider text-[10px] text-zinc-500">Min holders</span>
			<input
				type="number"
				min="0"
				step="10"
				bind:value={minHolders}
				oninput={() => (pageNum = 1)}
				class="bg-zinc-900/60 border border-zinc-700 rounded px-2 py-1 w-20 tabular-nums focus:outline-none focus:border-zinc-500"
			/>
		</label>
	</FilterBar>

	<div class="rounded-lg border border-zinc-800 overflow-x-auto mt-4">
		<table class="w-full text-sm">
			<thead class="bg-zinc-900/60 text-zinc-400 uppercase text-xs tracking-wider">
				<tr>
					<th class="text-left px-3 py-2 font-normal">#</th>
					<th
						class="text-left px-3 py-2 font-normal cursor-pointer hover:text-zinc-200"
						onclick={() => toggleSort('ticker')}
					>Token {arrow('ticker')}</th>
					<th class="text-left px-3 py-2 font-normal">CA</th>
					<th
						class="text-left px-3 py-2 font-normal cursor-pointer hover:text-zinc-200"
						onclick={() => toggleSort('launchpad')}
					>LP {arrow('launchpad')}</th>
					<th
						class="text-right px-3 py-2 font-normal cursor-pointer hover:text-zinc-200"
						onclick={() => toggleSort('call_count')}
					>Calls {arrow('call_count')}</th>
					<th
						class="text-right px-3 py-2 font-normal cursor-pointer hover:text-zinc-200"
						onclick={() => toggleSort('days_active')}
					>Days {arrow('days_active')}</th>
					<th
						class="text-right px-3 py-2 font-normal cursor-pointer hover:text-zinc-200"
						onclick={() => toggleSort('market_cap')}
					>MC {arrow('market_cap')}</th>
					<th
						class="text-right px-3 py-2 font-normal cursor-pointer hover:text-zinc-200"
						onclick={() => toggleSort('price_change_h24')}
					>24h {arrow('price_change_h24')}</th>
					<th class="text-left px-3 py-2 font-normal">Description</th>
					<th class="text-left px-3 py-2 font-normal">Groups</th>
					<th
						class="text-left px-3 py-2 font-normal cursor-pointer hover:text-zinc-200"
						onclick={() => toggleSort('first_seen_at')}
					>First {arrow('first_seen_at')}</th>
					<th
						class="text-left px-3 py-2 font-normal cursor-pointer hover:text-zinc-200"
						onclick={() => toggleSort('last_seen_at')}
					>Last {arrow('last_seen_at')}</th>
					<th
						class="text-right px-3 py-2 font-normal cursor-pointer hover:text-zinc-200"
						onclick={() => toggleSort('holder_count')}
					>Holders {arrow('holder_count')}</th>
					<th class="text-left px-3 py-2 font-normal">Flags</th>
					<th class="text-left px-3 py-2 font-normal"></th>
				</tr>
			</thead>
			<tbody>
				{#if rangeQuery.isPending}
					<tr><td colspan="15" class="px-3 py-8 text-center text-zinc-500">Loading…</td></tr>
				{:else if rangeQuery.isError}
					<tr><td colspan="15" class="px-3 py-8 text-center text-rose-400">
						Error: {rangeQuery.error.message}
					</td></tr>
				{:else if !rangeQuery.data?.ready || rangeQuery.data.data.length === 0}
					<tr><td colspan="15" class="px-3 py-8 text-center text-zinc-500">No calls in this range.</td></tr>
				{:else}
					{#each rangeQuery.data.data as r, i (r.contract_address)}
						<TokenRow
							row={r}
							index={(rangeQuery.data.page - 1) * rangeQuery.data.pageSize + i + 1}
							showDaysActive
							daysActive={r.days_active}
							showLast
						/>
					{/each}
				{/if}
			</tbody>
		</table>
	</div>

	{#if rangeQuery.data?.ready && rangeQuery.data.pageCount > 1}
		<div class="flex items-center justify-between mt-4 text-sm">
			<button
				disabled={pageNum <= 1}
				onclick={() => (pageNum = Math.max(1, pageNum - 1))}
				class="px-3 py-1 rounded border border-zinc-700 hover:bg-zinc-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
			>← Prev</button>
			<span class="text-zinc-500">
				Page {rangeQuery.data.page} / {rangeQuery.data.pageCount}
			</span>
			<button
				disabled={pageNum >= rangeQuery.data.pageCount}
				onclick={() => (pageNum = Math.min(rangeQuery.data?.pageCount ?? 1, pageNum + 1))}
				class="px-3 py-1 rounded border border-zinc-700 hover:bg-zinc-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
			>Next →</button>
		</div>
	{/if}
</section>
