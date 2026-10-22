<script lang="ts">
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { authSession } from "$lib/stores/auth";
  import GuestReview from "$lib/components/GuestReview.svelte";
  import OwnedReview from "$lib/components/OwnedReview.svelte";

  type ReviewSession =
    | { kind: "waiting" }
    | { kind: "guest" }
    | { kind: "owned"; subject: string };
  let session: ReviewSession = $state({ kind: "waiting" });

  $effect(() => {
    const auth = $authSession;
    if (auth.kind === "initializing") return;
    if (auth.kind === "authenticated" && auth.profile.sub) {
      if (session.kind !== "owned" || session.subject !== auth.profile.sub) {
        session = { kind: "owned", subject: auth.profile.sub };
      }
    } else if (session.kind !== "owned") {
      if (auth.kind === "guest") {
        if (session.kind !== "guest") session = { kind: "guest" };
      } else void goto(resolve("/"), { replaceState: true });
    }
  });
</script>

{#if session.kind === "owned"}
  {#key session.subject}
    <OwnedReview ownerSubject={session.subject} />
  {/key}
{:else if session.kind === "guest"}
  <GuestReview />
{/if}
