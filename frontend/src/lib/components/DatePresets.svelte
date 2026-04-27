<script lang="ts">
	import { todayIso, daysAgoIso } from '$lib/format';

	type Mode = 'day' | 'range';

	type Props = {
		mode: Mode;
		date?: string;
		from?: string;
		to?: string;
		onchange: (next: { date?: string; from?: string; to?: string }) => void;
	};

	let { mode, date, from, to, onchange }: Props = $props();

	const PRESETS: { id: string; label: string; days: number | 'today' | 'yesterday' }[] = [
		{ id: 'today', label: 'Today', days: 'today' },
		{ id: 'yesterday', label: 'Yesterday', days: 'yesterday' },
		{ id: '3d', label: '3d', days: 3 },
		{ id: '7d', label: '7d', days: 7 },
		{ id: '30d', label: '30d', days: 30 }
	];

	const today = $derived(todayIso());
	const yesterday = $derived(daysAgoIso(1));

	function presetMatches(p: (typeof PRESETS)[number]): boolean {
		if (mode === 'day') {
			if (p.days === 'today') return date === today;
			if (p.days === 'yesterday') return date === yesterday;
			return false;
		}
		if (p.days === 'today') return from === today && to === today;
		if (p.days === 'yesterday') return from === yesterday && to === yesterday;
		return from === daysAgoIso((p.days as number) - 1) && to === today;
	}

	const activeId = $derived(PRESETS.find(presetMatches)?.id ?? 'custom');
	const showCustom = $derived(activeId === 'custom');

	function applyPreset(p: (typeof PRESETS)[number]) {
		if (mode === 'day') {
			if (p.days === 'today') onchange({ date: today });
			else if (p.days === 'yesterday') onchange({ date: yesterday });
			else onchange({ date: today });
			return;
		}
		if (p.days === 'today') onchange({ from: today, to: today });
		else if (p.days === 'yesterday') onchange({ from: yesterday, to: yesterday });
		else onchange({ from: daysAgoIso((p.days as number) - 1), to: today });
	}
</script>

<div class="flex items-center gap-1 flex-wrap">
	{#each PRESETS as p (p.id)}
		{#if mode === 'range' || p.days === 'today' || p.days === 'yesterday'}
			<button
				type="button"
				onclick={() => applyPreset(p)}
				class="px-2 py-1 rounded text-xs border transition-colors {activeId === p.id
					? 'border-emerald-500/50 bg-emerald-500/15 text-emerald-200'
					: 'border-zinc-700 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200'}"
			>{p.label}</button>
		{/if}
	{/each}
	{#if mode === 'day'}
		<input
			type="date"
			value={date ?? ''}
			onchange={(e) => onchange({ date: (e.target as HTMLInputElement).value })}
			class="bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs focus:outline-none focus:border-zinc-500"
		/>
	{:else}
		<button
			type="button"
			onclick={() => onchange({ from: from ?? today, to: to ?? today })}
			class="px-2 py-1 rounded text-xs border transition-colors {showCustom
				? 'border-emerald-500/50 bg-emerald-500/15 text-emerald-200'
				: 'border-zinc-700 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200'}"
		>Custom</button>
		{#if showCustom}
			<input
				type="date"
				value={from ?? ''}
				max={to ?? today}
				onchange={(e) => onchange({ from: (e.target as HTMLInputElement).value, to })}
				class="bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs focus:outline-none focus:border-zinc-500"
			/>
			<span class="text-zinc-600 text-xs">→</span>
			<input
				type="date"
				value={to ?? ''}
				min={from ?? ''}
				max={today}
				onchange={(e) => onchange({ from, to: (e.target as HTMLInputElement).value })}
				class="bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs focus:outline-none focus:border-zinc-500"
			/>
		{/if}
	{/if}
</div>
