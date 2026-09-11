export function canAnswerCard(isTopCard: boolean, isBack: boolean, isBusy: boolean): boolean {
	return isTopCard && isBack && !isBusy;
}
