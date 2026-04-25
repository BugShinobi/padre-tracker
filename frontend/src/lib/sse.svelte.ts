import type { QueryClient } from '@tanstack/svelte-query';
import type { EnrichedRow } from './types';

const FEED_MAX = 20;

class LiveFeedStore {
	items = $state<EnrichedRow[]>([]);
	connected = $state(false);
	lastTickAt = $state<number | null>(null);
}

export const live = new LiveFeedStore();

let es: EventSource | null = null;

export function connectSse(queryClient: QueryClient): void {
	if (es) return;
	es = new EventSource('/api/stream/calls');

	es.addEventListener('ready', () => {
		live.connected = true;
		live.lastTickAt = Date.now();
	});

	es.addEventListener('new', (ev) => {
		try {
			const row = JSON.parse((ev as MessageEvent).data) as EnrichedRow;
			const filtered = live.items.filter((r) => r.contract_address !== row.contract_address);
			live.items = [row, ...filtered].slice(0, FEED_MAX);
			live.lastTickAt = Date.now();
			queryClient.invalidateQueries({ queryKey: ['day'] });
			queryClient.invalidateQueries({ queryKey: ['overview'] });
		} catch (e) {
			console.error('sse parse failed', e);
		}
	});

	es.addEventListener('ping', () => {
		live.lastTickAt = Date.now();
	});

	es.onerror = () => {
		live.connected = false;
	};
}

export function disconnectSse(): void {
	es?.close();
	es = null;
	live.connected = false;
}
