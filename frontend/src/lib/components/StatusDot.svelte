<script lang="ts">
	type Props = {
		connected: boolean;
		size?: 'sm' | 'md' | 'lg';
	};

	let { connected, size = 'sm' }: Props = $props();

	const sizes = {
		sm: 'h-2 w-2',
		md: 'h-2.5 w-2.5',
		lg: 'h-3 w-3'
	};
</script>

<span class="relative flex {sizes[size]}">
	{#if connected}
		<span
			class="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75 animate-ping"
		></span>
		<span class="relative inline-flex rounded-full {sizes[size]} bg-emerald-500"></span>
	{:else}
		<span class="relative inline-flex rounded-full {sizes[size]} bg-zinc-600"></span>
	{/if}
</span>
