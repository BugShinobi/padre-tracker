<script lang="ts">
	import { fmtMc, fmtPct, fmtNum, fmtAge, fmtDateTime, shortCa } from '$lib/format';
	import type { EnrichedRow } from '$lib/types';

	type Props = {
		row: EnrichedRow;
		index: number;
		showDaysActive?: boolean;
		daysActive?: number;
		showLast?: boolean;
	};

	let { row, index, showDaysActive = false, daysActive, showLast = false }: Props = $props();

	const changeCls = $derived(
		row.price_change_h24 == null
			? 'text-zinc-500'
			: row.price_change_h24 >= 0
				? 'text-emerald-400'
				: 'text-rose-400'
	);

	const launchpadBadge = (lp: string | null) => {
		if (!lp) return 'bg-zinc-800 text-zinc-400';
		const k = lp.split('.')[0];
		switch (k) {
			case 'pump':
				return 'bg-amber-900/40 text-amber-300';
			case 'BAGS':
				return 'bg-purple-900/40 text-purple-300';
			case 'bonk':
				return 'bg-orange-900/40 text-orange-300';
			case 'moon':
				return 'bg-blue-900/40 text-blue-300';
			case 'printr':
				return 'bg-emerald-900/40 text-emerald-300';
			default:
				return 'bg-zinc-800 text-zinc-300';
		}
	};

	const flags = $derived.by(() => {
		const f: string[] = [];
		if (row.renounced) f.push('RNK');
		if (row.renounced_mint) f.push('MNT');
		if (row.renounced_freeze) f.push('FRZ');
		if (row.burn_status === 'burn') f.push('LP');
		return f;
	});

	function go(e: MouseEvent | KeyboardEvent) {
		if (e instanceof KeyboardEvent && e.key !== 'Enter') return;
		const target = e.target as HTMLElement;
		if (target.closest('a')) return;
		window.location.href = `/t/${row.contract_address}`;
	}
</script>

<tr
	class="border-t border-zinc-800/60 hover:bg-zinc-900/40 cursor-pointer transition-colors"
	onclick={go}
	onkeydown={go}
	tabindex="0"
	role="link"
>
	<td class="px-3 py-3 text-zinc-600 tabular-nums text-xs">{index}</td>

	<td class="px-3 py-3">
		<div class="flex items-center gap-2.5">
			{#if row.image_url}
				<img
					src={row.image_url}
					alt=""
					class="w-8 h-8 rounded-full object-cover bg-zinc-800 shrink-0"
					loading="lazy"
					referrerpolicy="no-referrer"
				/>
			{:else}
				<div class="w-8 h-8 rounded-full bg-zinc-800 shrink-0"></div>
			{/if}
			<div class="min-w-0">
				<div class="font-medium text-zinc-100 {row.ticker ? '' : 'italic text-zinc-500'}">
					{row.ticker ?? 'unknown'}
				</div>
				{#if row.name && row.name !== row.ticker}
					<div class="text-xs text-zinc-500 truncate max-w-[140px]">{row.name}</div>
				{/if}
			</div>
		</div>
	</td>

	<td class="px-3 py-3">
		<div class="flex items-center gap-2 text-xs">
			<span class="font-mono text-zinc-400">{shortCa(row.contract_address)}</span>
			<span class="text-zinc-500">{fmtAge(row.creation_timestamp)}</span>
			<span class="flex gap-1">
				<a
					href="https://dexscreener.com/solana/{row.contract_address}"
					target="_blank"
					rel="noopener"
					class="text-blue-400 hover:underline"
					title="DexScreener"
					onclick={(e) => e.stopPropagation()}>D</a
				>
				<a
					href="https://gmgn.ai/sol/token/{row.contract_address}"
					target="_blank"
					rel="noopener"
					class="text-emerald-400 hover:underline"
					title="GMGN"
					onclick={(e) => e.stopPropagation()}>G</a
				>
				<a
					href="https://trade.padre.gg/trade/solana/{row.contract_address}"
					target="_blank"
					rel="noopener"
					class="text-amber-400 hover:underline"
					title="Padre"
					onclick={(e) => e.stopPropagation()}>P</a
				>
			</span>
		</div>
	</td>

	<td class="px-3 py-3">
		<span class="px-2 py-0.5 rounded text-xs {launchpadBadge(row.launchpad)}">
			{row.launchpad ?? '—'}
		</span>
	</td>

	<td class="px-3 py-3 text-right tabular-nums font-medium">{row.call_count}</td>

	{#if showDaysActive && daysActive != null}
		<td class="px-3 py-3 text-right tabular-nums text-zinc-300">{daysActive}</td>
	{/if}

	<td class="px-3 py-3 text-right tabular-nums">
		<div>{fmtMc(row.market_cap)}</div>
		{#if row.market_cap_ath && (!row.market_cap || row.market_cap_ath > row.market_cap)}
			<div class="text-[10px] text-zinc-500" title="ATH since tracking">
				ATH {fmtMc(row.market_cap_ath)}
			</div>
		{/if}
	</td>

	<td class="px-3 py-3 text-right tabular-nums {changeCls}">{fmtPct(row.price_change_h24)}</td>

	<td class="px-3 py-3 max-w-[260px]">
		{#if row.description}
			<p class="text-xs text-zinc-400 line-clamp-2" title={row.description}>{row.description}</p>
		{:else}
			<span class="text-xs text-zinc-700">—</span>
		{/if}
	</td>

	<td class="px-3 py-3 text-zinc-300 text-xs max-w-[180px] truncate" title={row.groups_mentioned ?? ''}>
		{row.groups_mentioned ?? '—'}
	</td>

	<td class="px-3 py-3 text-zinc-400 tabular-nums text-xs whitespace-nowrap" title={row.first_seen_at}>
		{fmtDateTime(row.first_seen_at)}
	</td>

	{#if showLast}
		<td class="px-3 py-3 text-zinc-400 tabular-nums text-xs whitespace-nowrap" title={row.last_seen_at}>
			{fmtDateTime(row.last_seen_at)}
		</td>
	{/if}

	<td class="px-3 py-3 text-right tabular-nums text-xs text-zinc-400">
		{row.holder_count ? fmtNum(row.holder_count) : '—'}
	</td>

	<td class="px-3 py-3">
		<div class="flex gap-1 flex-wrap">
			{#each flags as f}
				<span class="px-1.5 py-0.5 rounded text-[10px] bg-emerald-900/40 text-emerald-300">{f}</span>
			{/each}
		</div>
	</td>
</tr>
