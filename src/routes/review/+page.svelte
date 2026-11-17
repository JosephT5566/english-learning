<script lang="ts">
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { authSession } from "$lib/stores/auth";
  import GuestReview from "$lib/components/GuestReview.svelte";
  import OwnedReview from "$lib/components/OwnedReview.svelte";

  type ReviewSession =
    | { kind: "waiting" }
    | { kind: "guest" }
    | { kind: "owned"; ownerId: number };
  let session: ReviewSession = $state({ kind: "waiting" });

  $effect(() => {
    const auth = $authSession;
    if (auth.kind === "initializing") return;
    if (auth.kind === "authenticated" && auth.profile.id) {
      if (session.kind !== "owned" || session.ownerId !== auth.profile.id) {
        session = { kind: "owned", ownerId: auth.profile.id };
      }
    } else if (auth.kind === "guest") {
      if (session.kind !== "guest") session = { kind: "guest" };
    } else if (auth.kind === "expired") {
      if (auth.profile && session.kind !== "owned")
        session = { kind: "owned", ownerId: auth.profile.id };
    } else if (session.kind !== "owned") {
      if (session.kind !== "waiting") session = { kind: "waiting" };
      void goto(resolve("/"), { replaceState: true });
    }
  });
</script>

{#if session.kind === "owned"}
  {#key session.ownerId}
    <OwnedReview ownerId={session.ownerId} />
  {/key}
{:else if session.kind === "guest" && $authSession.kind === "guest"}
  <GuestReview />
{/if}
