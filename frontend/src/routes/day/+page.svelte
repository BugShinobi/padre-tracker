<script lang="ts">
	import { page as pageStore } from '$app/state';
	import { goto } from '$app/navigation';
	import { createQuery, keepPreviousData } from '@tanstack/svelte-query';
	import { api, fmtNum, todayIso } from '$lib/api';
	import type { DaySortField, SortDir } from '$lib/types';
	import FilterBar from '$lib/components/FilterBar.svelte';
	import FilterChip from '$lib/components/FilterChip.svelte';
	import TokenRow from '$lib/components/TokenRow.svelte';

	const KNOWN_LAUNCHPADS = ['pump.fun', 'BAGS', 'bonk.fun', 'moon.it', 'printr.brrr'];

	const params = pageStore.url.searchParams;

	let date = $state(params.get('d') || todayIso());
	let pageNum = $state(Number(params.get('page')) || 1);
	let pageSize = $state(Number(params.get('pageSize')) || 50);
	let searchInput = $state(params.get('search') || '');
	let search = $state(params.get('search') || '');
	let sortField = $state<DaySortField>(
		(params.get('sortField') as DaySortField) || 'call_count'
	);
	let sortDir = $state<SortDir>((params.get('sortDir') as SortDir) || 'desc');
	let launchpads = $state<string[]>(
		params.get('lp') ? params.get('lp')!.split(',').filter(Boolean) : []
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
		sp.set('d', date);
		if (pageNum > 1) sp.set('page', String(pageNum));
		if (pageSize !== 50) sp.set('pageSize', String(pageSize));
		if (search) sp.set('search', search);
		if (sortField !== 'call_count') sp.set('sortField', sortField);
		if (sortDir !== 'desc') sp.set('sortDir', sortDir);
		if (launchpads.length > 0) sp.set('lp', launchpads.join(','));
		goto(`?${sp}`, { replaceState: true, noScroll: true, keepFocus: true });
	});

	const dayQuery = createQuery(() => ({
		queryKey: ['day', date, pageNum, pageSize, search, sortField, sortDir, launchpads.join(',')],
		queryFn: () =>
			api.day({
				d: date,
				page: pageNum,
				pageSize,
				search,
				sort: `${sortField}:${sortDir}`,
				launchpad: launchpads.length > 0 ? launchpads : undefined
			}),
		placeholderData: keepPreviousData,
		refetchInterval: 60_000
	}));

	function toggleSort(field: DaySortField) {
		if (sortField === field) {
			sortDir = sortDir === 'asc' ? 'desc' : 'asc';
		} else {
			sortField = field;
			sortDir = field === 'ticker' || field === 'launchpad' ? 'asc' : 'desc';
		}
		pageNum = 1;
	}

	function toggleLaunchpad(lp: string) {
		launchpads = launchpads.includes(lp)
			? launchpads.filter((x) => x !== lp)
			: [...launchpads, lp];
		pageNum = 1;
	}

	function resetFilters() {
		searchInput = '';
		search = '';
		launchpads = [];
		sortField = 'call_count';
		sortDir = 'desc';
		pageNum = 1;
	}

	const arrow = (field: DaySortField) =>
		sortField === field ? (sortDir === 'desc' ? '↓' : '↑') : '';

	const hasFilters = $derived(
		search !== '' ||
			launchpads.length > 0 ||
			sortField !== 'call_count' ||
			sortDir !== 'desc'
	);
</script>

