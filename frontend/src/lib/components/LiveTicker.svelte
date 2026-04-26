<script lang="ts">
	import { fly, fade } from 'svelte/transition';
	import { flip } from 'svelte/animate';
	import { live } from '$lib/sse.svelte';
	import { fmtTime, shortCa } from '$lib/format';
	import StatusDot from './StatusDot.svelte';
</script>

<div class="border-b border-zinc-800/60 bg-zinc-950/40 backdrop-blur-sm">
	<div class="mx-auto max-w-screen-2xl px-4 py-2 flex items-center gap-2 overflow-x-auto">
		<a
			href="/live"
			class="flex items-center gap-1.5 text-xs uppercase tracking-wide text-zinc-400 hover:text-zinc-200 shrink-0 transition-colors"
		>
			<StatusDot connected={live.connected} />
			<span class="font-medium">Live</span>
			{#if live.items.length > 0}
				<span class="px-1.5 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 text-[10px]">
					{live.items.length}
				</span>
			{/if}
		</a>
		{#if live.items.length === 0}
			<span class="text-xs text-zinc-600">Watching for new tokens…</span>
		{:else}
			{#each live.items.slice(0, 12) as row (row.contract_address)}
				<a
					href="/t/{row.contract_address}"
					class="flex items-center gap-1.5 rounded-full bg-zinc-900/80 border border-zinc-800 hover:border-zinc-600 px-2.5 py-1 text-xs whitespace-nowrap transition-colors"
					in:fly={{ x: -20, duration: 250 }}
					out:fade={{ duration: 150 }}
					animate:flip={{ duration: 200 }}
				>
					{#if row.image_url}
						<img src={row.image_url} alt="" class="w-4 h-4 rounded-full" loading="lazy" />
					{/if}
					<span class="font-medium text-zinc-100">
						{row.ticker ?? shortCa(row.contract_address)}
					</span>
					{#if row.launchpad}
						<span class="text-zinc-500">{row.launchpad.split('.')[0]}</span>
					{/if}
					<span class="text-zinc-600">{fmtTime(row.first_seen_at)}</span>
				</a>
			{/each}
			{#if live.items.length > 12}
				<a href="/live" class="text-xs text-zinc-500 hover:text-zinc-300 shrink-0">
					+{live.items.length - 12} more →
				</a>
			{/if}
		{/if}
	</div>
</div>
