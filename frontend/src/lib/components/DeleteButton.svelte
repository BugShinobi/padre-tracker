<script lang="ts">
	import { useQueryClient } from '@tanstack/svelte-query';
	import { goto } from '$app/navigation';
	import { api } from '$lib/api';

	type Props = {
		ca: string;
		ticker?: string | null;
		size?: 'sm' | 'md';
		redirectTo?: string;
	};

	let { ca, ticker = null, size = 'sm', redirectTo }: Props = $props();

	const qc = useQueryClient();
	let busy = $state(false);

	const cls = $derived(
		size === 'sm' ? 'px-1.5 py-0.5 text-[11px]' : 'px-2.5 py-1 text-xs'
	);

	async function onClick(e: MouseEvent) {
		e.stopPropagation();
		if (busy) return;
		const label = ticker ? `${ticker} (${ca.slice(0, 6)}…)` : `${ca.slice(0, 8)}…`;
		const ok = window.confirm(
			`Delete ${label}? This wipes every row for the token from the DB. Irreversible.`
		);
		if (!ok) return;
		busy = true;
		try {
			await api.deleteToken(ca);
			qc.invalidateQueries({ queryKey: ['day'] });
			qc.invalidateQueries({ queryKey: ['range'] });
			qc.invalidateQueries({ queryKey: ['overview'] });
			qc.removeQueries({ queryKey: ['token', ca] });
			if (redirectTo) await goto(redirectTo);
		} catch (err) {
			console.error('delete failed', err);
			alert(`Failed to delete: ${(err as Error).message}`);
		} finally {
			busy = false;
		}
	}
</script>

<button
	type="button"
	onclick={onClick}
	disabled={busy}
	class="rounded border border-rose-800/50 bg-rose-900/30 text-rose-300 hover:bg-rose-900/50 hover:text-rose-200 disabled:opacity-40 transition {cls}"
	title="Delete token (irreversible)"
>
	{busy ? '…' : 'Delete'}
</button>
