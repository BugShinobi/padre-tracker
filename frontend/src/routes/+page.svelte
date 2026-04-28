<script lang="ts">
	import { createQuery } from '@tanstack/svelte-query';
	import { api } from '$lib/api';
	import { fmtMc, fmtPct, fmtNum, fmtDateTime, shortCa } from '$lib/format';
	import type { EnrichedRow } from '$lib/types';

	const overview = createQuery(() => ({
		queryKey: ['overview'],
		queryFn: api.overview,
		refetchInterval: 60_000
	}));

	const latest = $derived(overview.data?.latest_calls ?? []);
	const topToday = $derived(overview.data?.top_tokens_today ?? []);
	const topWeek = $derived(overview.data?.top_tokens ?? []);

	function changeCls(p: number | null | undefined): string {
		if (p == null) return 'text-zinc-500';
		return p >= 0 ? 'text-emerald-400' : 'text-rose-400';
	}
</script>

{#snippet tokenLine(row: EnrichedRow, idx: number)}
	<a
		href="/t/{row.contract_address}"
		class="flex items-center gap-3 px-3 py-2 hover:bg-zinc-900/60 border-t border-zinc-800/60 first:border-t-0 transition-colors"
	>
		<span class="text-xs text-zinc-600 tabular-nums w-5 shrink-0 text-right">{idx}</span>
		{#if row.image_url}
			<img
				src={row.image_url}
				alt=""
				class="w-7 h-7 rounded-full object-cover bg-zinc-800 shrink-0"
				loading="lazy"
				referrerpolicy="no-referrer"
			/>
		{:else}
			<div class="w-7 h-7 rounded-full bg-zinc-800 shrink-0"></div>
		{/if}
		<div class="min-w-0 flex-1">
			<div class="flex items-center gap-2">
				<span class="font-medium text-zinc-100 truncate {row.ticker ? '' : 'italic text-zinc-500'}">
					{row.ticker ?? shortCa(row.contract_address)}
				</span>
				{#if row.launchpad}
					<span class="text-[10px] text-zinc-500 shrink-0">{row.launchpad.split('.')[0]}</span>
				{/if}
			</div>
			{#if row.groups_mentioned}
				<div class="text-[11px] text-zinc-500 truncate">{row.groups_mentioned}</div>
			{/if}
		</div>
		<div class="text-right shrink-0">
			<div class="text-sm tabular-nums text-zinc-300">{fmtMc(row.market_cap)}</div>
			<div class="text-[11px] tabular-nums {changeCls(row.price_change_h24)}">
				{fmtPct(row.price_change_h24)}
			</div>
		</div>
		<div class="text-right shrink-0 hidden sm:block">
			<div class="text-sm tabular-nums text-zinc-400">{fmtNum(row.call_count)}</div>
			<div class="text-[11px] text-zinc-600">calls</div>
		</div>
		<div class="text-[11px] text-zinc-500 tabular-nums shrink-0 hidden md:block w-24 text-right">
			{fmtDateTime(row.last_seen_at)}
		</div>
	</a>
{/snippet}

<section class="space-y-8">
	{#if overview.isPending}
		<p class="text-zinc-500">Loading…</p>
	{:else if overview.isError}
		<p class="text-rose-400">Error: {overview.error.message}</p>
	{:else if !overview.data?.ready}
		<p class="text-zinc-500">No data yet — backend booting.</p>
	{:else}
		{@const d = overview.data}

		<header class="flex items-end justify-between gap-4 flex-wrap">
			<div>
				<h1 class="text-3xl font-semibold tracking-tight">padre-tracker</h1>
				<p class="text-sm text-zinc-500 mt-0.5">
					{fmtNum(d.today?.tokens ?? 0)} tokens · {fmtNum(d.today?.total_calls ?? 0)} calls today
					<span class="text-zinc-600">·</span>
					{fmtNum(d.week_totals?.tokens ?? 0)} · {fmtNum(d.week_totals?.total_calls ?? 0)} this week
				</p>
			</div>
			<div class="flex gap-2 text-xs">
				<a href="/day" class="px-3 py-1.5 rounded border border-zinc-800 text-zinc-300 hover:bg-zinc-900 transition-colors">Day →</a>
				<a href="/range" class="px-3 py-1.5 rounded border border-zinc-800 text-zinc-300 hover:bg-zinc-900 transition-colors">Range →</a>
			</div>
		</header>

		<section>
			<div class="flex items-center justify-between mb-3">
				<h2 class="text-lg font-semibold tracking-tight">Latest calls</h2>
				<a href="/day" class="text-xs text-zinc-400 hover:text-zinc-200 transition-colors">See all →</a>
			</div>
			{#if latest.length === 0}
				<div class="rounded-lg border border-zinc-800 p-6 text-center text-sm text-zinc-500">
					No calls yet.
				</div>
			{:else}
				<div class="rounded-lg border border-zinc-800 overflow-hidden bg-zinc-950/40">
					{#each latest as row, i (row.contract_address)}
						{@render tokenLine(row, i + 1)}
					{/each}
				</div>
			{/if}
		</section>

		<div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
			<section>
				<div class="flex items-center justify-between mb-3">
					<h2 class="text-lg font-semibold tracking-tight">Most called · today</h2>
					<a
						href="/day?sortField=call_count&sortDir=desc"
						class="text-xs text-zinc-400 hover:text-zinc-200 transition-colors"
					>See all →</a>
				</div>
				{#if topToday.length === 0}
					<div class="rounded-lg border border-zinc-800 p-6 text-center text-sm text-zinc-500">
						No calls today yet.
					</div>
				{:else}
					<div class="rounded-lg border border-zinc-800 overflow-hidden bg-zinc-950/40">
						{#each topToday as row, i (row.contract_address)}
							{@render tokenLine(row, i + 1)}
						{/each}
					</div>
				{/if}
			</section>

			<section>
				<div class="flex items-center justify-between mb-3">
					<h2 class="text-lg font-semibold tracking-tight">Most called · 7d</h2>
					<a
						href="/range?sortField=call_count&sortDir=desc"
						class="text-xs text-zinc-400 hover:text-zinc-200 transition-colors"
					>See all →</a>
				</div>
				{#if topWeek.length === 0}
					<div class="rounded-lg border border-zinc-800 p-6 text-center text-sm text-zinc-500">
						No calls in the last 7 days.
					</div>
				{:else}
					<div class="rounded-lg border border-zinc-800 overflow-hidden bg-zinc-950/40">
						{#each topWeek as row, i (row.contract_address)}
							{@render tokenLine(row, i + 1)}
						{/each}
					</div>
				{/if}
			</section>
		</div>
	{/if}
</section>
