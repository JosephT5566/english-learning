import { writable, derived } from 'svelte/store';
import type { WordItem } from '$lib/types';

export const wordList = writable<WordItem[]>([]);
export const currentIdx = writable(0);

export const current = derived(
  [wordList, currentIdx],
  ([$due, $idx]) => $due[$idx]
);

// export function nextQuestion(loopWrongAgain = true) {
export function nextQuestion() {
  currentIdx.update(i => i + 1);
}

export function restartWithWrongs(wrongs: WordItem[]) {
  wordList.set(wrongs);
  currentIdx.set(0);
}
