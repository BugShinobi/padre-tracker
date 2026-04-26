<script lang="ts">
	import { page as pageStore } from '$app/state';
	import { createQuery } from '@tanstack/svelte-query';
	import { api } from '$lib/api';
	import { fmtMc, fmtPct, fmtPrice, fmtNum, fmtAge, fmtDateTime, shortCa } from '$lib/format';

	const ca = $derived(pageStore.params.ca ?? '');

	const tokenQuery = createQuery(() => ({
		queryKey: ['token', ca],
		queryFn: () => api.token(ca),
		refetchInterval: 60_000,
		enabled: ca.length > 0
	}));

	const t = $derived(tokenQuery.data?.token);
	const timeline = $derived(tokenQuery.data?.timeline ?? []);

	const flags = $derived.by(() => {
		const f: string[] = [];
		if (!t) return f;
		if (t.renounced) f.push('Renounced');
		if (t.renounced_mint) f.push('Mint');
		if (t.renounced_freeze) f.push('Freeze');
		if (t.burn_status === 'burn') f.push('LP Burn');
		return f;
	});
</script>

<section>
	<div class="mb-4">
		<a href="/day" class="text-sm text-zinc-400 hover:text-zinc-200">← back to Day</a>
	</div>

	{#if tokenQuery.isPending}
		<div class="py-12 text-center text-zinc-500">Loading…</div>
	{:else if tokenQuery.isError}
		<div class="py-12 text-center text-rose-400">Error: {tokenQuery.error.message}</div>
	{:else if !tokenQuery.data?.ready || !t}
		<div class="py-12 text-center text-zinc-500">Token not found.</div>
	{:else}
		<header class="flex items-start gap-4 mb-6 flex-wrap">
			{#if t.image_url}
				<img
					src={t.image_url}
					alt=""
					class="w-16 h-16 rounded-full object-cover bg-zinc-800 shrink-0"
					referrerpolicy="no-referrer"
				/>
			{:else}
				<div class="w-16 h-16 rounded-full bg-zinc-800 shrink-0"></div>
			{/if}
			<div class="min-w-0 flex-1">
				<div class="flex items-baseline gap-3 flex-wrap">
					<h1 class="text-3xl font-semibold tracking-tight">
						{t.ticker ?? 'unknown'}
					</h1>
					{#if t.name && t.name !== t.ticker}
						<span class="text-zinc-400">{t.name}</span>
					{/if}
					{#if t.launchpad}
						<span class="px-2 py-0.5 rounded text-xs bg-zinc-800 text-zinc-300">{t.launchpad}</span>
					{/if}
				</div>
				<div class="mt-1.5 flex items-center gap-2 text-xs text-zinc-500 flex-wrap">
					<span class="font-mono select-all" title={t.contract_address}>{shortCa(t.contract_address)}</span>
					<button
						type="button"
						class="text-zinc-500 hover:text-zinc-200 transition-colors"
						onclick={() => navigator.clipboard.writeText(t.contract_address)}
						title="Copy CA"
					>copy</button>
					{#if t.creation_timestamp}<span>· age {fmtAge(t.creation_timestamp)}</span>{/if}
					<span>· first {fmtDateTime(t.first_seen_at)}</span>
					<span>· last {fmtDateTime(t.last_seen_at)}</span>
				</div>
				<div class="mt-2 flex gap-2 text-xs flex-wrap">
					<a
						href="https://dexscreener.com/solana/{t.contract_address}"
						target="_blank"
						rel="noopener"
						class="px-2 py-1 rounded bg-zinc-900 border border-zinc-800 text-blue-400 hover:border-zinc-700"
					>DexScreener</a>
					<a
						href="https://gmgn.ai/sol/token/{t.contract_address}"
						target="_blank"
						rel="noopener"
						class="px-2 py-1 rounded bg-zinc-900 border border-zinc-800 text-emerald-400 hover:border-zinc-700"
					>GMGN</a>
					<a
						href="https://trade.padre.gg/trade/solana/{t.contract_address}"
						target="_blank"
						rel="noopener"
						class="px-2 py-1 rounded bg-zinc-900 border border-zinc-800 text-amber-400 hover:border-zinc-700"
					>Padre</a>
					<a
						href="https://solscan.io/token/{t.contract_address}"
						target="_blank"
						rel="noopener"
						class="px-2 py-1 rounded bg-zinc-900 border border-zinc-800 text-zinc-400 hover:border-zinc-700"
					>Solscan</a>
				</div>
			</div>
		</header>

		{#if t.description}
			<p class="text-sm text-zinc-400 mb-4 max-w-3xl">{t.description}</p>
		{/if}

		<div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
			<div class="rounded-lg border border-zinc-800 bg-zinc-900/40 px-3 py-2.5">
				<div class="text-[10px] uppercase tracking-wider text-zinc-500">Calls</div>
				<div class="text-lg font-medium tabular-nums mt-0.5">{fmtNum(t.call_count)}</div>
				<div class="text-[10px] text-zinc-500 mt-0.5">across {t.days_active}d</div>
			</div>
			<div class="rounded-lg border border-zinc-800 bg-zinc-900/40 px-3 py-2.5">
				<div class="text-[10px] uppercase tracking-wider text-zinc-500">Market Cap</div>
				<div class="text-lg font-medium tabular-nums mt-0.5">{fmtMc(t.market_cap)}</div>
				{#if t.market_cap_ath}
					<div class="text-[10px] text-zinc-500 mt-0.5">ATH {fmtMc(t.market_cap_ath)}</div>
				{/if}
			</div>
			<div class="rounded-lg border border-zinc-800 bg-zinc-900/40 px-3 py-2.5">
				<div class="text-[10px] uppercase tracking-wider text-zinc-500">24h</div>
				<div
					class="text-lg font-medium tabular-nums mt-0.5 {t.price_change_h24 == null
						? 'text-zinc-400'
						: t.price_change_h24 >= 0
							? 'text-emerald-400'
							: 'text-rose-400'}"
				>{fmtPct(t.price_change_h24)}</div>
			</div>
			<div class="rounded-lg border border-zinc-800 bg-zinc-900/40 px-3 py-2.5">
				<div class="text-[10px] uppercase tracking-wider text-zinc-500">Price</div>
				<div class="text-lg font-medium tabular-nums mt-0.5">{fmtPrice(t.price_usd)}</div>
			</div>
			<div class="rounded-lg border border-zinc-800 bg-zinc-900/40 px-3 py-2.5">
				<div class="text-[10px] uppercase tracking-wider text-zinc-500">Holders</div>
				<div class="text-lg font-medium tabular-nums mt-0.5">
					{t.holder_count ? fmtNum(t.holder_count) : '—'}
				</div>
				{#if t.top10_pct != null}
					<div class="text-[10px] text-zinc-500 mt-0.5">top10 {t.top10_pct.toFixed(1)}%</div>
				{/if}
			</div>
			<div class="rounded-lg border border-zinc-800 bg-zinc-900/40 px-3 py-2.5">
				<div class="text-[10px] uppercase tracking-wider text-zinc-500">Liquidity</div>
				<div class="text-lg font-medium tabular-nums mt-0.5">{fmtMc(t.liquidity_usd)}</div>
				{#if t.volume_h24 != null}
					<div class="text-[10px] text-zinc-500 mt-0.5">vol24h {fmtMc(t.volume_h24)}</div>
				{/if}
			</div>
		</div>

		{#if flags.length > 0 || t.groups_mentioned}
			<div class="flex items-center gap-3 mb-6 text-xs flex-wrap">
				{#if flags.length > 0}
					<div class="flex gap-1.5">
						{#each flags as f}
							<span class="px-2 py-0.5 rounded bg-emerald-900/40 text-emerald-300">{f}</span>
						{/each}
					</div>
				{/if}
				{#if t.groups_mentioned}
					<span class="text-zinc-500">Groups:</span>
					<span class="text-zinc-300">{t.groups_mentioned}</span>
				{/if}
			</div>
		{/if}

		<div class="rounded-lg border border-zinc-800 overflow-hidden mb-6 bg-zinc-950">
			<iframe
				src="https://dexscreener.com/solana/{t.contract_address}?embed=1&theme=dark&trades=0&info=0"
				title="DexScreener chart"
				class="w-full"
				style="height: 540px; border: 0;"
			></iframe>
		</div>

		{#if timeline.length > 0}
			<div class="rounded-lg border border-zinc-800 overflow-hidden">
				<div class="bg-zinc-900/60 px-3 py-2 text-xs uppercase tracking-wider text-zinc-400">
					Daily timeline
				</div>
				<table class="w-full text-sm">
					<thead class="bg-zinc-900/40 text-zinc-500 uppercase text-[10px] tracking-wider">
						<tr>
							<th class="text-left px-3 py-1.5 font-normal">Date</th>
							<th class="text-right px-3 py-1.5 font-normal">Calls</th>
							<th class="text-left px-3 py-1.5 font-normal">First</th>
							<th class="text-left px-3 py-1.5 font-normal">Last</th>
							<th class="text-left px-3 py-1.5 font-normal">Groups</th>
						</tr>
					</thead>
					<tbody>
						{#each timeline as e (e.call_date)}
							<tr class="border-t border-zinc-800/60">
								<td class="px-3 py-2 text-zinc-300 tabular-nums">{e.call_date}</td>
								<td class="px-3 py-2 text-right tabular-nums">{fmtNum(e.call_count)}</td>
								<td class="px-3 py-2 text-zinc-400 tabular-nums text-xs">{fmtDateTime(e.first_seen_at)}</td>
								<td class="px-3 py-2 text-zinc-400 tabular-nums text-xs">{fmtDateTime(e.last_seen_at)}</td>
								<td class="px-3 py-2 text-zinc-400 text-xs">{e.groups_mentioned ?? '—'}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}
	{/if}
</section>
