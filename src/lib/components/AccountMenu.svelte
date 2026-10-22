<script lang="ts">
  import { DropdownMenu } from "bits-ui";
  import UserRound from "@lucide/svelte/icons/user-round";
  import type { getProfile } from "$lib/auth";

  type Profile = Pick<
    NonNullable<ReturnType<typeof getProfile>>,
    "name" | "email" | "picture"
  >;

  let {
    profile = null,
    onSignIn,
    onSignOut,
  }: {
    profile?: Profile | null;
    onSignIn: () => void;
    onSignOut: () => void;
  } = $props();

  let open = $state(false);
  let trigger = $state<HTMLButtonElement | null>(null);
  let failedPicture = $state<string | null>(null);
  let displayName = $derived(
    profile?.name?.trim() || profile?.email || "Signed-in account",
  );
  let initials = $derived(
    displayName
      .split(/\s+/)
      .filter(Boolean)
      .filter((_, index, words) => index === 0 || index === words.length - 1)
      .map((word) => Array.from(word)[0])
      .join("")
      .toLocaleUpperCase(),
  );

  function stopKeyboardPropagation(event: KeyboardEvent) {
    event.stopPropagation();
    if (event.key === "Escape") open = false;
  }
</script>

<DropdownMenu.Root bind:open>
  <DropdownMenu.Trigger
    bind:ref={trigger}
    aria-label={profile
      ? `Account menu for ${displayName}`
      : "Guest account menu"}
    title={profile ? displayName : "Guest"}
    class="flex size-11 shrink-0 items-center justify-center overflow-hidden rounded-full border border-[#4075a6]/20 bg-white/80 text-sm font-semibold text-[#405c73] shadow-sm hover:bg-[#4075a6]/10 focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-[#4075a6]/40"
    onkeydown={stopKeyboardPropagation}
  >
    {#if profile?.picture && profile.picture !== failedPicture}
      <img
        src={profile.picture}
        alt=""
        referrerpolicy="no-referrer"
        class="size-full object-cover"
        onerror={() => (failedPicture = profile?.picture ?? null)}
      />
    {:else if profile}
      <span aria-hidden="true">{initials}</span>
    {:else}
      <UserRound size={20} aria-hidden="true" />
    {/if}
  </DropdownMenu.Trigger>
  <DropdownMenu.Portal>
    <DropdownMenu.Content
      align="end"
      sideOffset={8}
      collisionPadding={12}
      aria-label="Account"
      class="z-50 w-64 max-w-[calc(100vw-1.5rem)] rounded-2xl border border-[#4075a6]/20 bg-white p-2 text-sm text-[#405c73] shadow-lg outline-none"
      onCloseAutoFocus={(event) => {
        event.preventDefault();
        trigger?.focus();
      }}
      onkeydown={stopKeyboardPropagation}
    >
      <DropdownMenu.Group>
        <DropdownMenu.GroupHeading class="px-3 py-2 font-semibold break-words">
          {profile ? displayName : "Guest"}
        </DropdownMenu.GroupHeading>
        {#if profile?.email}
          <p class="px-3 pb-2 text-xs break-words text-[#405c73]">
            {profile.email}
          </p>
        {/if}
        <DropdownMenu.Separator class="my-1 h-px bg-[#4075a6]/15" />
        <DropdownMenu.Item
          class="flex min-h-11 cursor-pointer items-center rounded-xl px-3 outline-none data-highlighted:bg-[#4075a6]/10"
          onkeydown={(event) => {
            if (event.key === "Enter" || event.key === " ")
              event.stopPropagation();
          }}
          onSelect={profile ? onSignOut : onSignIn}
        >
          {profile ? "Sign out" : "Sign in"}
        </DropdownMenu.Item>
      </DropdownMenu.Group>
    </DropdownMenu.Content>
  </DropdownMenu.Portal>
</DropdownMenu.Root>
