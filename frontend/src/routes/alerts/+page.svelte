<script lang="ts">
	import { page as pageStore } from '$app/state';
	import { goto } from '$app/navigation';
	import { createInfiniteQuery, createQuery } from '@tanstack/svelte-query';
	import { api } from '$lib/api';
	import { fmtNum, fmtMc } from '$lib/format';
	import type { AlertsResponse, AlertType } from '$lib/types';

	const PAGE_SIZE = 100;

	const params = pageStore.url.searchParams;

	let typeFilter = $state<string>(params.get('type') || 'all');
	let tickerInput = $state(params.get('ticker') || '');
	let actorInput = $state(params.get('actor') || '');
	let ticker = $state(params.get('ticker') || '');
	let actor = $state(params.get('actor') || '');
	let minUsd = $state<number>(Number(params.get('minUsd')) || 0);
	let mcMin = $state<number>(Number(params.get('mcMin')) || 0);
	let mcMax = $state<number>(Number(params.get('mcMax')) || 0);

	let tickerTimer: ReturnType<typeof setTimeout> | null = null;
	$effect(() => {
		const v = tickerInput;
		if (tickerTimer) clearTimeout(tickerTimer);
		tickerTimer = setTimeout(() => {
			ticker = v;
		}, 300);
	});

	let actorTimer: ReturnType<typeof setTimeout> | null = null;
	$effect(() => {
		const v = actorInput;
		if (actorTimer) clearTimeout(actorTimer);
		actorTimer = setTimeout(() => {
			actor = v;
		}, 300);
	});

	$effect(() => {
		const sp = new URLSearchParams();
		if (typeFilter !== 'all') sp.set('type', typeFilter);
		if (ticker) sp.set('ticker', ticker);
		if (actor) sp.set('actor', actor);
		if (minUsd > 0) sp.set('minUsd', String(minUsd));
		if (mcMin > 0) sp.set('mcMin', String(mcMin));
		if (mcMax > 0) sp.set('mcMax', String(mcMax));
		const qs = sp.toString();
		goto(qs ? `?${qs}` : '?', { replaceState: true, noScroll: true, keepFocus: true });
	});

	const alertsQuery = createInfiniteQuery(() => ({
		queryKey: ['alerts', typeFilter, ticker, actor, minUsd, mcMin, mcMax],
		initialPageParam: 1,
		queryFn: ({ pageParam }) =>
			api.alerts({
				page: pageParam as number,
				pageSize: PAGE_SIZE,
				type: typeFilter,
				ticker: ticker || undefined,
				actor: actor || undefined,
				minUsd: minUsd > 0 ? minUsd : undefined,
				minMc: mcMin > 0 ? mcMin : undefined,
				maxMc: mcMax > 0 ? mcMax : undefined
			}),
		getNextPageParam: (lastPage: AlertsResponse) =>
			lastPage.page < lastPage.pageCount ? lastPage.page + 1 : undefined,
		refetchInterval: 30_000
	}));

	const allRows = $derived(alertsQuery.data?.pages.flatMap((p) => p.data) ?? []);
	const totalRows = $derived(alertsQuery.data?.pages[0]?.rowCount ?? 0);

	const statsQuery = createQuery(() => ({
		queryKey: ['alerts-stats'],
		queryFn: api.alertsStats,
		refetchInterval: 60_000
	}));

	let sentinel: HTMLDivElement | undefined = $state();
	$effect(() => {
		if (!sentinel) return;
		const obs = new IntersectionObserver(
			(entries) => {
				if (entries[0].isIntersecting && alertsQuery.hasNextPage && !alertsQuery.isFetchingNextPage) {
					alertsQuery.fetchNextPage();
				}
			},
			{ rootMargin: '300px' }
		);
		obs.observe(sentinel);
		return () => obs.disconnect();
	});

	const TYPE_LABEL: Record<AlertType | 'all', string> = {
		all: 'All',
		whale: '🐳 Whale',
		kol: '🧠 KOL',
		kol_newpair: '🌱 KOL New'
	};
	const TYPES: ('all' | AlertType)[] = ['all', 'whale', 'kol', 'kol_newpair'];

	function typeBadgeCls(t: string | null): string {
		if (t === 'whale') return 'bg-blue-900/40 text-blue-300';
		if (t === 'kol') return 'bg-purple-900/40 text-purple-300';
		if (t === 'kol_newpair') return 'bg-emerald-900/40 text-emerald-300';
		return 'bg-zinc-800 text-zinc-400';
	}

	function fmtTimeShort(iso: string): string {
		if (!iso) return '—';
		const d = new Date(iso);
		const now = new Date();
		const sameDay = d.toDateString() === now.toDateString();
		if (sameDay) {
			return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
		}
		return d.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ' ' +
			d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
	}

	function clearFilters() {
		typeFilter = 'all';
		tickerInput = '';
		actorInput = '';
		ticker = '';
		actor = '';
		minUsd = 0;
		mcMin = 0;
		mcMax = 0;
	}

	let expanded = $state<Set<number>>(new Set());
	function toggleExpand(id: number) {
		const s = new Set(expanded);
		if (s.has(id)) s.delete(id);
		else s.add(id);
		expanded = s;
	}
