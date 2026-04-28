<script lang="ts">
	import { watchlist } from '$lib/watchlist.svelte';

	type Props = { ca: string; size?: 'sm' | 'md' };
	let { ca, size = 'sm' }: Props = $props();

	const isOn = $derived(watchlist.has(ca));
	let busy = $state(false);

	async function toggle(e: MouseEvent | KeyboardEvent) {
		e.stopPropagation();
		if (e instanceof KeyboardEvent && e.key !== 'Enter' && e.key !== ' ') return;
		if (busy) return;
		busy = true;
		try {
			await watchlist.toggle(ca);
		} catch (err) {
			console.error('watchlist toggle failed', err);
		} finally {
			busy = false;
		}
	}

	const cls = $derived(
		size === 'md'
			? `inline-flex items-center justify-center w-9 h-9 rounded border text-lg leading-none transition-colors ${
					isOn
						? 'border-amber-500/70 bg-amber-500/20 text-amber-300 shadow-[0_0_18px_rgba(245,158,11,0.18)]'
						: 'border-zinc-800 bg-zinc-900 text-zinc-400 hover:text-zinc-200 hover:border-zinc-700'
				}`
			: `inline-flex items-center justify-center w-7 h-7 rounded border text-base leading-none transition-colors ${
					isOn
						? 'border-amber-500/70 bg-amber-500/20 text-amber-300 shadow-[0_0_14px_rgba(245,158,11,0.16)]'
						: 'border-zinc-800 bg-zinc-950 text-zinc-600 hover:text-zinc-300 hover:border-zinc-700'
				}`
	);
</script>

<button
	type="button"
	onclick={toggle}
	onkeydown={toggle}
	disabled={busy}
	class={cls}
	title={isOn ? 'Remove from watchlist' : 'Add to watchlist'}
	aria-label={isOn ? 'Remove from watchlist' : 'Add to watchlist'}
	aria-pressed={isOn}
>{isOn ? '★' : '☆'}</button>
