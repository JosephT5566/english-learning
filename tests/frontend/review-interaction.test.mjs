import assert from 'node:assert/strict';
import test from 'node:test';

import { canAnswerCard } from '../../src/lib/review/interaction.ts';

test('only an exposed top card can be answered', () => {
	assert.equal(canAnswerCard(true, false, false), false);
	assert.equal(canAnswerCard(false, true, false), false);
	assert.equal(canAnswerCard(true, true, true), false);
	assert.equal(canAnswerCard(true, true, false), true);
});
