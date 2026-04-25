<script lang="ts">
	import { fly, fade } from 'svelte/transition';
	import { flip } from 'svelte/animate';
	import { live } from '$lib/sse.svelte';
	import { fmtTime, shortCa } from '$lib/format';
</script>

<div class="border-b border-zinc-800 bg-zinc-950/60">
	<div class="mx-auto max-w-6xl px-4 py-2 flex items-center gap-2 overflow-x-auto">
		<span class="flex items-center gap-1.5 text-xs uppercase tracking-wide text-zinc-500 shrink-0">
			<span class="relative flex h-2 w-2">
				{#if live.connected}
					<span class="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75 animate-ping"></span>
					<span class="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
				{:else}
					<span class="relative inline-flex rounded-full h-2 w-2 bg-zinc-600"></span>
				{/if}
			</span>
			Live
		</span>
		{#if live.items.length === 0}
			<span class="text-xs text-zinc-600">Watching for new tokens…</span>
		{:else}
			{#each live.items as row (row.contract_address)}
				<div
					class="flex items-center gap-1.5 rounded-full bg-zinc-900 border border-zinc-800 px-2.5 py-1 text-xs whitespace-nowrap"
					in:fly={{ x: -20, duration: 250 }}
					out:fade={{ duration: 150 }}
					animate:flip={{ duration: 200 }}
				>
					{#if row.image_url}
						<img src={row.image_url} alt="" class="w-4 h-4 rounded-full" />
					{/if}
					<span class="font-medium text-zinc-100">
						{row.ticker ?? shortCa(row.contract_address)}
					</span>
					{#if row.launchpad}
						<span class="text-zinc-500">{row.launchpad}</span>
					{/if}
					<span class="text-zinc-600">{fmtTime(row.first_seen_at)}</span>
				</div>
			{/each}
		{/if}
	</div>
</div>
