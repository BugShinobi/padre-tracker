<script lang="ts">
	import { live } from '$lib/sse.svelte';
	import { fmtMc, fmtPct, fmtAge, fmtDateTime, shortCa } from '$lib/format';
	import StatusDot from '$lib/components/StatusDot.svelte';
</script>

<section>
	<header class="mb-4 flex items-end justify-between gap-4 flex-wrap">
		<div>
			<h1 class="text-3xl font-semibold tracking-tight">Live</h1>
			<div class="flex items-center gap-2 mt-1 text-sm text-zinc-500">
				<StatusDot connected={live.connected} />
				<span>
					{live.connected ? 'streaming' : 'reconnecting…'}
				</span>
				{#if live.lastTickAt}
					<span class="text-xs text-zinc-600">last tick {new Date(live.lastTickAt).toLocaleTimeString()}</span>
				{/if}
			</div>
		</div>
		<div class="text-sm text-zinc-500 tabular-nums">{live.items.length} in feed</div>
	</header>

	{#if live.items.length === 0}
		<div class="rounded-lg border border-zinc-800 px-4 py-12 text-center text-zinc-500">
			Watching for new tokens… the feed updates as soon as a call is detected.
		</div>
	{:else}
		<div class="rounded-lg border border-zinc-800 overflow-hidden">
			<table class="w-full text-sm">
				<thead class="bg-zinc-900/60 text-zinc-400 uppercase text-xs tracking-wider">
					<tr>
						<th class="text-left px-3 py-2 font-normal">Token</th>
						<th class="text-left px-3 py-2 font-normal">CA</th>
						<th class="text-left px-3 py-2 font-normal">LP</th>
						<th class="text-right px-3 py-2 font-normal">Calls</th>
						<th class="text-right px-3 py-2 font-normal">MC</th>
						<th class="text-right px-3 py-2 font-normal">24h</th>
						<th class="text-left px-3 py-2 font-normal">Groups</th>
						<th class="text-left px-3 py-2 font-normal">First seen</th>
					</tr>
				</thead>
				<tbody>
					{#each live.items as r (r.contract_address)}
						<tr
							class="border-t border-zinc-800/60 hover:bg-zinc-900/40 cursor-pointer transition-colors"
							onclick={() => (window.location.href = `/t/${r.contract_address}`)}
						>
							<td class="px-3 py-2.5">
								<div class="flex items-center gap-2.5">
									{#if r.image_url}
										<img
											src={r.image_url}
											alt=""
											class="w-7 h-7 rounded-full object-cover bg-zinc-800 shrink-0"
											loading="lazy"
											referrerpolicy="no-referrer"
										/>
									{:else}
										<div class="w-7 h-7 rounded-full bg-zinc-800 shrink-0"></div>
									{/if}
									<div class="font-medium text-zinc-100">
										{r.ticker ?? shortCa(r.contract_address)}
									</div>
								</div>
							</td>
							<td class="px-3 py-2.5 font-mono text-xs text-zinc-400">{shortCa(r.contract_address)}</td>
							<td class="px-3 py-2.5 text-xs text-zinc-300">{r.launchpad ?? '—'}</td>
							<td class="px-3 py-2.5 text-right tabular-nums">{r.call_count}</td>
							<td class="px-3 py-2.5 text-right tabular-nums">{fmtMc(r.market_cap)}</td>
							<td
								class="px-3 py-2.5 text-right tabular-nums {r.price_change_h24 == null
									? 'text-zinc-500'
									: r.price_change_h24 >= 0
										? 'text-emerald-400'
										: 'text-rose-400'}"
							>{fmtPct(r.price_change_h24)}</td>
							<td class="px-3 py-2.5 text-xs text-zinc-400 max-w-[180px] truncate" title={r.groups_mentioned ?? ''}>
								{r.groups_mentioned ?? '—'}
							</td>
							<td class="px-3 py-2.5 text-xs text-zinc-400 tabular-nums whitespace-nowrap">
								{fmtDateTime(r.first_seen_at)}
								{#if r.creation_timestamp}
									<span class="text-zinc-600 ml-1">({fmtAge(r.creation_timestamp)})</span>
								{/if}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}

	<p class="mt-4 text-xs text-zinc-600">
		The feed keeps the {live.items.length || 'last 20'} most recent calls received in this browser session.
		Refresh the page or open <a href="/day" class="underline hover:text-zinc-400">Day</a> for the full history.
	</p>
</section>
