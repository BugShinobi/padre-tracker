<script lang="ts">
	import Surface from './Surface.svelte';
	import { fmtMc, fmtPct, fmtAge, shortCa } from '$lib/format';
	import type { EnrichedRow } from '$lib/types';

	type Props = {
		row: EnrichedRow;
		variant?: 'compact' | 'expanded';
	};

	let { row, variant = 'compact' }: Props = $props();

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
</script>

<a href="/t/{row.contract_address}" class="block">
	<Surface variant="card" hover padding="md">
		<div class="flex items-center gap-3">
			{#if row.image_url}
				<img
					src={row.image_url}
					alt=""
					class="w-10 h-10 rounded-full object-cover bg-zinc-800 shrink-0"
					loading="lazy"
					referrerpolicy="no-referrer"
				/>
			{:else}
				<div class="w-10 h-10 rounded-full bg-zinc-800 shrink-0"></div>
			{/if}
			<div class="min-w-0 flex-1">
				<div class="flex items-center gap-2">
					<span class="font-semibold text-zinc-100 truncate">
						{row.ticker ?? shortCa(row.contract_address)}
					</span>
					{#if row.launchpad}
						<span class="px-1.5 py-0.5 rounded text-[10px] uppercase {launchpadBadge(row.launchpad)}">
							{row.launchpad.split('.')[0]}
						</span>
					{/if}
				</div>
				{#if row.name && row.name !== row.ticker}
					<div class="text-xs text-zinc-500 truncate">{row.name}</div>
				{/if}
			</div>
			<div class="text-right shrink-0">
				<div class="text-sm font-medium tabular-nums">{fmtMc(row.market_cap)}</div>
				<div class="text-xs tabular-nums {changeCls}">{fmtPct(row.price_change_h24)}</div>
			</div>
		</div>

		{#if variant === 'expanded'}
			<div class="mt-3 flex items-center gap-3 text-xs text-zinc-500">
				<span>{row.call_count} calls</span>
				<span>·</span>
				<span>{fmtAge(row.creation_timestamp)}</span>
				{#if row.holder_count}
					<span>·</span>
					<span>{row.holder_count.toLocaleString('en-US')} holders</span>
				{/if}
			</div>
			{#if row.description}
				<p class="mt-2 text-xs text-zinc-400 line-clamp-2">{row.description}</p>
			{/if}
		{/if}
	</Surface>
</a>