<section>
	<header class="mb-4 flex items-end justify-between gap-4 flex-wrap">
		<div>
			<h1 class="text-3xl font-semibold tracking-tight">Day</h1>
			<div class="flex items-center gap-3 mt-1">
				<input
					id="date"
					type="date"
					bind:value={date}
					oninput={() => (pageNum = 1)}
					class="bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-sm focus:outline-none focus:border-zinc-500"
				/>
				<select
					id="psize"
					bind:value={pageSize}
					onchange={() => (pageNum = 1)}
					class="bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-sm focus:outline-none focus:border-zinc-500"
				>
					<option value={25}>25/page</option>
					<option value={50}>50/page</option>
					<option value={100}>100/page</option>
					<option value={200}>200/page</option>
				</select>
			</div>
		</div>
		<div class="text-sm text-zinc-500 text-right">
			{#if dayQuery.isFetching}
				<span class="text-zinc-400">refreshing…</span>
			{:else if dayQuery.data?.ready}
				<div class="text-zinc-300 tabular-nums">{fmtNum(dayQuery.data.rowCount)} rows</div>
				<div class="text-xs">page {dayQuery.data.page} of {dayQuery.data.pageCount}</div>
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
	</FilterBar>

	<div class="rounded-lg border border-zinc-800 overflow-x-auto mt-4">
		<table class="w-full text-sm">
			<thead class="bg-zinc-900/60 text-zinc-400 uppercase text-xs tracking-wider">
				<tr>
					<th class="text-left px-3 py-2 font-normal">#</th>
					<th
						class="text-left px-3 py-2 font-normal cursor-pointer hover:text-zinc-200"
						onclick={() => toggleSort('ticker')}
					>
						Token {arrow('ticker')}
					</th>
					<th class="text-left px-3 py-2 font-normal">CA</th>
					<th
						class="text-left px-3 py-2 font-normal cursor-pointer hover:text-zinc-200"
						onclick={() => toggleSort('launchpad')}
					>
						LP {arrow('launchpad')}
					</th>
					<th
						class="text-right px-3 py-2 font-normal cursor-pointer hover:text-zinc-200"
						onclick={() => toggleSort('call_count')}
					>
						Calls {arrow('call_count')}
					</th>
					<th class="text-right px-3 py-2 font-normal">MC</th>
					<th class="text-right px-3 py-2 font-normal">24h</th>
					<th class="text-left px-3 py-2 font-normal">Description</th>
					<th class="text-left px-3 py-2 font-normal">Groups</th>
					<th
						class="text-left px-3 py-2 font-normal cursor-pointer hover:text-zinc-200"
						onclick={() => toggleSort('first_seen_at')}
					>
						First {arrow('first_seen_at')}
					</th>
					<th class="text-right px-3 py-2 font-normal">Holders</th>
					<th class="text-left px-3 py-2 font-normal">Flags</th>
				</tr>
			</thead>
			<tbody>
				{#if dayQuery.isPending}
					<tr><td colspan="13" class="px-3 py-8 text-center text-zinc-500">Loading…</td></tr>
				{:else if dayQuery.isError}
					<tr><td colspan="13" class="px-3 py-8 text-center text-rose-400">
						Error: {dayQuery.error.message}
					</td></tr>
				{:else if !dayQuery.data?.ready || dayQuery.data.data.length === 0}
					<tr><td colspan="13" class="px-3 py-8 text-center text-zinc-500">No calls.</td></tr>
				{:else}
					{#each dayQuery.data.data as r, i (r.contract_address)}
						<TokenRow
							row={r}
							index={(dayQuery.data.page - 1) * dayQuery.data.pageSize + i + 1}
						/>
					{/each}
				{/if}
			</tbody>
		</table>
	</div>

	{#if dayQuery.data?.ready && dayQuery.data.pageCount > 1}
		<div class="flex items-center justify-between mt-4 text-sm">
			<button
				disabled={pageNum <= 1}
				onclick={() => (pageNum = Math.max(1, pageNum - 1))}
				class="px-3 py-1 rounded border border-zinc-700 hover:bg-zinc-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
			>← Prev</button>
			<span class="text-zinc-500">
				Page {dayQuery.data.page} / {dayQuery.data.pageCount}
			</span>
			<button
				disabled={pageNum >= dayQuery.data.pageCount}
				onclick={() => (pageNum = Math.min(dayQuery.data?.pageCount ?? 1, pageNum + 1))}
				class="px-3 py-1 rounded border border-zinc-700 hover:bg-zinc-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
			>Next →</button>
		</div>
	{/if}
</section>
