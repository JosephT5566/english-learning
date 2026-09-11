<script lang="ts">
	import type { CardCreate, CardDetail, TargetLanguage } from '$lib/api/contracts';
	import MutationNotice from './MutationNotice.svelte';
	import type { MutationErrorCopy } from '$lib/management/mutations';

	type CardFields = Omit<CardCreate, 'deck_id'>;
	type PartOfSpeech = NonNullable<CardCreate['part_of_speech']>;

	function localToday(): string {
		const now = new Date();
		const month = String(now.getMonth() + 1).padStart(2, '0');
		const day = String(now.getDate()).padStart(2, '0');
		return `${now.getFullYear()}-${month}-${day}`;
	}

	function optional(value: string): string | null {
		const trimmed = value.trim();
		return trimmed || null;
	}

	function words(value: string): string[] {
		return value
			.split(',')
			.map((item) => item.trim())
			.filter(Boolean);
	}

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
		initial?: CardDetail | null;
		draft?: CardFields | null;
		busy?: boolean;
		locked?: boolean;
		notice?: MutationErrorCopy | null;
		onsave: (payload: CardFields) => void;
		oncancel: () => void;
		onreload?: () => void;
	} = $props();

	let term = $state(draft?.term ?? initial?.term ?? '');
	let meaning = $state(draft?.meaning ?? initial?.meaning ?? '');
	let reading = $state(draft?.reading ?? initial?.reading ?? '');
	let pronunciation = $state(draft?.pronunciation ?? initial?.pronunciation ?? '');
	let romanization = $state(draft?.romanization ?? initial?.romanization ?? '');
	let definition = $state(
		draft?.target_language_definition ?? initial?.target_language_definition ?? '',
	);
	let partOfSpeech = $state<PartOfSpeech | ''>(
		(draft?.part_of_speech ?? initial?.part_of_speech ?? '') as PartOfSpeech | '',
	);
	let partOfSpeechDetail = $state(
		draft?.part_of_speech_detail ?? initial?.part_of_speech_detail ?? '',
	);
	let exampleSentence = $state(draft?.example_sentence ?? initial?.example_sentence ?? '');
	let exampleTranslation = $state(draft?.example_translation ?? initial?.example_translation ?? '');
	let exampleSource = $state(draft?.example_source ?? initial?.example_source ?? '');
	let synonyms = $state(draft?.synonyms.join(', ') ?? initial?.synonyms.join(', ') ?? '');
	let antonyms = $state(draft?.antonyms.join(', ') ?? initial?.antonyms.join(', ') ?? '');
	let note = $state(draft?.note ?? initial?.note ?? '');
	let supplementaryNote = $state(draft?.supplementary_note ?? initial?.supplementary_note ?? '');
	let learnedOn = $state(draft?.learned_on ?? initial?.learned_on ?? localToday());

	function submit(): void {
		onsave({
			term,
			meaning,
			reading: language === 'ja' ? optional(reading) : null,
			pronunciation: language === 'en' ? optional(pronunciation) : null,
			romanization: language === 'ja' ? optional(romanization) : null,
			target_language_definition: optional(definition),
			example_sentence: optional(exampleSentence),
			example_translation: optional(exampleTranslation),
			example_source: optional(exampleSource),
			synonyms: words(synonyms),
			antonyms: words(antonyms),
			part_of_speech: partOfSpeech || null,
			part_of_speech_detail: optional(partOfSpeechDetail),
			note: optional(note),
			supplementary_note: optional(supplementaryNote),
			learned_on: optional(learnedOn),
		});
	}
</script>

<form
	class="management-form card-form"
	onsubmit={(event) => {
		event.preventDefault();
		submit();
	}}
>
	<fieldset class="form-grid" disabled={busy || locked}>
		<label><span>Term</span><input bind:value={term} required maxlength="255" /></label>
		<label><span>Meaning</span><input bind:value={meaning} required maxlength="2000" /></label>
		{#if language === 'ja'}
			<label><span>Reading</span><input bind:value={reading} maxlength="255" /></label>
			<label><span>Romanization</span><input bind:value={romanization} maxlength="255" /></label>
		{:else}
			<label><span>Pronunciation</span><input bind:value={pronunciation} maxlength="255" /></label>
		{/if}
		<label><span>Learned on</span><input type="date" bind:value={learnedOn} /></label>
		<label>
			<span>Part of speech</span>
			<select bind:value={partOfSpeech}>
				<option value="">Not set</option>
				{#each ['noun', 'verb', 'adjective', 'adverb', 'pronoun', 'determiner', 'preposition', 'conjunction', 'interjection', 'particle', 'auxiliary', 'numeral', 'phrase', 'other'] as value (value)}
					<option {value}>{value}</option>
				{/each}
			</select>
		</label>
		{#if partOfSpeech === 'other'}<label
				><span>Type detail</span><input
					bind:value={partOfSpeechDetail}
					required
					maxlength="100"
				/></label
			>{/if}
		<label class="wide"
			><span>Definition</span><textarea bind:value={definition} maxlength="2000"></textarea></label
		>
		<label class="wide"
			><span>Example sentence</span><textarea bind:value={exampleSentence} maxlength="1000"
			></textarea></label
		>
		<label class="wide"
			><span>Example translation</span><textarea bind:value={exampleTranslation} maxlength="1000"
			></textarea></label
		>
		<label class="wide"
			><span>Example source</span><input bind:value={exampleSource} maxlength="500" /></label
		>
		<label><span>Synonyms, comma separated</span><input bind:value={synonyms} /></label>
		<label><span>Antonyms, comma separated</span><input bind:value={antonyms} /></label>
		<label class="wide"
			><span>Note</span><textarea bind:value={note} maxlength="4000"></textarea></label
		>
		<label class="wide"
			><span>Supplementary note</span><textarea bind:value={supplementaryNote} maxlength="4000"
			></textarea></label
		>
	</fieldset>
	{#if notice}<MutationNotice {notice} {onreload} />{/if}
	<div class="form-actions">
		<button type="button" class="secondary-button" disabled={busy} onclick={oncancel}>Cancel</button
		>
		<button type="submit" class="primary-button" disabled={busy}
			>{busy ? 'Saving…' : 'Save card'}</button
		>
	</div>
</form>
