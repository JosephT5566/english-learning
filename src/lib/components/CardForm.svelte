<script lang="ts">
	import Icon from '@iconify/svelte';
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

	const commonPartsOfSpeech: { value: PartOfSpeech; label: string }[] = [
		{ value: 'noun', label: 'Noun' },
		{ value: 'verb', label: 'Verb' },
		{ value: 'adjective', label: 'Adjective' },
		{ value: 'adverb', label: 'Adverb' },
		{ value: 'phrase', label: 'Phrase' },
	];
	const additionalPartsOfSpeech: { value: PartOfSpeech; label: string }[] = [
		{ value: 'pronoun', label: 'Pronoun' },
		{ value: 'determiner', label: 'Determiner' },
		{ value: 'preposition', label: 'Preposition' },
		{ value: 'conjunction', label: 'Conjunction' },
		{ value: 'interjection', label: 'Interjection' },
		{ value: 'particle', label: 'Particle' },
		{ value: 'auxiliary', label: 'Auxiliary' },
		{ value: 'numeral', label: 'Numeral' },
		{ value: 'other', label: 'Other' },
	];

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
	let synonyms = $state<string[]>([...(draft?.synonyms ?? initial?.synonyms ?? [])]);
	let antonyms = $state<string[]>([...(draft?.antonyms ?? initial?.antonyms ?? [])]);
	let synonymInput = $state('');
	let antonymInput = $state('');
	let note = $state(draft?.note ?? initial?.note ?? '');
	let supplementaryNote = $state(draft?.supplementary_note ?? initial?.supplementary_note ?? '');
	let learnedOn = $state(draft?.learned_on ?? initial?.learned_on ?? localToday());

	const hasWordDetails = Boolean(
		(draft?.pronunciation ?? initial?.pronunciation) ||
			(draft?.romanization ?? initial?.romanization) ||
			(draft?.part_of_speech ?? initial?.part_of_speech) ||
			(draft?.target_language_definition ?? initial?.target_language_definition),
	);
	const hasExample = Boolean(
		(draft?.example_sentence ?? initial?.example_sentence) ||
			(draft?.example_translation ?? initial?.example_translation) ||
			(draft?.example_source ?? initial?.example_source),
	);
	const hasConnections = Boolean(
		(draft?.synonyms ?? initial?.synonyms ?? []).length ||
			(draft?.antonyms ?? initial?.antonyms ?? []).length,
	);
	const hasNotes = Boolean(
		(draft?.note ?? initial?.note) || (draft?.supplementary_note ?? initial?.supplementary_note),
	);

	function addWords(target: 'synonyms' | 'antonyms'): void {
		const input = target === 'synonyms' ? synonymInput : antonymInput;
		const current = target === 'synonyms' ? synonyms : antonyms;
		const additions = words(input).filter(
			(item) => !current.some((existing) => existing.toLocaleLowerCase() === item.toLocaleLowerCase()),
		);

		if (target === 'synonyms') {
			synonyms = [...synonyms, ...additions];
			synonymInput = '';
		} else {
			antonyms = [...antonyms, ...additions];
			antonymInput = '';
		}
	}

	function removeWord(target: 'synonyms' | 'antonyms', index: number): void {
		if (target === 'synonyms') {
			synonyms = synonyms.filter((_, itemIndex) => itemIndex !== index);
		} else {
			antonyms = antonyms.filter((_, itemIndex) => itemIndex !== index);
		}
	}

	function handleWordKeydown(event: KeyboardEvent, target: 'synonyms' | 'antonyms'): void {
		if (event.key === 'Enter' || event.key === ',') {
			event.preventDefault();
			addWords(target);
		}
	}

	function submittedWords(current: string[], pending: string): string[] {
		const additions = words(pending);
		return [...current, ...additions].filter(
			(item, index, values) =>
				values.findIndex((value) => value.toLocaleLowerCase() === item.toLocaleLowerCase()) === index,
		);
	}

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
			synonyms: submittedWords(synonyms, synonymInput),
			antonyms: submittedWords(antonyms, antonymInput),
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
	<fieldset disabled={busy || locked}>
		<div class="form-intro">
			<p>Start with the two things you need to study. Add detail only when it helps.</p>
			<span><b aria-hidden="true">*</b> Required</span>
		</div>

		<div class="essential-fields">
			<label>
				<span>Term <b aria-hidden="true">*</b></span>
				<input aria-label="Term" bind:value={term} required maxlength="255" autocomplete="off" />
			</label>
			<label>
				<span>Meaning <b aria-hidden="true">*</b></span>
				<textarea aria-label="Meaning" bind:value={meaning} required maxlength="2000"></textarea>
			</label>
		{#if language === 'ja'}
				<label>
					<span>Reading <small>Optional</small></span>
					<input aria-label="Reading" bind:value={reading} maxlength="255" autocomplete="off" />
				</label>
		{/if}
		</div>

		<div class="optional-sections">
			<details open={hasWordDetails}>
				<summary>
					<span>Word details</span>
					<small>Pronunciation, type, definition, and date</small>
				</summary>
				<div class="section-fields two-column">
					{#if language === 'ja'}
						<label><span>Romanization</span><input bind:value={romanization} maxlength="255" /></label>
					{:else}
						<label><span>Pronunciation</span><input bind:value={pronunciation} maxlength="255" /></label>
					{/if}
					<label><span>Learned on</span><input type="date" bind:value={learnedOn} /></label>
					<label>
						<span>Part of speech</span>
						<select bind:value={partOfSpeech}>
							<option value="">Not set</option>
							<optgroup label="Common">
								{#each commonPartsOfSpeech as option (option.value)}
									<option value={option.value}>{option.label}</option>
								{/each}
							</optgroup>
							<optgroup label="More">
								{#each additionalPartsOfSpeech as option (option.value)}
									<option value={option.value}>{option.label}</option>
								{/each}
							</optgroup>
						</select>
					</label>
					{#if partOfSpeech === 'other'}
						<label>
							<span>Type detail</span>
							<input bind:value={partOfSpeechDetail} required maxlength="100" />
						</label>
					{/if}
					<label class="wide">
						<span>Definition in the language you’re learning</span>
						<textarea bind:value={definition} maxlength="2000"></textarea>
					</label>
				</div>
			</details>

			<details open={hasExample}>
				<summary>
					<span>Example</span>
					<small>Sentence, translation, and source</small>
				</summary>
				<div class="section-fields">
					<label><span>Example sentence</span><textarea bind:value={exampleSentence} maxlength="1000"></textarea></label>
					<label><span>Translation</span><textarea bind:value={exampleTranslation} maxlength="1000"></textarea></label>
					<label><span>Source</span><input bind:value={exampleSource} maxlength="500" /></label>
				</div>
			</details>

			<details open={hasConnections}>
				<summary>
					<span>Related words</span>
					<small>Synonyms and antonyms</small>
				</summary>
				<div class="section-fields two-column">
					<div class="token-field">
						<label for="synonym-input">Synonyms</label>
						<div class="token-list" aria-live="polite">
							{#each synonyms as synonym, index (`${synonym}-${index}`)}
								<span class="token">
									{synonym}
									<button type="button" aria-label={`Remove synonym ${synonym}`} onclick={() => removeWord('synonyms', index)}>
										<Icon icon="solar:close-circle-linear" width="16" height="16" aria-hidden="true" />
									</button>
								</span>
							{/each}
						</div>
						<div class="token-entry">
							<input id="synonym-input" bind:value={synonymInput} onkeydown={(event) => handleWordKeydown(event, 'synonyms')} onblur={() => addWords('synonyms')} placeholder="Type a word" autocomplete="off" />
							<button type="button" onclick={() => addWords('synonyms')} disabled={!synonymInput.trim()}>Add</button>
						</div>
						<small>Press Enter after each word.</small>
					</div>
					<div class="token-field">
						<label for="antonym-input">Antonyms</label>
						<div class="token-list" aria-live="polite">
							{#each antonyms as antonym, index (`${antonym}-${index}`)}
								<span class="token">
									{antonym}
									<button type="button" aria-label={`Remove antonym ${antonym}`} onclick={() => removeWord('antonyms', index)}>
										<Icon icon="solar:close-circle-linear" width="16" height="16" aria-hidden="true" />
									</button>
								</span>
							{/each}
						</div>
						<div class="token-entry">
							<input id="antonym-input" bind:value={antonymInput} onkeydown={(event) => handleWordKeydown(event, 'antonyms')} onblur={() => addWords('antonyms')} placeholder="Type a word" autocomplete="off" />
							<button type="button" onclick={() => addWords('antonyms')} disabled={!antonymInput.trim()}>Add</button>
						</div>
						<small>Press Enter after each word.</small>
					</div>
				</div>
			</details>

			<details open={hasNotes}>
				<summary>
					<span>Notes</span>
					<small>Personal context and supplementary detail</small>
				</summary>
				<div class="section-fields">
					<label><span>Note</span><textarea bind:value={note} maxlength="4000"></textarea></label>
					<label><span>Supplementary note</span><textarea bind:value={supplementaryNote} maxlength="4000"></textarea></label>
				</div>
			</details>
		</div>
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

<style>
	.card-form fieldset {
		display: grid;
		gap: 1.5rem;
	}

	.form-intro {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 1rem;
		padding-bottom: 1rem;
		border-bottom: 1px solid rgba(64, 117, 166, 0.2);
	}

	.form-intro p,
	.form-intro span {
		margin: 0;
	}

	.form-intro p {
		max-width: 42ch;
		color: #405c73;
		line-height: 1.5;
	}

	.form-intro span,
	.token-field > small {
		color: #60788c;
		font-size: 0.76rem;
	}

	b {
		color: #a34646;
	}

	.essential-fields,
	.section-fields {
		display: grid;
		gap: 1rem;
	}

	.essential-fields textarea {
		min-height: 7rem;
	}

	.essential-fields small {
		margin-left: 0.35rem;
		color: #60788c;
		font-size: 0.72rem;
		font-weight: 400;
	}

	.optional-sections {
		display: grid;
		border-top: 1px solid rgba(64, 117, 166, 0.24);
	}

	details {
		border-bottom: 1px solid rgba(64, 117, 166, 0.24);
	}

	summary {
		padding: 1rem 2rem 1rem 0;
		color: #20394e;
		cursor: pointer;
		list-style-position: outside;
	}

	summary::marker {
		color: #4075a6;
	}

	summary span,
	summary small {
		display: block;
	}

	summary span {
		font-weight: 750;
	}

	summary small {
		margin-top: 0.2rem;
		color: #60788c;
		font-size: 0.78rem;
		font-weight: 400;
	}

	summary:focus-visible {
		border-radius: 0.4rem;
		outline: 3px solid rgba(64, 117, 166, 0.28);
		outline-offset: 2px;
	}

	.section-fields {
		padding: 0 0 1.25rem 1rem;
	}

	.two-column {
		grid-template-columns: repeat(2, minmax(0, 1fr));
	}

	.two-column .wide {
		grid-column: 1 / -1;
	}

	.token-field {
		display: grid;
		align-content: start;
		gap: 0.4rem;
	}

	.token-field > label {
		display: block;
	}

	.token-list {
		display: flex;
		min-height: 0.25rem;
		flex-wrap: wrap;
		gap: 0.4rem;
	}

	.token {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		max-width: 100%;
		padding: 0.28rem 0.35rem 0.28rem 0.6rem;
		border-radius: 999px;
		color: #315f89;
		background: rgba(64, 117, 166, 0.12);
		font-size: 0.82rem;
		font-weight: 700;
		overflow-wrap: anywhere;
	}

	.token button {
		display: grid;
		width: 1.35rem;
		height: 1.35rem;
		padding: 0;
		place-items: center;
		border: 0;
		border-radius: 999px;
		color: #315f89;
		background: rgba(255, 255, 255, 0.65);
		font: inherit;
		line-height: 1;
		cursor: pointer;
	}

	.token-entry {
		display: grid;
		grid-template-columns: minmax(0, 1fr) auto;
		gap: 0.5rem;
	}

	.token-entry button {
		padding: 0.55rem 0.7rem;
		border: 1px solid rgba(49, 95, 137, 0.4);
		border-radius: 0.55rem;
		color: #315f89;
		background: rgba(255, 255, 255, 0.72);
		font: inherit;
		font-weight: 700;
		cursor: pointer;
	}

	.token-entry button:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	@media (max-width: 40rem) {
		.form-intro {
			align-items: flex-start;
			flex-direction: column;
			gap: 0.5rem;
		}

		.two-column {
			grid-template-columns: 1fr;
		}

		.two-column .wide {
			grid-column: auto;
		}

		.section-fields {
			padding-left: 0;
		}
	}
</style>
