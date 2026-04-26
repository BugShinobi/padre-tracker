<script lang="ts">
	import { createQuery } from '@tanstack/svelte-query';
	import { api, fmtMc, fmtPct, shortCa } from '$lib/api';
	import { live } from '$lib/sse.svelte';
	import KpiCard from '$lib/components/KpiCard.svelte';
	import TokenCard from '$lib/components/TokenCard.svelte';
	import GroupCard from '$lib/components/GroupCard.svelte';
	import Surface from '$lib/components/Surface.svelte';
	import Sparkline from '$lib/components/Sparkline.svelte';

	const overview = createQuery(() => ({
		queryKey: ['overview'],
		queryFn: api.overview,
		refetchInterval: 60_000
	}));

	const week = $derived(overview.data?.week ?? []);
	const tokensSpark = $derived(week.map((w) => w.tokens));
	const callsSpark = $derived(week.map((w) => w.total_calls));

	const avgCallsPerToken = $derived.by(() => {
		const t = overview.data?.today?.tokens ?? 0;
		const c = overview.data?.today?.total_calls ?? 0;
		return t > 0 ? Math.round(c / t) : 0;
	});

	const groupsCount = $derived((overview.data?.groups ?? []).length);

	const topMovers = $derived.by(() => {
		const tokens = overview.data?.top_tokens ?? [];
		return [...tokens]
			.filter((t) => t.price_change_h24 != null)
			.sort((a, b) => (b.price_change_h24 ?? 0) - (a.price_change_h24 ?? 0))
			.slice(0, 5);
	});

	const maxGroupTokens = $derived.by(() => {
		const groups = overview.data?.groups ?? [];
		return groups.reduce((m, g) => Math.max(m, g.tokens), 0);
	});
</script>

<section class="space-y-8">
	{#if overview.isPending}
		<p class="text-zinc-500">Loading…</p>
	{:else if overview.isError}
		<p class="text-rose-400">Error: {overview.error.message}</p>
	{:else if !overview.data?.ready}
		<p class="text-zinc-500">No data yet — backend booting.</p>
	{:else}
		{@const d = overview.data}

		<header class="flex items-end justify-between gap-4">
			<div>
				<h1 class="text-3xl font-semibold tracking-tight">Today</h1>
				<p class="text-sm text-zinc-500">{d.date}</p>
			</div>
			<div class="text-xs text-zinc-500 text-right">
				<div>Week total</div>
				<div class="text-zinc-300 text-sm tabular-nums font-medium">
					{(d.week_totals?.tokens ?? 0).toLocaleString('en-US')} tokens · {(
						d.week_totals?.total_calls ?? 0
					).toLocaleString('en-US')} calls
				</div>
			</div>
		</header>

		<div class="grid grid-cols-2 lg:grid-cols-4 gap-3">
			<KpiCard
				label="Tokens today"
				value={d.today?.tokens ?? 0}
				delta={d.delta?.tokens}
				spark={tokensSpark}
				variant="gradient-pos"
				sparkStroke="rgb(52 211 153)"
				sparkFill="rgb(52 211 153 / 0.15)"
			/>
			<KpiCard
				label="Calls today"
				value={d.today?.total_calls ?? 0}
				delta={d.delta?.calls}
				spark={callsSpark}
				variant="gradient-cool"
				sparkStroke="rgb(96 165 250)"
				sparkFill="rgb(96 165 250 / 0.15)"
			/>
			<KpiCard label="Active groups" value={groupsCount} variant="card" />
			<KpiCard label="Avg calls/token" value={avgCallsPerToken} variant="card" />
		</div>

		<section>
			<div class="flex items-center justify-between mb-3">
				<h2 class="text-lg font-semibold tracking-tight">Live activity</h2>
				<a
					href="/live"
					class="text-sm text-zinc-400 hover:text-zinc-200 flex items-center gap-1 transition-colors"
				>
					See all <span aria-hidden="true">→</span>
				</a>
			</div>
			{#if live.items.length === 0}
				<Surface variant="card" padding="lg">
					<p class="text-sm text-zinc-500">Watching for new tokens…</p>
				</Surface>
			{:else}
				<div class="grid grid-cols-1 md:grid-cols-2 gap-3">
					{#each live.items.slice(0, 4) as row (row.contract_address)}
						<TokenCard {row} />
					{/each}
				</div>
			{/if}
		</section>

		{#if topMovers.length > 0}
			<section>
				<h2 class="text-lg font-semibold tracking-tight mb-3">Top movers · 24h</h2>
				<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-3">
					{#each topMovers as row (row.contract_address)}
						<a href="/t/{row.contract_address}" class="block">
							<Surface variant="card" hover padding="md">
								<div class="flex items-center gap-2 mb-2">
									{#if row.image_url}
										<img
											src={row.image_url}
											alt=""
											class="w-7 h-7 rounded-full bg-zinc-800 shrink-0"
											loading="lazy"
											referrerpolicy="no-referrer"
										/>
									{:else}
										<div class="w-7 h-7 rounded-full bg-zinc-800 shrink-0"></div>
									{/if}
									<span class="font-semibold truncate">
										{row.ticker ?? shortCa(row.contract_address)}
									</span>
								</div>
								<div class="text-2xl font-semibold tabular-nums {(row.price_change_h24 ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}">
									{fmtPct(row.price_change_h24)}
								</div>
								<div class="text-xs text-zinc-500 tabular-nums">{fmtMc(row.market_cap)}</div>
							</Surface>
						</a>
					{/each}
				</div>
			</section>
		{/if}

		<section class="grid grid-cols-1 lg:grid-cols-3 gap-3">
			<Surface variant="card" padding="lg" class="lg:col-span-2">
				<div class="flex items-center justify-between mb-2">
					<div class="text-xs uppercase tracking-wider text-zinc-500 font-medium">Tokens · 7d</div>
					<div class="text-xs text-zinc-400 tabular-nums">
						{(d.week_totals?.tokens ?? 0).toLocaleString('en-US')}
					</div>
				</div>
				<Sparkline
					data={tokensSpark}
					stroke="rgb(52 211 153)"
					fill="rgb(52 211 153 / 0.18)"
					height={80}
					strokeWidth={2}
				/>
			</Surface>
			<Surface variant="card" padding="lg">
				<div class="flex items-center justify-between mb-2">
					<div class="text-xs uppercase tracking-wider text-zinc-500 font-medium">Calls · 7d</div>
					<div class="text-xs text-zinc-400 tabular-nums">
						{(d.week_totals?.total_calls ?? 0).toLocaleString('en-US')}
					</div>
				</div>
				<Sparkline
					data={callsSpark}
					stroke="rgb(96 165 250)"
					fill="rgb(96 165 250 / 0.18)"
					height={80}
					strokeWidth={2}
				/>
			</Surface>
		</section>

		<section>
			<h2 class="text-lg font-semibold tracking-tight mb-3">Top tokens · week</h2>
			<div class="grid grid-cols-1 md:grid-cols-2 gap-3">
				{#each (d.top_tokens ?? []).slice(0, 10) as row (row.contract_address)}
					<TokenCard {row} variant="expanded" />
				{/each}
			</div>
		</section>

		<section>
			<h2 class="text-lg font-semibold tracking-tight mb-3">Top groups · week</h2>
			<div class="grid grid-cols-1 md:grid-cols-2 gap-3">
				{#each (d.groups ?? []).slice(0, 10) as group, i (group.name ?? group.group ?? i)}
					<GroupCard {group} rank={i + 1} maxTokens={maxGroupTokens} />
				{/each}
			</div>
		</section>
	{/if}
</section>
