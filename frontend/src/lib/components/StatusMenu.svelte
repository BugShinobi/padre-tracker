<script lang="ts">
	import { useQueryClient } from '@tanstack/svelte-query';
	import { api } from '$lib/api';
	import type { TokenStatus } from '$lib/types';

	type Props = {
		ca: string;
		current?: TokenStatus;
		size?: 'sm' | 'md';
	};

	let { ca, current = 'active', size = 'sm' }: Props = $props();

	const qc = useQueryClient();
	let open = $state(false);
	let busy = $state(false);

	const OPTIONS: { value: TokenStatus; label: string; cls: string }[] = [
		{ value: 'active', label: 'Active', cls: 'text-emerald-300 hover:bg-emerald-900/30' },
		{ value: 'delisted', label: 'Delisted', cls: 'text-rose-300 hover:bg-rose-900/30' },
		{ value: 'ignored', label: 'Ignored', cls: 'text-zinc-400 hover:bg-zinc-800' }
	];

	async function setStatus(status: TokenStatus) {
		if (busy || status === current) {
			open = false;
			return;
		}
		busy = true;
		try {
			await api.setTokenStatus(ca, status);
			qc.invalidateQueries({ queryKey: ['day'] });
			qc.invalidateQueries({ queryKey: ['range'] });
			qc.invalidateQueries({ queryKey: ['token', ca] });
			qc.invalidateQueries({ queryKey: ['overview'] });
		} catch (e) {
			console.error('setStatus failed', e);
			alert(`Failed to update status: ${(e as Error).message}`);
		} finally {
			busy = false;
			open = false;
		}
	}

	function toggle(e: MouseEvent) {
		e.stopPropagation();
		open = !open;
	}

	function close() {
		open = false;
	}

	const triggerCls = $derived(
		size === 'sm'
			? 'px-1.5 py-0.5 text-[11px]'
			: 'px-2.5 py-1 text-xs'
	);

	const badgeCls = $derived(
		current === 'delisted'
			? 'bg-rose-900/40 text-rose-300 border-rose-800/50'
			: current === 'ignored'
				? 'bg-zinc-800 text-zinc-400 border-zinc-700'
				: 'bg-emerald-900/30 text-emerald-300 border-emerald-800/40'
	);
</script>

<svelte:window onclick={close} />

<div class="relative inline-block">
	<button
		type="button"
		onclick={toggle}
		disabled={busy}
		class="rounded border tabular-nums {triggerCls} {badgeCls} hover:brightness-125 disabled:opacity-40 transition"
		title="Change status"
	>
		{busy ? '…' : current}
	</button>
	{#if open}
		<div
			class="absolute right-0 mt-1 z-20 min-w-[120px] rounded-md border border-zinc-700 bg-zinc-900 shadow-lg"
			onclick={(e) => e.stopPropagation()}
			role="menu"
			tabindex="-1"
			onkeydown={(e) => e.key === 'Escape' && close()}
		>
			{#each OPTIONS as opt}
				<button
					type="button"
					onclick={() => setStatus(opt.value)}
					disabled={opt.value === current}
					class="block w-full text-left px-3 py-1.5 text-xs {opt.cls} disabled:opacity-40 disabled:cursor-default first:rounded-t-md last:rounded-b-md"
				>
					{opt.value === current ? '✓ ' : ''}{opt.label}
				</button>
			{/each}
		</div>
	{/if}
</div>
