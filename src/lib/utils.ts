// 各階段的間隔天數, stage: 1-5
export const STAGE_INTERVALS = [0, 1, 3, 7, 14, 30];

export function calNewEaseFactor(quality: number, currentEaseFactor: number): number {
	const minEaseFactor = 1.3;
	const maxEaseFactor = 2.5;
	let newEaseFactor = currentEaseFactor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02));
	if (newEaseFactor < minEaseFactor) newEaseFactor = minEaseFactor;
	if (newEaseFactor > maxEaseFactor) newEaseFactor = maxEaseFactor;

	return parseFloat(newEaseFactor.toFixed(2));
}
