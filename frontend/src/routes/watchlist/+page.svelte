<script lang="ts">
	import { createQuery } from '@tanstack/svelte-query';
	import { api, fmtNum } from '$lib/api';
	import TokenRow from '$lib/components/TokenRow.svelte';
	import { tablePrefs, cellPadding } from '$lib/tablePrefs.svelte';
	import { watchlist } from '$lib/watchlist.svelte';

	const watchlistQuery = createQuery(() => ({
		queryKey: ['watchlist', watchlist.cas.size],
		queryFn: () => api.watchlist(),
		refetchInterval: 60_000
	}));

	const cell = $derived(cellPadding(tablePrefs.density));
	const colspan = $derived(
		10 +
			(tablePrefs.cols.description ? 1 : 0) +
			(tablePrefs.cols.groups ? 1 : 0) +
			(tablePrefs.cols.holders ? 1 : 0) +
			(tablePrefs.cols.flags ? 1 : 0)
	);
</script>

<section>
	<header class="mb-4 flex items-end justify-between gap-4 flex-wrap">
		<div>
			<h1 class="text-3xl font-semibold tracking-tight flex items-center gap-2">
				<span class="text-amber-400">★</span>Watchlist
			</h1>
			<p class="text-sm text-zinc-500 mt-1">
				Tokens you've starred. Add or remove with the ☆ next to any row.
			</p>
		</div>
		<div class="text-sm text-zinc-500 text-right">
			{#if watchlistQuery.isFetching}
				<span class="text-zinc-400">refreshing…</span>
			{:else if watchlistQuery.data?.ready}
				<div class="text-zinc-300 tabular-nums">{fmtNum(watchlistQuery.data.data.length)} tokens</div>
			{/if}
		</div>
	</header>

	<div class="rounded-lg border border-zinc-800 overflow-x-auto mt-4">
		<table class="w-full text-sm">
			<thead class="bg-zinc-900/60 text-zinc-400 uppercase text-xs tracking-wider">
				<tr>
					<th class="text-left {cell} font-normal">#</th>
					<th class="text-left {cell} font-normal">Token</th>
					<th class="text-left {cell} font-normal">CA</th>
					<th class="text-left {cell} font-normal">LP</th>
					<th class="text-right {cell} font-normal">Calls</th>
					<th class="text-right {cell} font-normal">MC</th>
					<th class="text-right {cell} font-normal">24h</th>
					{#if tablePrefs.cols.description}
						<th class="text-left {cell} font-normal">Description</th>
					{/if}
					{#if tablePrefs.cols.groups}
						<th class="text-left {cell} font-normal">Groups</th>
					{/if}
					<th class="text-left {cell} font-normal">First</th>
					<th class="text-left {cell} font-normal">Last</th>
					{#if tablePrefs.cols.holders}
						<th class="text-right {cell} font-normal">Holders</th>
					{/if}
					{#if tablePrefs.cols.flags}
						<th class="text-left {cell} font-normal">Flags</th>
					{/if}
					<th class="text-left {cell} font-normal"></th>
				</tr>
			</thead>
			<tbody>
				{#if watchlistQuery.isPending}
					<tr><td colspan={colspan} class="px-3 py-8 text-center text-zinc-500">Loading…</td></tr>
				{:else if watchlistQuery.isError}
					<tr><td colspan={colspan} class="px-3 py-8 text-center text-rose-400">
						Error: {watchlistQuery.error.message}
					</td></tr>
				{:else if !watchlistQuery.data?.ready || watchlistQuery.data.data.length === 0}
					<tr>
						<td colspan={colspan} class="px-3 py-12 text-center text-zinc-500">
							No tokens starred yet. Click ☆ on any token to add it here.
						</td>
					</tr>
				{:else}
					{#each watchlistQuery.data.data as r, i (r.contract_address)}
						<TokenRow row={r} index={i + 1} showLast />
					{/each}
				{/if}
			</tbody>
		</table>
	</div>
</section>
