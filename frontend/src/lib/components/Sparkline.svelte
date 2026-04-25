<script lang="ts">
	type Props = {
		data: number[];
		height?: number;
		stroke?: string;
		fill?: string;
		strokeWidth?: number;
	};

	let {
		data,
		height = 56,
		stroke = 'rgb(16 185 129)',
		fill = 'rgb(16 185 129 / 0.15)',
		strokeWidth = 1.5
	}: Props = $props();

	const width = 200;
	const pad = 3;

	const min = $derived(data.length ? Math.min(...data) : 0);
	const max = $derived(data.length ? Math.max(...data) : 1);
	const span = $derived(max - min || 1);

	function pointFor(v: number, i: number, len: number) {
		const x = len > 1 ? pad + (i / (len - 1)) * (width - pad * 2) : width / 2;
		const y = height - pad - ((v - min) / span) * (height - pad * 2);
		return [x, y] as const;
	}

	const linePoints = $derived(
		data.map((v, i) => pointFor(v, i, data.length).join(',')).join(' ')
	);

	const areaPath = $derived(
		data.length === 0
			? ''
			: (() => {
					const pts = data.map((v, i) => pointFor(v, i, data.length));
					const move = `M ${pts[0][0]},${pts[0][1]}`;
					const lines = pts.slice(1).map(([x, y]) => `L ${x},${y}`).join(' ');
					return `${move} ${lines} L ${pts[pts.length - 1][0]},${height - pad} L ${pts[0][0]},${height - pad} Z`;
				})()
	);
</script>

<svg
	viewBox="0 0 {width} {height}"
	class="w-full block"
	preserveAspectRatio="none"
	{height}
	role="img"
	aria-label="trend"
>
	{#if data.length}
		<path d={areaPath} {fill} />
		<polyline
			points={linePoints}
			fill="none"
			{stroke}
			stroke-width={strokeWidth}
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
	{/if}
</svg>
