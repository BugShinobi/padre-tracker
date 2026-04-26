<script lang="ts">
	type Props = {
		hasActiveFilters: boolean;
		onreset: () => void;
		children: import('svelte').Snippet;
	};

	let { hasActiveFilters, onreset, children }: Props = $props();
</script>

<div class="sticky top-[57px] z-[5] -mx-4 px-4 py-3 bg-zinc-950/85 backdrop-blur-md border-b border-zinc-800/60">
	<div class="flex items-center gap-2 flex-wrap">
		{@render children()}
		{#if hasActiveFilters}
			<button
				type="button"
				onclick={onreset}
				class="ml-auto text-xs text-zinc-500 hover:text-rose-300 px-2 py-1 transition-colors"
			>
				Reset all ✕
			</button>
		{/if}
	</div>
</div>
