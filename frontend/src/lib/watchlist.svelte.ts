import { api } from './api';

let cas = $state<Set<string>>(new Set());
let loaded = $state(false);

export const watchlist = {
	get cas() {
		return cas;
	},
	get loaded() {
		return loaded;
	},
	has(ca: string) {
		return cas.has(ca);
	},
	async load() {
		if (loaded) return;
		const r = await api.getWatchlistCas();
		cas = new Set(r.cas);
		loaded = true;
	},
	async add(ca: string) {
		cas = new Set(cas).add(ca);
		try {
			await api.addToWatchlist(ca);
		} catch (e) {
			const next = new Set(cas);
			next.delete(ca);
			cas = next;
			throw e;
		}
	},
	async remove(ca: string) {
		const next = new Set(cas);
		next.delete(ca);
		cas = next;
		try {
			await api.removeFromWatchlist(ca);
		} catch (e) {
			cas = new Set(cas).add(ca);
			throw e;
		}
	},
	async toggle(ca: string) {
		if (cas.has(ca)) await this.remove(ca);
		else await this.add(ca);
	}
};
