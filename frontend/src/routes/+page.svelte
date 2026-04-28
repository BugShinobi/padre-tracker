<script lang="ts">
	import { createQuery } from '@tanstack/svelte-query';
	import { api } from '$lib/api';
	import { fmtMc, fmtPct, fmtNum, fmtDateTime, shortCa } from '$lib/format';
	import type { EnrichedRow, AlertSummaryRow } from '$lib/types';

	const overview = createQuery(() => ({
		queryKey: ['overview'],
		queryFn: api.overview,
		refetchInterval: 60_000
	}));

	const alertSummary = createQuery(() => ({
		queryKey: ['home-alerts-summary'],
		queryFn: () => api.alertsSummary({ minUsd: 1000 }),
		refetchInterval: 60_000
	}));

	const latest = $derived(overview.data?.latest_calls ?? []);
	const topToday = $derived(overview.data?.top_tokens_today ?? []);
	const topWeek = $derived(overview.data?.top_tokens ?? []);
	const whaleMomentum = $derived(alertSummary.data?.data ?? []);

	function changeCls(p: number | null | undefined): string {
		if (p == null) return 'text-zinc-500';
		return p >= 0 ? 'text-emerald-400' : 'text-rose-400';
	}

	function initials(row: EnrichedRow): string {
		return (row.ticker || row.name || row.contract_address || '?').slice(0, 2).toUpperCase();
	}

	function alertInitials(row: AlertSummaryRow): string {
		return (row.target_ticker || row.name || '?').slice(0, 2).toUpperCase();
	}

	function lpClass(lp: string | null | undefined): string {
		const k = (lp || '').split('.')[0].toLowerCase();
		if (k === 'pump') return 'bg-amber-500/12 text-amber-300 border-amber-500/20';
		if (k === 'bags') return 'bg-fuchsia-500/12 text-fuchsia-300 border-fuchsia-500/20';
		if (k === 'bonk') return 'bg-orange-500/12 text-orange-300 border-orange-500/20';
		if (k === 'printr') return 'bg-emerald-500/12 text-emerald-300 border-emerald-500/20';
		return 'bg-zinc-900 text-zinc-400 border-zinc-800';
	}
</script>

