<script lang="ts">
	type Props = {
		active: boolean;
		label: string;
		count?: number | null;
		onclick: () => void;
		variant?: 'default' | 'launchpad';
		color?: string;
	};

	let {
		active,
		label,
		count,
		onclick,
		variant = 'default',
		color = ''
	}: Props = $props();

	const launchpadColor = (lp: string) => {
		const k = lp.split('.')[0].toLowerCase();
		switch (k) {
			case 'pump':
				return 'border-amber-500/50 bg-amber-500/15 text-amber-200';
			case 'bags':
				return 'border-purple-500/50 bg-purple-500/15 text-purple-200';
			case 'bonk':
				return 'border-orange-500/50 bg-orange-500/15 text-orange-200';
			case 'moonshot':
				return 'border-blue-500/50 bg-blue-500/15 text-blue-200';
			case 'printr':
				return 'border-emerald-500/50 bg-emerald-500/15 text-emerald-200';
			default:
				return 'border-zinc-500/50 bg-zinc-500/15 text-zinc-200';
		}
	};

	const activeClass = $derived(
		active
			? variant === 'launchpad'
				? launchpadColor(color || label)
				: 'border-emerald-500/50 bg-emerald-500/15 text-emerald-200'
			: 'border-zinc-700 bg-zinc-900/40 text-zinc-400 hover:border-zinc-600 hover:text-zinc-200'
	);
</script>

<button
	type="button"
	{onclick}
	class="px-2.5 py-1 rounded-full border text-xs whitespace-nowrap transition-all duration-150 {activeClass}"
>
	{label}{#if count != null}<span class="ml-1.5 text-[10px] opacity-70">{count}</span>{/if}
</button>
