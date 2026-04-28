import { api } from './api';

const cas = $state<Set<string>>(new Set());
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
		cas.clear();
		r.cas.forEach((c) => cas.add(c));
		loaded = true;
	},
	async add(ca: string) {
		cas.add(ca);
		try {
			await api.addToWatchlist(ca);
		} catch (e) {
			cas.delete(ca);
			throw e;
		}
	},
	async remove(ca: string) {
		cas.delete(ca);
		try {
			await api.removeFromWatchlist(ca);
		} catch (e) {
			cas.add(ca);
			throw e;
		}
	},
	async toggle(ca: string) {
		if (cas.has(ca)) await this.remove(ca);
		else await this.add(ca);
	}
};