{#snippet tokenAvatar(row: EnrichedRow, size = 'md')}
	{@const dim = size === 'lg' ? 'w-11 h-11 text-sm' : 'w-9 h-9 text-xs'}
	{#if row.image_url}
		<img
			src={row.image_url}
			alt=""
			class="{dim} rounded-full object-cover bg-zinc-800 shrink-0 ring-1 ring-zinc-800"
			loading="lazy"
			referrerpolicy="no-referrer"
		/>
	{:else}
		<div class="{dim} rounded-full shrink-0 ring-1 ring-zinc-700 bg-zinc-900 text-zinc-300 grid place-items-center font-semibold">
			{initials(row)}
		</div>
	{/if}
{/snippet}

{#snippet tokenRow(row: EnrichedRow, idx: number)}
	<a
		href="/t/{row.contract_address}"
		class="grid grid-cols-[2rem_minmax(0,1fr)_auto] lg:grid-cols-[2rem_minmax(0,1fr)_8rem_5rem_8rem] items-center gap-3 px-3.5 py-3 min-h-[64px] hover:bg-zinc-900/70 border-t border-zinc-800/70 first:border-t-0 transition-colors"
	>
		<span class="text-xs text-zinc-600 tabular-nums text-right">{idx}</span>
		<div class="flex items-center gap-3 min-w-0">
			{@render tokenAvatar(row)}
			<div class="min-w-0">
				<div class="flex items-center gap-2 min-w-0">
					<span class="font-semibold text-zinc-100 truncate {row.ticker ? '' : 'italic text-zinc-500'}">
						{row.ticker ?? shortCa(row.contract_address)}
					</span>
					{#if row.launchpad}
						<span class="hidden sm:inline-flex px-1.5 py-0.5 rounded border text-[10px] shrink-0 {lpClass(row.launchpad)}">
							{row.launchpad.split('.')[0]}
						</span>
					{/if}
				</div>
				<div class="text-[11px] text-zinc-500 truncate">
					{row.groups_mentioned || row.name || shortCa(row.contract_address)}
				</div>
			</div>
		</div>
		<div class="text-right tabular-nums">
			<div class="text-sm text-zinc-200">{fmtMc(row.market_cap)}</div>
			<div class="text-[11px] {changeCls(row.price_change_h24)}">{fmtPct(row.price_change_h24)}</div>
		</div>
		<div class="hidden lg:block text-right tabular-nums">
			<div class="text-sm text-zinc-200">{fmtNum(row.call_count)}</div>
			<div class="text-[11px] text-zinc-600">calls</div>
		</div>
		<div class="hidden lg:block text-right text-[11px] text-zinc-500 tabular-nums">
			{fmtDateTime(row.last_seen_at)}
		</div>
	</a>
{/snippet}

{#snippet whaleRow(row: AlertSummaryRow, idx: number)}
	<a
		href="/t/{encodeURIComponent(row.target_ca || row.target_ticker)}"
		class="grid grid-cols-[2rem_minmax(0,1fr)_auto] md:grid-cols-[2rem_minmax(0,1fr)_8rem_6rem] items-center gap-3 px-3.5 py-3 min-h-[64px] hover:bg-zinc-900/70 border-t border-zinc-800/70 first:border-t-0 transition-colors"
	>
		<span class="text-xs text-zinc-600 tabular-nums text-right">{idx}</span>
		<div class="flex items-center gap-3 min-w-0">
			{#if row.image_url}
				<img
					src={row.image_url}
					alt=""
					class="w-9 h-9 rounded-full object-cover bg-zinc-800 shrink-0 ring-1 ring-zinc-800"
					loading="lazy"
					referrerpolicy="no-referrer"
				/>
			{:else}
				<div class="w-9 h-9 rounded-full shrink-0 ring-1 ring-zinc-700 bg-zinc-900 text-zinc-300 grid place-items-center font-semibold text-xs">
					{alertInitials(row)}
				</div>
			{/if}
			<div class="min-w-0">
				<div class="font-semibold text-zinc-100 truncate">${row.target_ticker}</div>
				<div class="text-[11px] text-zinc-500 truncate">
					{fmtNum(row.whale_count)} whales · {fmtNum(row.actor_count)} actors
				</div>
			</div>
		</div>
		<div class="text-right tabular-nums">
			<div class="text-sm text-emerald-300">{fmtMc(row.total_amount_usd)}</div>
			<div class="text-[11px] text-zinc-600">added</div>
		</div>
		<div class="hidden md:block text-right tabular-nums">
			<div class="text-sm text-zinc-200">{fmtNum(row.alert_count)}</div>
			<div class="text-[11px] text-zinc-600">alerts</div>
		</div>
	</a>
{/snippet}

{#snippet panel(title: string, href: string, action: string)}
	<div class="flex items-center justify-between gap-3 px-4 py-3 border-b border-zinc-800 bg-zinc-950">
		<h2 class="text-sm font-semibold tracking-wide text-zinc-100 uppercase">{title}</h2>
		<a href={href} class="text-xs font-medium text-zinc-300 hover:text-white transition-colors">{action}</a>
	</div>
{/snippet}

<section class="space-y-6">
	{#if overview.isPending}
		<p class="text-zinc-500">Loading...</p>
	{:else if overview.isError}
		<p class="text-rose-400">Error: {overview.error.message}</p>
	{:else if !overview.data?.ready}
		<p class="text-zinc-500">No data yet. Backend is booting.</p>
	{:else}
		{@const d = overview.data}

		<header class="border border-zinc-800 bg-zinc-950 overflow-hidden rounded-lg">
			<div class="p-5 lg:p-6">
				<div class="min-w-0">
					<div class="flex items-center gap-2 text-xs text-emerald-300 font-medium mb-2">
						<span class="w-2 h-2 rounded-full bg-emerald-400"></span>
						<span>Alpha calls monitor</span>
					</div>
					<h1 class="text-3xl lg:text-4xl font-semibold tracking-tight text-zinc-50">
						Padre signal desk
					</h1>
					<p class="mt-2 text-sm text-zinc-400 max-w-3xl">
						Live Alpha Tracker calls, repeat mentions, whale flow and watchlist actions in one place.
					</p>
				</div>
			</div>

			<div class="grid grid-cols-2 lg:grid-cols-4 border-t border-zinc-800">
				<div class="p-4 border-r border-zinc-800">
					<div class="text-xs text-zinc-500">Tokens today</div>
					<div class="mt-1 text-2xl font-semibold tabular-nums text-zinc-50">{fmtNum(d.today?.tokens ?? 0)}</div>
				</div>
				<div class="p-4 lg:border-r border-zinc-800">
					<div class="text-xs text-zinc-500">Calls today</div>
					<div class="mt-1 text-2xl font-semibold tabular-nums text-zinc-50">{fmtNum(d.today?.total_calls ?? 0)}</div>
				</div>
				<div class="p-4 border-t lg:border-t-0 border-r border-zinc-800">
					<div class="text-xs text-zinc-500">7d tokens</div>
					<div class="mt-1 text-2xl font-semibold tabular-nums text-zinc-50">{fmtNum(d.week_totals?.tokens ?? 0)}</div>
				</div>
				<div class="p-4 border-t lg:border-t-0 border-zinc-800">
					<div class="text-xs text-zinc-500">7d calls</div>
					<div class="mt-1 text-2xl font-semibold tabular-nums text-zinc-50">{fmtNum(d.week_totals?.total_calls ?? 0)}</div>
				</div>
			</div>
		</header>

		<div class="grid grid-cols-1 xl:grid-cols-[minmax(0,1.25fr)_minmax(420px,0.75fr)] gap-5">
			<section class="rounded-lg border border-zinc-800 bg-zinc-950/60 overflow-hidden">
				{@render panel('Latest calls', '/day', 'Open day board')}
				{#if latest.length === 0}
					<div class="p-8 text-center text-sm text-zinc-500">No calls yet.</div>
				{:else}
					<div class="max-h-[640px] overflow-y-auto">
						{#each latest as row, i (row.contract_address)}
							{@render tokenRow(row, i + 1)}
						{/each}
					</div>
				{/if}
			</section>

			<section class="rounded-lg border border-zinc-800 bg-zinc-950/60 overflow-hidden">
				{@render panel('Whale momentum', '/alerts', 'Open alerts')}
				{#if alertSummary.isPending}
					<div class="p-8 text-center text-sm text-zinc-500">Loading...</div>
				{:else if whaleMomentum.length === 0}
					<div class="p-8 text-center text-sm text-zinc-500">No whale alerts yet.</div>
				{:else}
					<div class="max-h-[640px] overflow-y-auto">
						{#each whaleMomentum as row, i (`${row.target_ticker}-${row.target_ca ?? i}`)}
							{@render whaleRow(row, i + 1)}
						{/each}
					</div>
				{/if}
			</section>
		</div>

		<div class="grid grid-cols-1 xl:grid-cols-2 gap-5">
			<section class="rounded-lg border border-zinc-800 bg-zinc-950/60 overflow-hidden">
				{@render panel('Most called today', '/day?sortField=call_count&sortDir=desc', 'Open ranking')}
				{#if topToday.length === 0}
					<div class="p-8 text-center text-sm text-zinc-500">No calls today yet.</div>
				{:else}
					<div class="max-h-[640px] overflow-y-auto">
						{#each topToday as row, i (row.contract_address)}
							{@render tokenRow(row, i + 1)}
						{/each}
					</div>
				{/if}
			</section>

			<section class="rounded-lg border border-zinc-800 bg-zinc-950/60 overflow-hidden">
				{@render panel('Most called 7d', '/range?sortField=call_count&sortDir=desc', 'Open range')}
				{#if topWeek.length === 0}
					<div class="p-8 text-center text-sm text-zinc-500">No calls in the last 7 days.</div>
				{:else}
					<div class="max-h-[640px] overflow-y-auto">
						{#each topWeek as row, i (row.contract_address)}
							{@render tokenRow(row, i + 1)}
						{/each}
					</div>
				{/if}
			</section>
		</div>
	{/if}
</section>
