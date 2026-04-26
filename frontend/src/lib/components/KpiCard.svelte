<script lang="ts">
	import AnimatedNumber from './AnimatedNumber.svelte';
	import Sparkline from './Sparkline.svelte';
	import Surface from './Surface.svelte';
	import type { Delta } from '$lib/types';

	type Props = {
		label: string;
		value: number;
		delta?: Delta;
		spark?: number[];
		variant?: 'gradient-pos' | 'gradient-neg' | 'gradient-cool' | 'card';
		sparkStroke?: string;
		sparkFill?: string;
	};

	let {
		label,
		value,
		delta,
		spark,
		variant = 'card',
		sparkStroke = 'rgb(16 185 129)',
		sparkFill = 'rgb(16 185 129 / 0.15)'
	}: Props = $props();

	const deltaCls = $derived(
		delta?.class === 'pos'
			? 'text-emerald-400'
			: delta?.class === 'neg'
				? 'text-rose-400'
				: 'text-zinc-500'
	);
</script>

<Surface {variant} padding="lg">
	<div class="flex items-start justify-between gap-2">
		<div class="text-xs uppercase tracking-wider text-zinc-400 font-medium">{label}</div>
		{#if delta}
			<div class="text-xs tabular-nums {deltaCls}">{delta.str}</div>
		{/if}
	</div>
	<div class="mt-2 text-3xl font-semibold tracking-tight">
		<AnimatedNumber {value} />
	</div>
	{#if spark && spark.length > 1}
		<div class="mt-3 -mx-1">
			<Sparkline data={spark} stroke={sparkStroke} fill={sparkFill} height={40} strokeWidth={1.5} />
		</div>
	{/if}
</Surface>
