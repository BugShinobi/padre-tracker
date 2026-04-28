<script lang="ts">
	import { api } from '$lib/api';

	type Props = { ca: string };
	let { ca }: Props = $props();

	let note = $state('');
	let savedNote = $state('');
	let updatedAt = $state<string | null>(null);
	let loading = $state(true);
	let saving = $state(false);
	let error = $state<string | null>(null);
	let timer: ReturnType<typeof setTimeout> | null = null;

	$effect(() => {
		const target = ca;
		if (!target) return;
		loading = true;
		api
			.getNote(target)
			.then((r) => {
				if (target !== ca) return;
				note = r.note;
				savedNote = r.note;
				updatedAt = r.updated_at;
				error = null;
			})
			.catch((e) => {
				error = e.message;
			})
			.finally(() => {
				loading = false;
			});
	});

	const dirty = $derived(note !== savedNote);

	$effect(() => {
		const v = note;
		if (loading || v === savedNote) return;
		if (timer) clearTimeout(timer);
		timer = setTimeout(async () => {
			saving = true;
			try {
				const r = await api.saveNote(ca, v);
				savedNote = r.note;
				updatedAt = r.updated_at;
				error = null;
			} catch (e) {
				error = e instanceof Error ? e.message : 'save failed';
			} finally {
				saving = false;
			}
		}, 600);
	});

	const status = $derived(
		loading ? 'loading…' : saving ? 'saving…' : dirty ? 'unsaved' : updatedAt ? 'saved' : ''
	);
</script>

<div class="rounded-lg border border-zinc-800 bg-zinc-900/40 mb-6">
	<div class="flex items-center justify-between bg-zinc-900/60 px-3 py-1.5">
		<span class="text-xs uppercase tracking-wider text-zinc-400">Notes</span>
		<span
			class="text-[10px] tabular-nums {error
				? 'text-rose-400'
				: dirty || saving
					? 'text-amber-400'
					: 'text-zinc-500'}"
			title={error ?? ''}
		>{error ? 'error' : status}</span>
	</div>
	<textarea
		bind:value={note}
		disabled={loading}
		placeholder="Personal notes — autosaved. Why is this token interesting? What changed? What to watch for?"
		rows="4"
		class="w-full bg-transparent border-0 px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 resize-y focus:outline-none focus:ring-0"
	></textarea>
</div>