</script>

<section>
	<header class="mb-4 flex items-end justify-between gap-4 flex-wrap">
		<div>
			<h1 class="text-2xl font-semibold tracking-tight">🐳 Alerts</h1>
			<p class="text-sm text-zinc-500 mt-0.5">
				{#if statsQuery.data}
					{fmtNum(statsQuery.data.alerts_today)} today · {fmtNum(totalRows)} total
				{:else}
					Loading…
				{/if}
			</p>
		</div>
		<button
			type="button"
			onclick={clearFilters}
			class="text-xs px-3 py-1.5 rounded border border-zinc-800 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900 transition-colors"
		>
			Clear filters
		</button>
	</header>

	<div class="grid lg:grid-cols-[240px_1fr] gap-6">
		<aside class="space-y-4 lg:sticky lg:top-20 self-start">
			<div>
				<div class="text-xs uppercase tracking-wider text-zinc-500 mb-2">Type</div>
				<div class="flex flex-wrap gap-1.5">
					{#each TYPES as t}
						<button
							type="button"
							onclick={() => (typeFilter = t)}
							class="px-2.5 py-1 rounded text-xs border transition-colors {typeFilter === t
								? 'border-zinc-400 bg-zinc-800 text-zinc-100'
								: 'border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200'}"
						>{TYPE_LABEL[t]}</button>
					{/each}
				</div>
			</div>

			<div>
				<label class="block text-xs uppercase tracking-wider text-zinc-500 mb-1.5" for="ticker-input">Ticker</label>
				<input
					id="ticker-input"
					type="text"
					bind:value={tickerInput}
					placeholder="e.g. ZEREBRO"
					class="w-full px-2.5 py-1.5 text-sm rounded bg-zinc-900 border border-zinc-800 text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-600"
				/>
			</div>

			<div>
				<label class="block text-xs uppercase tracking-wider text-zinc-500 mb-1.5" for="actor-input">Actor</label>
				<input
					id="actor-input"
					type="text"
					bind:value={actorInput}
					placeholder="e.g. MarcellxMarcell"
					class="w-full px-2.5 py-1.5 text-sm rounded bg-zinc-900 border border-zinc-800 text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-600"
				/>
			</div>

			<div>
				<label class="block text-xs uppercase tracking-wider text-zinc-500 mb-1.5" for="min-usd">Min $ Amount</label>
				<input
					id="min-usd"
					type="number"
					min="0"
					bind:value={minUsd}
					class="w-full px-2.5 py-1.5 text-sm rounded bg-zinc-900 border border-zinc-800 text-zinc-100 tabular-nums focus:outline-none focus:border-zinc-600"
				/>
			</div>

			<div>
				<div class="text-xs uppercase tracking-wider text-zinc-500 mb-1.5">MC Range ($)</div>
				<div class="flex gap-1.5">
					<input
						type="number"
						min="0"
						bind:value={mcMin}
						placeholder="min"
						class="w-1/2 px-2.5 py-1.5 text-sm rounded bg-zinc-900 border border-zinc-800 text-zinc-100 placeholder:text-zinc-600 tabular-nums focus:outline-none focus:border-zinc-600"
					/>
					<input
						type="number"
						min="0"
						bind:value={mcMax}
						placeholder="max"
						class="w-1/2 px-2.5 py-1.5 text-sm rounded bg-zinc-900 border border-zinc-800 text-zinc-100 placeholder:text-zinc-600 tabular-nums focus:outline-none focus:border-zinc-600"
					/>
				</div>
			</div>

			{#if statsQuery.data && statsQuery.data.top_actors_7d.length > 0}
				<div>
					<div class="text-xs uppercase tracking-wider text-zinc-500 mb-2">Top actors · 7d</div>
					<div class="space-y-1">
						{#each statsQuery.data.top_actors_7d.slice(0, 6) as a}
							<button
								type="button"
								onclick={() => (actorInput = a.actor)}
								class="w-full text-left flex items-center justify-between gap-2 text-xs text-zinc-400 hover:text-zinc-100 transition-colors"
							>
								<span class="truncate">{a.actor}</span>
								<span class="text-zinc-600 tabular-nums shrink-0">{a.hits}</span>
							</button>
						{/each}
					</div>
				</div>
			{/if}
		</aside>

		<div>
			{#if alertsQuery.isPending}
				<div class="py-12 text-center text-zinc-500">Loading…</div>
			{:else if alertsQuery.isError}
				<div class="py-12 text-center text-rose-400">Error: {alertsQuery.error.message}</div>
			{:else if allRows.length === 0}
				<div class="rounded-lg border border-zinc-800 p-8 text-center text-sm text-zinc-500">
					No alerts match the current filters.
				</div>
			{:else}
				<div class="rounded-lg border border-zinc-800 overflow-hidden bg-zinc-950/40">
					<table class="w-full text-sm">
						<thead class="bg-zinc-900/60 text-zinc-500 uppercase text-[10px] tracking-wider">
							<tr>
								<th class="text-left px-3 py-2 font-normal w-24">Time</th>
								<th class="text-left px-3 py-2 font-normal w-24">Type</th>
								<th class="text-left px-3 py-2 font-normal">Actor</th>
								<th class="text-left px-3 py-2 font-normal">Ticker</th>
								<th class="text-right px-3 py-2 font-normal w-24">Amount</th>
								<th class="text-right px-3 py-2 font-normal w-24">MC</th>
								<th class="text-left px-3 py-2 font-normal">Message</th>
							</tr>
						</thead>
						<tbody>
							{#each allRows as row (row.id)}
								<tr
									class="border-t border-zinc-800/60 hover:bg-zinc-900/40 cursor-pointer"
									onclick={() => toggleExpand(row.id)}
								>
									<td class="px-3 py-2 text-zinc-400 tabular-nums text-xs whitespace-nowrap">{fmtTimeShort(row.msg_date)}</td>
									<td class="px-3 py-2">
										<span class="px-1.5 py-0.5 rounded text-[10px] {typeBadgeCls(row.alert_type)}">{row.alert_type ?? '?'}</span>
									</td>
									<td class="px-3 py-2 text-zinc-300 truncate max-w-[200px]">{row.actor ?? '—'}</td>
									<td class="px-3 py-2 font-medium text-zinc-100">
										{#if row.target_ticker}
											<span>${row.target_ticker}</span>
										{:else}
											<span class="text-zinc-600">—</span>
										{/if}
									</td>
									<td class="px-3 py-2 text-right tabular-nums text-zinc-300">{fmtMc(row.amount_usd)}</td>
									<td class="px-3 py-2 text-right tabular-nums text-zinc-400">{fmtMc(row.market_cap_usd)}</td>
									<td class="px-3 py-2 text-zinc-500 text-xs">
										{#if expanded.has(row.id)}
											<div class="whitespace-pre-wrap break-words">{row.msg_text}</div>
										{:else}
											<div class="truncate max-w-[400px]">{row.msg_text}</div>
										{/if}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>

				<div bind:this={sentinel} class="h-1" aria-hidden="true"></div>

				<div class="mt-4 text-center text-xs text-zinc-500">
					{#if alertsQuery.isFetchingNextPage}
						Loading more…
					{:else if alertsQuery.hasNextPage}
						<button
							type="button"
							onclick={() => alertsQuery.fetchNextPage()}
							class="px-3 py-1.5 rounded border border-zinc-800 hover:bg-zinc-900 transition-colors"
						>Load more</button>
					{:else}
						— end of list —
					{/if}
				</div>
			{/if}
		</div>
	</div>
</section>
