import { browser } from '$app/environment';

export type Density = 'compact' | 'comfortable';

export type TablePrefs = {
	density: Density;
	cols: {
		description: boolean;
		groups: boolean;
		holders: boolean;
		flags: boolean;
	};
};

const STORAGE_KEY = 'padre.tablePrefs.v1';

const DEFAULTS: TablePrefs = {
	density: 'comfortable',
	cols: { description: true, groups: true, holders: true, flags: true }
};

function load(): TablePrefs {
	if (!browser) return DEFAULTS;
	try {
		const raw = localStorage.getItem(STORAGE_KEY);
		if (!raw) return DEFAULTS;
		const parsed = JSON.parse(raw);
		return {
			density: parsed.density === 'compact' ? 'compact' : 'comfortable',
			cols: { ...DEFAULTS.cols, ...(parsed.cols ?? {}) }
		};
	} catch {
		return DEFAULTS;
	}
}

export const tablePrefs = $state<TablePrefs>(load());

export function saveTablePrefs() {
	if (!browser) return;
	localStorage.setItem(STORAGE_KEY, JSON.stringify(tablePrefs));
}

export function cellPadding(density: Density): string {
	return density === 'compact' ? 'px-2 py-1.5' : 'px-3 py-3';
}
