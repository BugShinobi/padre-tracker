<script lang="ts">
	import { page as pageStore } from '$app/state';
	import { goto } from '$app/navigation';
	import { createQuery, keepPreviousData } from '@tanstack/svelte-query';
	import {
		api,
		fmtMc,
		fmtPct,
		fmtNum,
		shortCa,
		fmtAge,
		todayIso,
		daysAgoIso
	} from '$lib/api';
	import type { RangeRow, RangeSortField, SortDir } from '$lib/types';

	const initialFrom = pageStore.url.searchParams.get('from') || daysAgoIso(6);
	const initialTo = pageStore.url.searchParams.get('to') || todayIso();

	let dFrom = $state(initialFrom);
	let dTo = $state(initialTo);
	let pageNum = $state(1);
	let pageSize = $state(50);
	let searchInput = $state('');
	let search = $state('');
	let sortField = $state<RangeSortField>('call_count');
	let sortDir = $state<SortDir>('desc');

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
		const url = new URL(pageStore.url);
		url.searchParams.set('from', dFrom);
		url.searchParams.set('to', dTo);
		goto(url, { replaceState: true, noScroll: true, keepFocus: true });
	});

	const rangeQuery = createQuery(() => ({
		queryKey: ['range', dFrom, dTo, pageNum, pageSize, search, sortField, sortDir],
		queryFn: () =>
			api.range({
				from: dFrom,
				to: dTo,
				page: pageNum,
				pageSize,
				search,
				sort: `${sortField}:${sortDir}`
			}),
		placeholderData: keepPreviousData,
		refetchInterval: 60_000
	}));

	function toggleSort(field: RangeSortField) {
		if (sortField === field) {
			sortDir = sortDir === 'asc' ? 'desc' : 'asc';
		} else {
			sortField = field;
			sortDir = field === 'ticker' || field === 'launchpad' ? 'asc' : 'desc';
		}
		pageNum = 1;
	}

	function setRange(days: number) {
		dFrom = daysAgoIso(days - 1);
		dTo = todayIso();
		pageNum = 1;
	}

	const arrow = (field: RangeSortField) =>
		sortField === field ? (sortDir === 'desc' ? '↓' : '↑') : '';

	const changeClass = (v: number | null | undefined) =>
		v == null ? 'text-zinc-500' : v >= 0 ? 'text-emerald-400' : 'text-rose-400';

	const launchpadBadge = (lp: string | null) => {
		if (!lp) return 'bg-zinc-800 text-zinc-400';
		const k = lp.split('.')[0];
		switch (k) {
			case 'pump': return 'bg-amber-900/40 text-amber-300';
			case 'BAGS': return 'bg-purple-900/40 text-purple-300';
			case 'bonk': return 'bg-orange-900/40 text-orange-300';
			case 'moon': return 'bg-blue-900/40 text-blue-300';
			case 'printr': return 'bg-emerald-900/40 text-emerald-300';
			default: return 'bg-zinc-800 text-zinc-300';
		}
	};

	const flagBadge = (r: RangeRow) => {
		const flags: string[] = [];
		if (r.renounced) flags.push('RNK');
		if (r.renounced_mint) flags.push('MNT');
		if (r.renounced_freeze) flags.push('FRZ');
		if (r.burn_status === 'burn') flags.push('LP');
		return flags;
	};
</script>

