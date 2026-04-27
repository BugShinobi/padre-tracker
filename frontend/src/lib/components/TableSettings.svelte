<script lang="ts">
	import { tablePrefs, saveTablePrefs } from '$lib/tablePrefs.svelte';

	function setDensity(d: 'compact' | 'comfortable') {
		tablePrefs.density = d;
		saveTablePrefs();
	}

	function toggleCol(key: keyof typeof tablePrefs.cols) {
		tablePrefs.cols[key] = !tablePrefs.cols[key];
		saveTablePrefs();
	}

	const COLS: { key: keyof typeof tablePrefs.cols; label: string }[] = [
		{ key: 'description', label: 'Description' },
		{ key: 'groups', label: 'Groups' },
		{ key: 'holders', label: 'Holders' },
		{ key: 'flags', label: 'Flags' }
	];
</script>

<details class="text-xs text-zinc-400 group">
	<summary class="cursor-pointer list-none px-2 py-1 rounded border border-zinc-700 hover:bg-zinc-800 hover:text-zinc-200 transition-colors inline-flex items-center gap-1.5">
		<span>View</span>
		<span class="text-[10px] opacity-60 group-open:rotate-180 transition-transform">▾</span>
	</summary>
	<div class="mt-2 p-2.5 rounded border border-zinc-700 bg-zinc-900/80 flex flex-wrap items-center gap-3">
		<div class="flex items-center gap-1">
			<span class="text-[10px] uppercase tracking-wider text-zinc-500 mr-1">Density</span>
			{#each ['compact', 'comfortable'] as d (d)}
				<button
					type="button"
					onclick={() => setDensity(d as 'compact' | 'comfortable')}
					class="px-2 py-0.5 rounded text-[11px] border transition-colors {tablePrefs.density === d
						? 'border-emerald-500/50 bg-emerald-500/15 text-emerald-200'
						: 'border-zinc-700 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200'}"
				>{d}</button>
			{/each}
		</div>
		<div class="flex items-center gap-1.5 flex-wrap">
			<span class="text-[10px] uppercase tracking-wider text-zinc-500 mr-1">Columns</span>
			{#each COLS as c (c.key)}
				<button
					type="button"
					onclick={() => toggleCol(c.key)}
					class="px-2 py-0.5 rounded text-[11px] border transition-colors {tablePrefs.cols[c.key]
						? 'border-emerald-500/50 bg-emerald-500/15 text-emerald-200'
						: 'border-zinc-700 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300'}"
				>{c.label}</button>
			{/each}
		</div>
	</div>
</details>
