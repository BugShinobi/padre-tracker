<script lang="ts">
	import { createQuery } from '@tanstack/svelte-query';
	import { api, fmtMc, fmtPct, shortCa } from '$lib/api';

	const overview = createQuery(() => ({
		queryKey: ['overview'],
		queryFn: api.overview,
		refetchInterval: 60_000
	}));

	const deltaClass = (cls: string | undefined) =>
		cls === 'pos' ? 'text-emerald-400' : cls === 'neg' ? 'text-rose-400' : 'text-zinc-500';

	const changeClass = (v: number | null | undefined) =>
		v == null ? 'text-zinc-500' : v >= 0 ? 'text-emerald-400' : 'text-rose-400';
</script>

<section>
	{#if overview.isPending}
		<p class="text-zinc-500">Loading…</p>
	{:else if overview.isError}
		<p class="text-rose-400">Error: {overview.error.message}</p>
	{:else if !overview.data?.ready}
		<p class="text-zinc-500">No data yet — backend booting.</p>
	{:else}
		{@const d = overview.data}
		<h1 class="text-2xl font-semibold mb-1">Today</h1>
		<p class="text-sm text-zinc-500 mb-6">{d.date}</p>

		<div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
			<div class="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
				<div class="text-xs uppercase tracking-wider text-zinc-500">Tokens today</div>
				<div class="mt-1 text-2xl font-semibold">{d.today?.tokens ?? 0}</div>
				<div class="text-xs mt-1 {deltaClass(d.delta?.tokens.class)}">
					{d.delta?.tokens.str ?? ''} vs ieri
				</div>
			</div>
			<div class="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
				<div class="text-xs uppercase tracking-wider text-zinc-500">Calls today</div>
				<div class="mt-1 text-2xl font-semibold">{d.today?.total_calls ?? 0}</div>
				<div class="text-xs mt-1 {deltaClass(d.delta?.calls.class)}">
					{d.delta?.calls.str ?? ''} vs ieri
				</div>
			</div>
			<div class="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
				<div class="text-xs uppercase tracking-wider text-zinc-500">Tokens 7d</div>
				<div class="mt-1 text-2xl font-semibold">{d.week_totals?.tokens ?? 0}</div>
			</div>
			<div class="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
				<div class="text-xs uppercase tracking-wider text-zinc-500">Calls 7d</div>
				<div class="mt-1 text-2xl font-semibold">{d.week_totals?.total_calls ?? 0}</div>
			</div>
		</div>

		<h2 class="text-lg font-semibold mb-3">Top tokens (week)</h2>
		<div class="rounded-lg border border-zinc-800 overflow-hidden">
			<table class="w-full text-sm">
				<thead class="bg-zinc-900/60 text-zinc-400 uppercase text-xs tracking-wider">
					<tr>
						<th class="text-left px-3 py-2 font-normal">#</th>
						<th class="text-left px-3 py-2 font-normal">Ticker</th>
						<th class="text-left px-3 py-2 font-normal">CA</th>
						<th class="text-right px-3 py-2 font-normal">Calls</th>
						<th class="text-right px-3 py-2 font-normal">MC</th>
						<th class="text-right px-3 py-2 font-normal">24h</th>
						<th class="text-left px-3 py-2 font-normal">Age</th>
					</tr>
				</thead>
				<tbody>
					{#each d.top_tokens ?? [] as t, i (t.contract_address)}
						<tr class="border-t border-zinc-800 hover:bg-zinc-900/30">
							<td class="px-3 py-2 text-zinc-500">{i + 1}</td>
							<td class="px-3 py-2">
								<div class="flex items-center gap-2">
									{#if t.image_url}
										<img
											src={t.image_url}
											alt=""
											class="w-6 h-6 rounded-full object-cover bg-zinc-800"
											loading="lazy"
											referrerpolicy="no-referrer"
										/>
									{:else}
										<div class="w-6 h-6 rounded-full bg-zinc-800"></div>
									{/if}
									<span
										class="font-medium"
										title={t.description ?? t.name ?? ''}
									>{t.ticker ?? '—'}</span>
								</div>
							</td>
							<td class="px-3 py-2 font-mono text-xs text-zinc-400">{shortCa(t.contract_address)}</td>
							<td class="px-3 py-2 text-right tabular-nums">{t.call_count}</td>
							<td class="px-3 py-2 text-right tabular-nums">{fmtMc(t.market_cap)}</td>
							<td class="px-3 py-2 text-right tabular-nums {changeClass(t.change_24h)}">
								{fmtPct(t.change_24h)}
							</td>
							<td class="px-3 py-2 text-zinc-400">{t.age_str ?? '—'}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</section>
