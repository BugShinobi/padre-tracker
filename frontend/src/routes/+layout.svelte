<script lang="ts">
	import './layout.css';
	import favicon from '$lib/assets/favicon.svg';
	import { QueryClient, QueryClientProvider } from '@tanstack/svelte-query';
	import { onMount } from 'svelte';
	import { connectSse, disconnectSse, live } from '$lib/sse.svelte';
	import { watchlist } from '$lib/watchlist.svelte';
	import LiveTicker from '$lib/components/LiveTicker.svelte';
	import StatusDot from '$lib/components/StatusDot.svelte';

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
		watchlist.load().catch((e) => console.error('watchlist load failed', e));
		return () => disconnectSse();
	});

	let { children } = $props();
</script>

<svelte:head><link rel="icon" href={favicon} /></svelte:head>

<QueryClientProvider client={queryClient}>
	<div class="min-h-screen">
		<header class="border-b border-zinc-800 bg-zinc-950/80 backdrop-blur sticky top-0 z-10">
			<div class="mx-auto max-w-screen-2xl px-4 py-3 flex items-center justify-between gap-4">
				<a href="/" class="font-semibold tracking-tight flex items-center gap-2">
					<span class="text-emerald-400">◉</span>
					<span>padre-tracker</span>
				</a>
				<nav class="text-sm flex items-center gap-2 overflow-x-auto">
					<a href="/" class="px-3 py-1.5 rounded-md border border-zinc-800 bg-zinc-900/70 text-zinc-200 hover:bg-zinc-800 transition-colors">Home</a>
					<a href="/day" class="px-3 py-1.5 rounded-md border border-emerald-500/30 bg-emerald-500/10 text-emerald-100 hover:bg-emerald-500/16 transition-colors">Day</a>
					<a href="/range" class="px-3 py-1.5 rounded-md border border-zinc-800 bg-zinc-900/70 text-zinc-200 hover:bg-zinc-800 transition-colors">Range</a>
					<a href="/watchlist" class="px-3 py-1.5 rounded-md border border-amber-500/30 bg-amber-500/10 text-amber-100 hover:bg-amber-500/16 transition-colors flex items-center gap-1">
						<span>★</span><span>Watch</span>
					</a>
					<a href="/alerts" class="px-3 py-1.5 rounded-md border border-sky-500/30 bg-sky-500/10 text-sky-100 hover:bg-sky-500/16 transition-colors">Alerts</a>
					<a href="/live" class="px-3 py-1.5 rounded-md border border-zinc-800 bg-zinc-900/70 text-zinc-200 hover:bg-zinc-800 transition-colors flex items-center gap-1.5">
						<StatusDot connected={live.connected} />
						<span>Live</span>
					</a>
				</nav>
			</div>
		</header>
		<LiveTicker />
		<main class="mx-auto max-w-screen-2xl px-4 py-6">
			{@render children()}
		</main>
	</div>
</QueryClientProvider>
