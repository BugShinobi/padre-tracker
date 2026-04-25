<script lang="ts">
	import './layout.css';
	import favicon from '$lib/assets/favicon.svg';
	import { QueryClient, QueryClientProvider } from '@tanstack/svelte-query';
	import { onMount } from 'svelte';
	import { connectSse, disconnectSse } from '$lib/sse.svelte';
	import LiveTicker from '$lib/components/LiveTicker.svelte';

	const queryClient = new QueryClient({
		defaultOptions: {
			queries: {
				staleTime: 60_000,
				refetchOnWindowFocus: false
			}
		}
	});

	onMount(() => {
		connectSse(queryClient);
		return () => disconnectSse();
	});

	let { children } = $props();
</script>

<svelte:head><link rel="icon" href={favicon} /></svelte:head>

<QueryClientProvider client={queryClient}>
	<div class="min-h-screen">
		<header class="border-b border-zinc-800 bg-zinc-950/80 backdrop-blur sticky top-0 z-10">
			<div class="mx-auto max-w-6xl px-4 py-3 flex items-center justify-between">
				<a href="/" class="font-semibold tracking-tight">padre-tracker</a>
				<nav class="text-sm text-zinc-400 flex gap-4">
					<a href="/" class="hover:text-zinc-100">Home</a>
					<a href="/day" class="hover:text-zinc-100">Day</a>
					<a href="/range" class="hover:text-zinc-100">Range</a>
				</nav>
			</div>
		</header>
		<LiveTicker />
		<main class="mx-auto max-w-6xl px-4 py-6">
			{@render children()}
		</main>
	</div>
</QueryClientProvider>
