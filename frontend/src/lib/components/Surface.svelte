<script lang="ts">
	type Props = {
		variant?: 'card' | 'elevated' | 'glass' | 'gradient-pos' | 'gradient-neg' | 'gradient-cool';
		hover?: boolean;
		padding?: 'none' | 'sm' | 'md' | 'lg';
		class?: string;
		children: import('svelte').Snippet;
	};

	let {
		variant = 'card',
		hover = false,
		padding = 'md',
		class: cls = '',
		children
	}: Props = $props();

	const variantClasses = {
		card: 'bg-zinc-900/50 border border-zinc-800/80 backdrop-blur-sm',
		elevated: 'bg-zinc-900 border border-zinc-700/80',
		glass: 'bg-zinc-950/40 border border-zinc-800/60 backdrop-blur-md',
		'gradient-pos':
			'border border-emerald-500/20 bg-gradient-to-br from-emerald-500/10 via-zinc-900/40 to-cyan-500/5',
		'gradient-neg':
			'border border-rose-500/20 bg-gradient-to-br from-rose-500/10 via-zinc-900/40 to-amber-500/5',
		'gradient-cool':
			'border border-cyan-500/20 bg-gradient-to-br from-cyan-500/10 via-zinc-900/40 to-blue-500/5'
	};

	const paddingClasses = {
		none: '',
		sm: 'p-3',
		md: 'p-4',
		lg: 'p-5'
	};

	const hoverClasses = $derived(
		hover ? 'transition-all duration-200 hover:border-zinc-600 hover:bg-zinc-900/70 cursor-pointer' : ''
	);
</script>

<div class="rounded-xl {variantClasses[variant]} {paddingClasses[padding]} {hoverClasses} {cls}">
	{@render children()}
</div>
