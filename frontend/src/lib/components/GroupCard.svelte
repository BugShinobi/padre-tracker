<script lang="ts">
	import Surface from './Surface.svelte';
	import type { GroupRow } from '$lib/types';

	type Props = {
		group: GroupRow;
		rank?: number;
		maxTokens?: number;
	};

	let { group, rank, maxTokens }: Props = $props();

	const name = $derived(group.name ?? group.group ?? 'unknown');
	const pct = $derived(maxTokens && maxTokens > 0 ? (group.tokens / maxTokens) * 100 : 0);
</script>

<Surface variant="card" padding="md">
	<div class="flex items-center gap-3">
		{#if rank}
			<div class="text-zinc-600 text-sm tabular-nums w-6 shrink-0">#{rank}</div>
		{/if}
		<div class="min-w-0 flex-1">
			<div class="font-medium text-zinc-100 truncate">{name}</div>
			<div class="mt-1.5 h-1 rounded-full bg-zinc-800 overflow-hidden">
				<div
					class="h-full bg-gradient-to-r from-emerald-500 to-cyan-500 transition-all duration-500"
					style="width: {pct}%"
				></div>
			</div>
		</div>
		<div class="text-right shrink-0">
			<div class="text-sm font-medium tabular-nums">{group.tokens}</div>
			<div class="text-xs text-zinc-500 tabular-nums">{group.calls} calls</div>
		</div>
	</div>
</Surface>
