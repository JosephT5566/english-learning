import { writable, derived } from 'svelte/store';
import type { WordItem } from '$lib/types';

export const dueItems = writable<WordItem[]>([]);
export const currentIdx = writable(0);

export const current = derived(
  [dueItems, currentIdx],
  ([$due, $idx]) => $due[$idx]
);

// export function nextQuestion(loopWrongAgain = true) {
export function nextQuestion() {
  currentIdx.update(i => i + 1);
}

export function restartWithWrongs(wrongs: WordItem[]) {
  dueItems.set(wrongs);
  currentIdx.set(0);
}
