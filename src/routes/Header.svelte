<script lang="ts">
  import { page } from "$app/state";
  import { resolve } from "$app/paths";
  import { goto } from "$app/navigation";
  import { signOut } from "$lib/auth";
  import { authSession } from "$lib/stores/auth";
  import AccountMenu from "$lib/components/AccountMenu.svelte";
  import GoogleSignIn from "$lib/components/GoogleSignIn.svelte";
  import { Dialog } from "bits-ui";
  import { browser } from "$app/environment";
  import { isSignedIn } from "$lib/stores/auth";
  import HouseIcon from "@lucide/svelte/icons/house";
  import PlayingCardsFunIcon from "@lucide/svelte/icons/playing-cards-fan";
  import WalletCardsIcon from "@lucide/svelte/icons/wallet-cards";
  import SearchIcon from "@lucide/svelte/icons/search";

  let language = $derived(
    browser && page.url.searchParams.get("language") === "ja" ? "ja" : "en",
  );
  let homePath = $derived(resolve("/"));
  let reviewPath = $derived(
    $authSession.kind === "signed-out" ? homePath : resolve("/review"),
  );
  let signInOpen = $state(false);
  $effect(() => {
    if ($isSignedIn) signInOpen = false;
  });
  async function handleSignOut() {
    signOut();
    await goto(resolve("/"));
  }
  let decksPath = $derived(resolve("/decks"));
  let searchPath = $derived(resolve("/search"));
</script>

<header>
  <nav
    aria-label="Primary navigation"
    hidden={$authSession.kind !== "guest" &&
      $authSession.kind !== "authenticated"}
  >
    <ul>
      <li>
        <a
          href={homePath}
          aria-label="Home"
          title="Home"
          aria-current={page.url.pathname === homePath ? "page" : undefined}
          ><HouseIcon size={20} aria-hidden="true" /></a
        >
      </li>
      <li>
        <a
          href={reviewPath}
          aria-label={$isSignedIn ? "Review" : "Guest review"}
          title={$isSignedIn ? "Review" : "Guest review"}
          aria-current={page.url.pathname === reviewPath ? "page" : undefined}
          ><PlayingCardsFunIcon size={20} aria-hidden="true" /></a
        >
      </li>
      {#if $isSignedIn}
        <li>
          <a
            href={`${decksPath}?language=${language}`}
            aria-label="Decks"
            title="Decks"
            aria-current={page.url.pathname.startsWith(decksPath) ||
            page.url.pathname.includes("/cards/")
              ? "page"
              : undefined}><WalletCardsIcon size={20} aria-hidden="true" /></a
          >
        </li>
        <li>
          <a
            href={searchPath}
            aria-label="Search"
            title="Search"
            aria-current={page.url.pathname === searchPath ? "page" : undefined}
            ><SearchIcon size={20} aria-hidden="true" /></a
          >
        </li>
      {/if}
    </ul>
  </nav>
  <div class="account-control">
    <AccountMenu
      profile={$authSession.kind === "authenticated"
        ? $authSession.profile
        : null}
      onSignIn={() => {
        signInOpen = true;
      }}
      onSignOut={handleSignOut}
    />
  </div>
</header>

<Dialog.Root bind:open={signInOpen}>
  <Dialog.Portal>
    <Dialog.Overlay class="account-dialog-overlay" />
    <Dialog.Content
      class="account-dialog"
      onkeydown={(event) => {
        event.stopPropagation();
        if (event.key === "Escape") {
          event.preventDefault();
          signInOpen = false;
        }
      }}
    >
      <Dialog.Title>Sign in</Dialog.Title>
      <Dialog.Description
        >Use Google to open your private decks and review history.</Dialog.Description
      >
      <GoogleSignIn />
      <Dialog.Close class="account-dialog-close">Close</Dialog.Close>
    </Dialog.Content>
  </Dialog.Portal>
</Dialog.Root>

<style>
  header {
    position: relative;
    z-index: 10;
    display: flex;
    justify-content: center;
    align-items: center;
    padding: 0.75rem 1rem 0.25rem;
  }

  .account-control {
    position: absolute;
    right: 1rem;
    top: 1rem;
  }
  :global(.account-dialog-overlay) {
    position: fixed;
    inset: 0;
    z-index: 60;
    background: rgba(22, 42, 60, 0.35);
  }
  :global(.account-dialog) {
    position: fixed;
    z-index: 61;
    left: 50%;
    top: 50%;
    transform: translate(-50%, -50%);
    width: min(26rem, calc(100vw - 2rem));
    box-sizing: border-box;
    padding: 1.5rem;
    border-radius: 1rem;
    background: white;
    box-shadow: 0 16px 64px #20394e33;
  }
  :global(.account-dialog h2) {
    margin-top: 0;
  }
  :global(.account-dialog p) {
    color: #526b7f;
  }
  :global(.account-dialog-close) {
    margin-top: 1rem;
    min-height: 44px;
    padding: 0.5rem 1rem;
    border: 1px solid #4075a644;
    border-radius: 0.6rem;
  }
  nav[hidden] {
    visibility: hidden;
  }

  nav {
    display: flex;
    justify-content: center;
    border: 1px solid rgba(64, 117, 166, 0.16);
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.72);
    box-shadow: 0 6px 20px rgba(47, 78, 105, 0.08);
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

  nav a[aria-current="page"] {
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
      padding-right: 4.25rem;
    }

    nav {
      width: auto;
    }
    ul {
      width: 100%;
    }
    .account-control {
      right: 0.75rem;
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
