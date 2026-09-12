<script lang="ts">
	import type { TargetLanguage } from '$lib/api/contracts';

	let {
		current,
		englishHref,
		japaneseHref,
	}: {
		current: TargetLanguage;
		englishHref: string;
		japaneseHref: string;
	} = $props();
</script>

<nav class="language-tabs" aria-label="Learning language">
	<a
		class:active={current === 'en'}
		aria-current={current === 'en' ? 'page' : undefined}
		href={englishHref}
	>
		<span>EN</span>
		English
	</a>
	<a
		class:active={current === 'ja'}
		aria-current={current === 'ja' ? 'page' : undefined}
		href={japaneseHref}
	>
		<span>JA</span>
		日本語
	</a>
</nav>

<style>
	.language-tabs {
		display: inline-flex;
		gap: 0.25rem;
		padding: 0.25rem;
		border: 1px solid rgba(64, 117, 166, 0.22);
		border-radius: 0.9rem;
		background: rgba(255, 255, 255, 0.52);
	}

	a {
		display: flex;
		align-items: center;
		gap: 0.45rem;
		padding: 0.55rem 0.8rem;
		border-radius: 0.65rem;
		color: #39546c;
		font-weight: 700;
		text-decoration: none;
	}

	a:hover {
		text-decoration: none;
		background: rgba(255, 255, 255, 0.7);
	}

	a.active {
		color: white;
		background: #4075a6;
		box-shadow: 0 4px 12px rgba(38, 74, 107, 0.18);
	}

	span {
		font-family: var(--font-mono);
		font-size: 0.68rem;
		letter-spacing: 0.08em;
		opacity: 0.72;
	}
</style>
