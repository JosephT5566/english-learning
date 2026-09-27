<script lang="ts">
	import Header from './Header.svelte';
	import '../app.css';

	let { children } = $props();
</script>

<div class="app">
	<a class="skip-link" href="#main-content">Skip to content</a>

	<Header />

	<main id="main-content" tabindex="-1">
		{@render children()}
	</main>
</div>

<style>
	.app {
		position: relative;
		isolation: isolate;
		display: flex;
		flex-direction: column;
		min-height: 100dvh;
	}

	.skip-link {
		position: fixed;
		z-index: 100;
		top: 0.75rem;
		left: 0.75rem;
		padding: 0.65rem 0.9rem;
		border: 1px solid rgba(64, 117, 166, 0.35);
		border-radius: 0.65rem;
		color: white;
		background: #315f89;
		font-size: 0.875rem;
		font-weight: 750;
		text-decoration: none;
		box-shadow: 0 8px 24px rgba(31, 57, 79, 0.18);
		transform: translateY(calc(-100% - 1rem));
		transition: transform 160ms ease-out;
	}

	.skip-link:focus {
		transform: translateY(0);
	}

	main {
		flex: 1;
		display: flex;
		flex-direction: column;
		width: 100%;
		max-width: 64rem;
		margin: 0 auto;
		box-sizing: border-box;
	}

	main:focus {
		outline: none;
	}

	@media (prefers-reduced-motion: reduce) {
		.skip-link {
			transition: none;
		}
	}
</style>
