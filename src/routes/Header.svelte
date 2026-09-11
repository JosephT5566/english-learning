<script lang="ts">
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import { browser } from '$app/environment';

	let language = $derived(browser && page.url.searchParams.get('language') === 'ja' ? 'ja' : 'en');
	let homePath = $derived(resolve('/'));
	let reviewPath = $derived(resolve('/review'));
	let decksPath = $derived(resolve('/decks'));
</script>

<header>
	<nav aria-label="Primary navigation">
		<ul>
			<li aria-current={page.url.pathname === homePath ? 'page' : undefined}>
				<a href={homePath}>Home</a>
			</li>
			<li aria-current={page.url.pathname === reviewPath ? 'page' : undefined}>
				<a href={reviewPath}>Review</a>
			</li>
			<li
				aria-current={page.url.pathname.startsWith(decksPath) ||
				page.url.pathname.includes('/cards/')
					? 'page'
					: undefined}
			>
				<a href={`${decksPath}?language=${language}`}>Decks</a>
			</li>
		</ul>
	</nav>
</header>

<style>
	header {
		display: flex;
		justify-content: center;
		padding: 0.75rem 1rem 0;
	}

	nav {
		display: flex;
		justify-content: center;
		border: 1px solid rgba(64, 117, 166, 0.16);
		border-radius: 999px;
		background: rgba(255, 255, 255, 0.62);
		box-shadow: 0 6px 20px rgba(47, 78, 105, 0.08);
	}

	ul {
		position: relative;
		padding: 0;
		margin: 0;
		height: 3em;
		display: flex;
		justify-content: center;
		align-items: center;
		list-style: none;
	}

	li {
		position: relative;
		height: 100%;
	}

	li[aria-current='page']::before {
		--size: 6px;
		content: '';
		width: calc(var(--size) * 2);
		height: 0;
		position: absolute;
		bottom: 0;
		left: calc(50% - var(--size));
		border: 0;
		border-bottom: 3px solid var(--color-theme-2);
	}

	nav a {
		display: flex;
		height: 100%;
		align-items: center;
		padding: 0 0.75rem;
		color: var(--color-text);
		font-weight: 700;
		font-size: 0.72rem;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		text-decoration: none;
		transition: color 0.2s linear;
	}

	a:hover {
		color: var(--color-theme-1);
		text-decoration: none;
	}
</style>
