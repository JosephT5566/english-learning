<script lang="ts">
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import { browser } from '$app/environment';
	import { isSignedIn } from '$lib/stores/auth';
	import HouseIcon from '@lucide/svelte/icons/house';
	import PlayingCardsFunIcon from '@lucide/svelte/icons/playing-cards-fan';
	import WalletCardsIcon from '@lucide/svelte/icons/wallet-cards';
	import SearchIcon from '@lucide/svelte/icons/search';

	let language = $derived(browser && page.url.searchParams.get('language') === 'ja' ? 'ja' : 'en');
	let homePath = $derived(resolve('/'));
	let reviewPath = $derived(resolve('/review'));
	let decksPath = $derived(resolve('/decks'));
	let searchPath = $derived(resolve('/search'));
</script>

<header>
	<nav
		aria-label="Primary navigation"
		class:signed-out={!$isSignedIn}
		inert={!$isSignedIn}
		aria-hidden={!$isSignedIn}
	>
		<ul>
			<li>
				<a
					href={homePath}
					aria-label="Home"
					title="Home"
					aria-current={page.url.pathname === homePath ? 'page' : undefined}
					><HouseIcon size={20} aria-hidden="true" /></a
				>
			</li>
			<li>
				<a
					href={reviewPath}
					aria-label="Review"
					title="Review"
					aria-current={page.url.pathname === reviewPath ? 'page' : undefined}
					><PlayingCardsFunIcon size={20} aria-hidden="true" /></a
				>
			</li>
			<li>
				<a
					href={`${decksPath}?language=${language}`}
					aria-label="Decks"
					title="Decks"
					aria-current={page.url.pathname.startsWith(decksPath) ||
					page.url.pathname.includes('/cards/')
						? 'page'
						: undefined}><WalletCardsIcon size={20} aria-hidden="true" /></a
				>
			</li>
			<li>
				<a
					href={searchPath}
					aria-label="Search"
					title="Search"
					aria-current={page.url.pathname === searchPath ? 'page' : undefined}
					><SearchIcon size={20} aria-hidden="true" /></a
				>
			</li>
		</ul>
	</nav>
</header>

<style>
	header {
		position: relative;
		z-index: 10;
		display: flex;
		justify-content: center;
		padding: 0.75rem 1rem 0.25rem;
	}

	nav {
		display: flex;
		justify-content: center;
		border: 1px solid rgba(64, 117, 166, 0.16);
		border-radius: 999px;
		background: rgba(255, 255, 255, 0.72);
		box-shadow: 0 6px 20px rgba(47, 78, 105, 0.08);
	}

	nav.signed-out {
		visibility: hidden;
	}

	ul {
		display: flex;
		align-items: center;
		min-height: 3rem;
		padding: 0.25rem;
		margin: 0;
		list-style: none;
	}

	li {
		display: flex;
	}

	nav a {
		display: flex;
		align-items: center;
		justify-content: center;
		min-width: 2.75rem;
		min-height: 2.75rem;
		padding: 0 0.85rem;
		border-radius: 999px;
		color: #405c73;
		text-decoration: none;
		transition:
			color 160ms ease-out,
			background-color 160ms ease-out;
	}

	nav a:hover {
		color: #264f73;
		background: rgba(64, 117, 166, 0.1);
		text-decoration: none;
	}

	nav a[aria-current='page'] {
		color: white;
		background: #4075a6;
	}

	nav a:focus-visible {
		outline: 3px solid rgba(64, 117, 166, 0.32);
		outline-offset: 2px;
	}

	@media (max-width: 30rem) {
		header {
			padding-inline: 0.75rem;
		}

		nav,
		ul {
			width: 100%;
		}

		li {
			flex: 1;
		}

		nav a {
			width: 100%;
			padding-inline: 0.4rem;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		nav a {
			transition: none;
		}
	}
</style>
