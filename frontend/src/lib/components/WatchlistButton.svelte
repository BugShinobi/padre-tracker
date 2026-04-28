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

	const cls = $derived(size === 'md' ? 'text-base' : 'text-sm');
</script>

<button
	type="button"
	onclick={toggle}
	onkeydown={toggle}
	disabled={busy}
	class="{cls} transition-colors {isOn
		? 'text-amber-400 hover:text-amber-300'
		: 'text-zinc-600 hover:text-zinc-400'}"
	title={isOn ? 'Remove from watchlist' : 'Add to watchlist'}
	aria-label={isOn ? 'Remove from watchlist' : 'Add to watchlist'}
>{isOn ? '★' : '☆'}</button>
