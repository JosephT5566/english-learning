<script lang="ts">
	import type { Deck, DeckCreate, TargetLanguage } from '$lib/api/contracts';
	import MutationNotice from './MutationNotice.svelte';
	import type { MutationErrorCopy } from '$lib/management/mutations';

	let {
		language,
		initial = null,
		draft = null,
		busy = false,
		locked = false,
		notice = null,
		onsave,
		oncancel,
		onreload,
	}: {
		language: TargetLanguage;
		initial?: Deck | null;
		draft?: DeckCreate | null;
		busy?: boolean;
		locked?: boolean;
		notice?: MutationErrorCopy | null;
		onsave: (payload: DeckCreate) => void;
		oncancel: () => void;
		onreload?: () => void;
	} = $props();

	let title = $state(draft?.title ?? initial?.title ?? '');
	let explanationLanguage: DeckCreate['explanation_language'] = $state(
		draft?.explanation_language ?? initial?.explanation_language ?? 'zh-TW',
	);
</script>

<form
	class="management-form"
	onsubmit={(event) => {
		event.preventDefault();
		onsave({ title, target_language: language, explanation_language: explanationLanguage });
	}}
>
	<fieldset disabled={busy || locked}>
		<label>
			<span>Deck title</span>
			<input bind:value={title} required maxlength="100" autocomplete="off" />
		</label>
		<label>
			<span>Explanation language</span>
			<select bind:value={explanationLanguage}>
				<option value="zh-TW">Traditional Chinese</option>
				<option value="en">English</option>
				<option value="ja">Japanese</option>
			</select>
		</label>
	</fieldset>
	<p class="form-context">Cards in this deck are {language === 'ja' ? 'Japanese' : 'English'}.</p>
	{#if notice}<MutationNotice {notice} {onreload} />{/if}
	<div class="form-actions">
		<button type="button" class="secondary-button" disabled={busy} onclick={oncancel}>Cancel</button
		>
		<button type="submit" class="primary-button" disabled={busy}
			>{busy ? 'Saving…' : 'Save deck'}</button
		>
	</div>
</form>
