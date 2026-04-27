<script lang="ts">
	import { fmtMc, parseMc } from '$lib/format';

	type Props = {
		min: number;
		max: number;
		onchange: (next: { min: number; max: number }) => void;
	};

	let { min, max, onchange }: Props = $props();

	function formatRaw(n: number): string {
		if (n >= 1e9) return `${(n / 1e9).toFixed(n % 1e9 === 0 ? 0 : 1)}B`;
		if (n >= 1e6) return `${(n / 1e6).toFixed(n % 1e6 === 0 ? 0 : 1)}M`;
		if (n >= 1e3) return `${(n / 1e3).toFixed(n % 1e3 === 0 ? 0 : 1)}K`;
		return String(n);
	}

	let minInput = $state('');
	let maxInput = $state('');

	$effect(() => {
		minInput = min > 0 ? formatRaw(min) : '';
	});
	$effect(() => {
		maxInput = max > 0 ? formatRaw(max) : '';
	});

	function commit() {
		onchange({ min: parseMc(minInput), max: parseMc(maxInput) });
	}

	const minNum = $derived(parseMc(minInput));
	const maxNum = $derived(parseMc(maxInput));
	const summary = $derived.by(() => {
		if (!minNum && !maxNum) return null;
		if (minNum && !maxNum) return `≥ ${fmtMc(minNum)}`;
		if (!minNum && maxNum) return `≤ ${fmtMc(maxNum)}`;
		return `${fmtMc(minNum)} – ${fmtMc(maxNum)}`;
	});
</script>

<label class="flex items-center gap-1.5 text-xs text-zinc-400">
	<span class="uppercase tracking-wider text-[10px] text-zinc-500">MC</span>
	<input
		type="text"
		bind:value={minInput}
		onblur={commit}
		onkeydown={(e) => e.key === 'Enter' && commit()}
		placeholder="min"
		class="bg-zinc-900/60 border border-zinc-700 rounded px-2 py-1 w-16 tabular-nums focus:outline-none focus:border-zinc-500"
	/>
	<span class="text-zinc-600">–</span>
	<input
		type="text"
		bind:value={maxInput}
		onblur={commit}
		onkeydown={(e) => e.key === 'Enter' && commit()}
		placeholder="max"
		class="bg-zinc-900/60 border border-zinc-700 rounded px-2 py-1 w-16 tabular-nums focus:outline-none focus:border-zinc-500"
	/>
	{#if summary}
		<span class="text-[10px] text-emerald-400 tabular-nums">{summary}</span>
	{/if}
</label>