<section>
	<div class="flex flex-wrap items-end gap-3 mb-4">
		<div>
			<label class="block text-xs uppercase tracking-wider text-zinc-500 mb-1" for="from">From</label>
			<input
				id="from"
				type="date"
				bind:value={dFrom}
				oninput={() => (pageNum = 1)}
				max={dTo}
				class="bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-sm focus:outline-none focus:border-zinc-500"
			/>
		</div>
		<div>
			<label class="block text-xs uppercase tracking-wider text-zinc-500 mb-1" for="to">To</label>
			<input
				id="to"
				type="date"
				bind:value={dTo}
				oninput={() => (pageNum = 1)}
				min={dFrom}
				max={todayIso()}
				class="bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-sm focus:outline-none focus:border-zinc-500"
			/>
		</div>
		<div class="flex gap-1">
			{#each [7, 14, 30] as days}
				<button
					type="button"
					onclick={() => setRange(days)}
					class="px-2 py-1 rounded border border-zinc-700 text-xs hover:bg-zinc-800"
				>{days}d</button>
			{/each}
		</div>
		<div class="flex-1 min-w-[200px]">
			<label class="block text-xs uppercase tracking-wider text-zinc-500 mb-1" for="search">
				Search ticker / CA
			</label>
			<input
				id="search"
				type="text"
				bind:value={searchInput}
				placeholder="e.g. PEPE or 4Bx…"
				class="w-full bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-sm focus:outline-none focus:border-zinc-500"
			/>
		</div>
		<div>
			<label class="block text-xs uppercase tracking-wider text-zinc-500 mb-1" for="psize">Per page</label>
			<select
				id="psize"
				bind:value={pageSize}
				onchange={() => (pageNum = 1)}
				class="bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-sm focus:outline-none focus:border-zinc-500"
			>
				<option value={25}>25</option>
				<option value={50}>50</option>
				<option value={100}>100</option>
				<option value={200}>200</option>
			</select>
		</div>
		<div class="text-sm text-zinc-500 ml-auto">
			{#if rangeQuery.isFetching}
				<span class="text-zinc-400">refreshing…</span>
			{:else if rangeQuery.data?.ready}
				{fmtNum(rangeQuery.data.rowCount)} unique tokens · page {rangeQuery.data.page} of {rangeQuery.data.pageCount}
			{/if}
		</div>
	</div>

	<div class="rounded-lg border border-zinc-800 overflow-hidden">
		<table class="w-full text-sm">
			<thead class="bg-zinc-900/60 text-zinc-400 uppercase text-xs tracking-wider">
				<tr>
					<th class="text-left px-3 py-2 font-normal">#</th>
					<th
						class="text-left px-3 py-2 font-normal cursor-pointer hover:text-zinc-200"
						onclick={() => toggleSort('ticker')}
					>Ticker {arrow('ticker')}</th>
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
					<th class="text-right px-3 py-2 font-normal">MC</th>
					<th class="text-right px-3 py-2 font-normal">24h</th>
					<th class="text-left px-3 py-2 font-normal">Groups</th>
					<th
						class="text-left px-3 py-2 font-normal cursor-pointer hover:text-zinc-200"
						onclick={() => toggleSort('first_seen_at')}
					>First {arrow('first_seen_at')}</th>
					<th
						class="text-left px-3 py-2 font-normal cursor-pointer hover:text-zinc-200"
						onclick={() => toggleSort('last_seen_at')}
					>Last {arrow('last_seen_at')}</th>
					<th class="text-left px-3 py-2 font-normal">Flags</th>
				</tr>
			</thead>
			<tbody>
				{#if rangeQuery.isPending}
					<tr><td colspan="12" class="px-3 py-8 text-center text-zinc-500">Loading…</td></tr>
				{:else if rangeQuery.isError}
					<tr><td colspan="12" class="px-3 py-8 text-center text-rose-400">
						Error: {rangeQuery.error.message}
					</td></tr>
				{:else if !rangeQuery.data?.ready || rangeQuery.data.data.length === 0}
					<tr><td colspan="12" class="px-3 py-8 text-center text-zinc-500">No calls in this range.</td></tr>
				{:else}
					{#each rangeQuery.data.data as r, i (r.contract_address)}
						<tr class="border-t border-zinc-800 hover:bg-zinc-900/30">
							<td class="px-3 py-2 text-zinc-500 tabular-nums">
								{(rangeQuery.data.page - 1) * rangeQuery.data.pageSize + i + 1}
							</td>
							<td class="px-3 py-2">
								<div class="flex items-center gap-2">
									{#if r.image_url}
										<img
											src={r.image_url}
											alt=""
											class="w-6 h-6 rounded-full object-cover bg-zinc-800 shrink-0"
											loading="lazy"
											referrerpolicy="no-referrer"
										/>
									{:else}
										<div class="w-6 h-6 rounded-full bg-zinc-800 shrink-0"></div>
									{/if}
									<span
										class="font-medium {r.ticker ? '' : 'text-zinc-500 italic'}"
										title={r.description ?? r.name ?? ''}
									>{r.ticker ?? 'unknown'}</span>
								</div>
							</td>
							<td class="px-3 py-2">
								<div class="flex items-center gap-2">
									<span class="font-mono text-xs text-zinc-400">{shortCa(r.contract_address)}</span>
									<span class="text-xs text-zinc-500">{fmtAge(r.creation_timestamp)}</span>
									<span class="flex gap-1 text-xs">
										<a href="https://dexscreener.com/solana/{r.contract_address}"
											target="_blank" rel="noopener"
											class="text-blue-400 hover:underline" title="DexScreener">D</a>
										<a href="https://gmgn.ai/sol/token/{r.contract_address}"
											target="_blank" rel="noopener"
											class="text-emerald-400 hover:underline" title="GMGN">G</a>
										<a href="https://trade.padre.gg/trade/solana/{r.contract_address}"
											target="_blank" rel="noopener"
											class="text-amber-400 hover:underline" title="Padre">P</a>
									</span>
								</div>
							</td>
							<td class="px-3 py-2">
								<span class="px-2 py-0.5 rounded text-xs {launchpadBadge(r.launchpad)}">
									{r.launchpad ?? '—'}
								</span>
							</td>
							<td class="px-3 py-2 text-right tabular-nums font-medium">{r.call_count}</td>
							<td class="px-3 py-2 text-right tabular-nums text-zinc-400">{r.days_active}</td>
							<td class="px-3 py-2 text-right tabular-nums">
								<div>{fmtMc(r.market_cap)}</div>
								{#if r.market_cap_ath && (!r.market_cap || r.market_cap_ath > r.market_cap)}
									<div class="text-xs text-zinc-500" title="ATH since tracking">
										ATH {fmtMc(r.market_cap_ath)}
									</div>
								{/if}
							</td>
							<td class="px-3 py-2 text-right tabular-nums {changeClass(r.price_change_h24)}">
								{fmtPct(r.price_change_h24)}
							</td>
							<td class="px-3 py-2 text-zinc-300 text-xs">{r.groups_mentioned ?? '—'}</td>
							<td class="px-3 py-2 text-zinc-400 tabular-nums text-xs">{r.first_seen_at.slice(5, 10)}</td>
							<td class="px-3 py-2 text-zinc-400 tabular-nums text-xs">{r.last_seen_at.slice(5, 10)}</td>
							<td class="px-3 py-2">
								<div class="flex gap-1 flex-wrap">
									{#each flagBadge(r) as f}
										<span class="px-1.5 py-0.5 rounded text-xs bg-emerald-900/40 text-emerald-300">{f}</span>
									{/each}
								</div>
							</td>
						</tr>
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
				class="px-3 py-1 rounded border border-zinc-700 hover:bg-zinc-800 disabled:opacity-30 disabled:cursor-not-allowed"
			>← Prev</button>
			<span class="text-zinc-500">
				Page {rangeQuery.data.page} / {rangeQuery.data.pageCount}
			</span>
			<button
				disabled={pageNum >= rangeQuery.data.pageCount}
				onclick={() => (pageNum = Math.min(rangeQuery.data?.pageCount ?? 1, pageNum + 1))}
				class="px-3 py-1 rounded border border-zinc-700 hover:bg-zinc-800 disabled:opacity-30 disabled:cursor-not-allowed"
			>Next →</button>
		</div>
	{/if}
</section>
