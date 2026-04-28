<script lang="ts">
	import { page as pageStore } from '$app/state';
	import { goto } from '$app/navigation';
	import { createQuery, createInfiniteQuery } from '@tanstack/svelte-query';
	import { api, fmtNum, todayIso, daysAgoIso } from '$lib/api';
	import type { RangeSortField, SortDir, RangeResponse } from '$lib/types';
	import DatePresets from '$lib/components/DatePresets.svelte';
	import FilterBar from '$lib/components/FilterBar.svelte';
	import FilterChip from '$lib/components/FilterChip.svelte';
	import McRangeInput from '$lib/components/McRangeInput.svelte';
	import TableSettings from '$lib/components/TableSettings.svelte';
	import TokenRow from '$lib/components/TokenRow.svelte';
	import { tablePrefs, cellPadding } from '$lib/tablePrefs.svelte';

	const KNOWN_LAUNCHPADS = ['pump.fun', 'bags.fm', 'bonk.fun', 'moonshot', 'printr'];
	const PAGE_SIZE = 100;
	const params = pageStore.url.searchParams;

	const topGroupsQuery = createQuery(() => ({
		queryKey: ['top-groups', 7],
		queryFn: () => api.topGroups(7, 20),
		staleTime: 5 * 60_000
	}));

	let dFrom = $state(params.get('from') || daysAgoIso(6));
	let dTo = $state(params.get('to') || todayIso());
	let searchInput = $state(params.get('search') || '');
	let search = $state(params.get('search') || '');
	let sortField = $state<RangeSortField>(
		(params.get('sortField') as RangeSortField) || 'last_seen_at'
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
	let mcMin = $state<number>(Number(params.get('mcmin')) || 0);
	let mcMax = $state<number>(Number(params.get('mcmax')) || 0);

	let debounceTimer: ReturnType<typeof setTimeout> | null = null;
	$effect(() => {
		const v = searchInput;
		if (debounceTimer) clearTimeout(debounceTimer);
		debounceTimer = setTimeout(() => {
			search = v;
		}, 300);
	});

	$effect(() => {
		const sp = new URLSearchParams();
		sp.set('from', dFrom);
		sp.set('to', dTo);
		if (search) sp.set('search', search);
		if (sortField !== 'last_seen_at') sp.set('sortField', sortField);
		if (sortDir !== 'desc') sp.set('sortDir', sortDir);
		if (launchpads.length > 0) sp.set('lp', launchpads.join(','));
		if (groups.length > 0) sp.set('g', groups.join(','));
		if (minHolders !== 100) sp.set('mh', String(minHolders));
		if (mcMin > 0) sp.set('mcmin', String(mcMin));
		if (mcMax > 0) sp.set('mcmax', String(mcMax));
		goto(`?${sp}`, { replaceState: true, noScroll: true, keepFocus: true });
	});

	const rangeQuery = createInfiniteQuery(() => ({
		queryKey: [
			'range',
			dFrom,
			dTo,
			search,
			sortField,
			sortDir,
			launchpads.join(','),
			groups.join(','),
			minHolders,
			mcMin,
			mcMax
		],
		initialPageParam: 1,
		queryFn: ({ pageParam }) =>
			api.range({
				from: dFrom,
				to: dTo,
				page: pageParam as number,
				pageSize: PAGE_SIZE,
				search,
				sort: `${sortField}:${sortDir}`,
				launchpad: launchpads.length > 0 ? launchpads : undefined,
				groups: groups.length > 0 ? groups : undefined,
				minHolders,
				mcMin,
				mcMax
			}),
		getNextPageParam: (lastPage: RangeResponse) =>
			lastPage.page < lastPage.pageCount ? lastPage.page + 1 : undefined,
		refetchInterval: 60_000
	}));

	const allRows = $derived(rangeQuery.data?.pages.flatMap((p) => p.data) ?? []);
	const totalRows = $derived(rangeQuery.data?.pages[0]?.rowCount ?? 0);

	let sentinel: HTMLDivElement | undefined = $state();
	$effect(() => {
		if (!sentinel) return;
		const obs = new IntersectionObserver(
			(entries) => {
				if (entries[0].isIntersecting && rangeQuery.hasNextPage && !rangeQuery.isFetchingNextPage) {
					rangeQuery.fetchNextPage();
				}
			},
			{ rootMargin: '300px' }
		);
		obs.observe(sentinel);
		return () => obs.disconnect();
	});

	function toggleSort(field: RangeSortField) {
		if (sortField === field) {
			sortDir = sortDir === 'asc' ? 'desc' : 'asc';
		} else {
			sortField = field;
			const ascByDefault: RangeSortField[] = ['ticker', 'launchpad'];
			sortDir = ascByDefault.includes(field) ? 'asc' : 'desc';
		}
	}

	function toggleLaunchpad(lp: string) {
		launchpads = launchpads.includes(lp)
			? launchpads.filter((x) => x !== lp)
			: [...launchpads, lp];
	}

	function toggleGroup(g: string) {
		groups = groups.includes(g) ? groups.filter((x) => x !== g) : [...groups, g];
	}

	function resetFilters() {
		searchInput = '';
		search = '';
		launchpads = [];
		groups = [];
		minHolders = 100;
		mcMin = 0;
		mcMax = 0;
		sortField = 'last_seen_at';
		sortDir = 'desc';
	}

	const arrow = (field: RangeSortField) =>
		sortField === field ? (sortDir === 'desc' ? '↓' : '↑') : '';

	const hasFilters = $derived(
		search !== '' ||
			launchpads.length > 0 ||
			groups.length > 0 ||
			minHolders !== 100 ||
			mcMin > 0 ||
			mcMax > 0 ||
			sortField !== 'last_seen_at' ||
			sortDir !== 'desc'
	);

	const cell = $derived(cellPadding(tablePrefs.density));
	const colspan = $derived(
		11 +
			(tablePrefs.cols.description ? 1 : 0) +
			(tablePrefs.cols.groups ? 1 : 0) +
			(tablePrefs.cols.holders ? 1 : 0) +
			(tablePrefs.cols.flags ? 1 : 0)
	);
</script>

<section>
	<header class="mb-4 flex items-end justify-between gap-4 flex-wrap">
		<div>
			<h1 class="text-3xl font-semibold tracking-tight">Range</h1>
			<div class="flex items-center gap-2 mt-1 flex-wrap">
				<DatePresets
					mode="range"
					from={dFrom}
					to={dTo}
					onchange={(next) => {
						if (next.from !== undefined) dFrom = next.from;
						if (next.to !== undefined) dTo = next.to;
					}}
				/>
			</div>
		</div>
		<div class="text-sm text-zinc-500 text-right">
			{#if rangeQuery.isFetching && !rangeQuery.isFetchingNextPage}
				<span class="text-zinc-400">refreshing…</span>
			{:else if totalRows > 0}
				<div class="text-zinc-300 tabular-nums">
					{fmtNum(allRows.length)} of {fmtNum(totalRows)} tokens
				</div>
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
			{#each topGroupsQuery.data?.groups ?? [] as g (g.name)}
				<FilterChip
					active={groups.includes(g.name)}
					label={g.name}
					count={g.count}
					onclick={() => toggleGroup(g.name)}
				/>
			{/each}
			{#each groups.filter((g) => !(topGroupsQuery.data?.groups ?? []).some((tg) => tg.name === g)) as g (g)}
				<FilterChip active label={g} onclick={() => toggleGroup(g)} />
			{/each}
		</div>
		<label class="flex items-center gap-2 text-xs text-zinc-400">
			<span class="uppercase tracking-wider text-[10px] text-zinc-500">Min holders</span>
			<input
				type="number"
				min="0"
				step="10"
				bind:value={minHolders}
				class="bg-zinc-900/60 border border-zinc-700 rounded px-2 py-1 w-20 tabular-nums focus:outline-none focus:border-zinc-500"
			/>
		</label>
		<McRangeInput
			min={mcMin}
			max={mcMax}
			onchange={(next) => {
				mcMin = next.min;
				mcMax = next.max;
			}}
		/>
		<TableSettings />
	</FilterBar>

	<div class="rounded-lg border border-zinc-800 overflow-x-auto mt-4">
		<table class="w-full text-sm">
			<thead class="bg-zinc-900/60 text-zinc-400 uppercase text-xs tracking-wider">
				<tr>
					<th class="text-left {cell} font-normal">#</th>
					<th
						class="text-left {cell} font-normal cursor-pointer hover:text-zinc-200"
						onclick={() => toggleSort('ticker')}
					>Token {arrow('ticker')}</th>
					<th class="text-left {cell} font-normal">CA</th>
					<th
						class="text-left {cell} font-normal cursor-pointer hover:text-zinc-200"
						onclick={() => toggleSort('launchpad')}
					>LP {arrow('launchpad')}</th>
					<th
						class="text-right {cell} font-normal cursor-pointer hover:text-zinc-200"
						onclick={() => toggleSort('call_count')}
					>Calls {arrow('call_count')}</th>
					<th
						class="text-right {cell} font-normal cursor-pointer hover:text-zinc-200"
						onclick={() => toggleSort('days_active')}
					>Days {arrow('days_active')}</th>
					<th
						class="text-right {cell} font-normal cursor-pointer hover:text-zinc-200"
						onclick={() => toggleSort('market_cap')}
					>MC {arrow('market_cap')}</th>
					<th
						class="text-right {cell} font-normal cursor-pointer hover:text-zinc-200"
						onclick={() => toggleSort('price_change_h24')}
					>24h {arrow('price_change_h24')}</th>
					{#if tablePrefs.cols.description}
						<th class="text-left {cell} font-normal">Description</th>
					{/if}
					{#if tablePrefs.cols.groups}
						<th class="text-left {cell} font-normal">Groups</th>
					{/if}
					<th
						class="text-left {cell} font-normal cursor-pointer hover:text-zinc-200"
						onclick={() => toggleSort('first_seen_at')}
					>First {arrow('first_seen_at')}</th>
					<th
						class="text-left {cell} font-normal cursor-pointer hover:text-zinc-200"
						onclick={() => toggleSort('last_seen_at')}
					>Last {arrow('last_seen_at')}</th>
					{#if tablePrefs.cols.holders}
						<th
							class="text-right {cell} font-normal cursor-pointer hover:text-zinc-200"
							onclick={() => toggleSort('holder_count')}
						>Holders {arrow('holder_count')}</th>
					{/if}
					{#if tablePrefs.cols.flags}
						<th
							class="text-left {cell} font-normal cursor-help"
							title="RNK = authority renounced · MNT = mint renounced (fixed supply) · FRZ = freeze renounced · LP = liquidity burned"
						>Flags</th>
					{/if}
					<th class="text-left {cell} font-normal"></th>
				</tr>
			</thead>
			<tbody>
				{#if rangeQuery.isPending}
					<tr><td colspan={colspan} class="px-3 py-8 text-center text-zinc-500">Loading…</td></tr>
				{:else if rangeQuery.isError}
					<tr><td colspan={colspan} class="px-3 py-8 text-center text-rose-400">
						Error: {rangeQuery.error.message}
					</td></tr>
				{:else if allRows.length === 0}
					<tr><td colspan={colspan} class="px-3 py-8 text-center text-zinc-500">No calls in this range.</td></tr>
				{:else}
					{#each allRows as r, i (r.contract_address)}
						<TokenRow
							row={r}
							index={i + 1}
							showDaysActive
							daysActive={r.days_active}
							showLast
						/>
					{/each}
				{/if}
			</tbody>
		</table>
	</div>

	{#if rangeQuery.hasNextPage || rangeQuery.isFetchingNextPage}
		<div bind:this={sentinel} class="mt-4 text-center text-sm text-zinc-500 py-4">
			{#if rangeQuery.isFetchingNextPage}
				loading more…
			{:else}
				<button
					onclick={() => rangeQuery.fetchNextPage()}
					class="px-3 py-1 rounded border border-zinc-700 hover:bg-zinc-800 transition-colors"
				>Load more</button>
			{/if}
		</div>
	{:else if allRows.length > 0 && allRows.length === totalRows}
		<div class="mt-4 text-center text-xs text-zinc-600 py-2">— end of list —</div>
	{/if}
</section>
