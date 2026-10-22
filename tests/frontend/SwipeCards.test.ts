import { fireEvent, render, screen, waitFor } from "@testing-library/svelte";
import { describe, expect, it, vi } from "vitest";

import SwipeCards from "$lib/components/SwipeCards.svelte";
import type { DueCard } from "$lib/api/contracts";
import {
  toOwnedStudyCard,
  toPublicStudyCard,
  type StudyCard,
} from "$lib/review/presentation";

const card: DueCard = {
  id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  deck: {
    id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    title: "English",
    target_language: "en",
    explanation_language: "zh-TW",
    archived_at: null,
  },
  term: "resilient",
  meaning: "有復原力的",
  reading: null,
  pronunciation: "/rɪˈzɪliənt/",
  romanization: null,
  part_of_speech: "adjective",
  archived_at: null,
  version: 1,
  updated_at: "2026-09-10T00:00:00Z",
  target_language_definition: "able to recover quickly",
  example_sentence: "The service is resilient to retries.",
  example_translation: null,
  example_source: null,
  synonyms: ["robust"],
  antonyms: ["fragile"],
  part_of_speech_detail: null,
  note: null,
  supplementary_note: null,
  learned_on: "2026-09-01",
  created_at: "2026-09-01T00:00:00Z",
  tags: [
    { id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc", display_name: "backend" },
  ],
  review_state: {
    review_stage: 1,
    ease_factor: "2.50",
    interval_days: 0,
    last_reviewed_at: null,
    next_review_at: "2026-09-10T00:00:00Z",
    version: 7,
  },
};

describe("SwipeCards", () => {
  it("displays a preserved legacy part-of-speech label instead of canonical other", () => {
    const importedCard: DueCard = {
      ...card,
      part_of_speech: "other",
      part_of_speech_detail: "vocabulary",
      note: "informal",
    };

    render(SwipeCards, {
      props: { wordList: [toOwnedStudyCard(importedCard)] },
    });

    expect(screen.getByText("vocabulary", { exact: true })).toBeInTheDocument();
    expect(
      screen.queryByText("other", { exact: true }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("informal", { exact: true })).toBeInTheDocument();
  });

  it("requires a flip before answering and emits only content-level answer fields", async () => {
    const onAnswer = vi.fn();
    const { container } = render(SwipeCards, {
      props: { wordList: [toOwnedStudyCard(card)], onAnswer },
    });
    const yes = screen.getByRole("button", { name: "Knew it" });

    expect(yes).toBeDisabled();
    await fireEvent.click(container.querySelector(".swipe--card")!);
    expect(yes).toBeEnabled();
    await fireEvent.click(yes);

    await waitFor(() =>
      expect(onAnswer).toHaveBeenCalledWith({
        cardId: card.id,
        decision: "yes",
      }),
    );
    expect(
      screen.getByText("You have reviewed all cards."),
    ).toBeInTheDocument();
  });

  it("supports a complete keyboard review path with explicit guidance", async () => {
    const onAnswer = vi.fn();
    render(SwipeCards, {
      props: { wordList: [toOwnedStudyCard(card)], onAnswer },
    });
    const reviewCard = screen.getByRole("button", {
      name: `Question card for ${card.term}`,
    });

    expect(
      screen.getByText("Flip the card to reveal the answer."),
    ).toBeInTheDocument();
    reviewCard.focus();
    await fireEvent.keyDown(reviewCard, { key: "Enter" });
    expect(
      screen.getByText("Choose how well you remembered it."),
    ).toBeInTheDocument();

    await fireEvent.keyDown(reviewCard, { key: "2" });
    await waitFor(() =>
      expect(onAnswer).toHaveBeenCalledWith({
        cardId: card.id,
        decision: "no_a_bit",
      }),
    );
  });
});

const publicContent: StudyCard = {
  id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
  targetLanguage: "ja",
  term: "続く",
  meaning: "continue",
  pronunciation: null,
  reading: "つづく",
  romanization: "tsuzuku",
  part_of_speech: "verb",
  part_of_speech_detail: null,
  target_language_definition: "to continue",
  example_sentence: "雨が続く。",
  example_translation: "The rain continues.",
  synonyms: [],
  antonyms: [],
};

describe("content-only review", () => {
  it.each([
    { key: "1", decision: "no" },
    { key: "2", decision: "no_a_bit" },
    { key: "3", decision: "yes_a_bit" },
    { key: "4", decision: "yes" },
  ])(
    "grades a public card with shortcut $key after flipping",
    async ({ key, decision }) => {
      const onAnswer = vi.fn();
      const onComplete = vi.fn();
      render(SwipeCards, {
        props: { wordList: [publicContent], onAnswer, onComplete },
      });
      const reviewCard = screen.getByRole("button", {
        name: "Question card for 続く",
      });
      expect(screen.getByText("つづく")).toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: "Open supplementary info" }),
      ).not.toBeInTheDocument();
      await fireEvent.keyDown(reviewCard, { key });
      expect(onAnswer).not.toHaveBeenCalled();
      expect(onComplete).not.toHaveBeenCalled();
      await fireEvent.keyDown(reviewCard, { key: " " });
      await fireEvent.keyDown(reviewCard, { key });
      expect(onAnswer).toHaveBeenCalledExactlyOnceWith({
        cardId: publicContent.id,
        decision,
      });
      expect(onComplete).toHaveBeenCalledTimes(1);
      await fireEvent.keyDown(reviewCard, { key });
      expect(onAnswer).toHaveBeenCalledTimes(1);
      expect(onComplete).toHaveBeenCalledTimes(1);
    },
  );

  it("completes without an answer callback and starts a fresh cycle on remount", async () => {
    const onComplete = vi.fn();
    for (let batch = 0; batch < 2; batch += 1) {
      const { unmount } = render(SwipeCards, {
        props: { wordList: [publicContent], onComplete },
      });
      await fireEvent.click(
        screen.getByRole("button", { name: "Question card for 続く" }),
      );
      const knewIt = screen.getByRole("button", { name: "Knew it" });
      await fireEvent.click(knewIt);
      await fireEvent.click(knewIt);
      expect(onComplete).toHaveBeenCalledTimes(batch + 1);
      expect(
        screen.getByText("You have reviewed all cards."),
      ).toBeInTheDocument();
      unmount();
    }
  });

  it.each([
    { distance: 300, decision: "yes" },
    { distance: -300, decision: "no" },
  ])(
    "requires a flip for a $decision pointer gesture and ignores duplicate release",
    async ({ distance, decision }) => {
      const onAnswer = vi.fn();
      const onComplete = vi.fn();
      render(SwipeCards, {
        props: { wordList: [publicContent], onAnswer, onComplete },
      });
      const reviewCard = screen.getByRole("button", {
        name: "Question card for 続く",
      });
      Object.defineProperties(reviewCard, {
        setPointerCapture: { value: vi.fn() },
        hasPointerCapture: { value: () => true },
        releasePointerCapture: { value: vi.fn() },
      });
      async function pointer(type: string, clientX: number) {
        const event = new MouseEvent(type, {
          bubbles: true,
          clientX,
          clientY: 0,
        });
        Object.defineProperty(event, "pointerId", { value: 1 });
        await fireEvent(reviewCard, event);
      }
      await pointer("pointerdown", 0);
      await pointer("pointermove", distance);
      await pointer("pointerup", distance);
      expect(onAnswer).not.toHaveBeenCalled();
      expect(onComplete).not.toHaveBeenCalled();
      await fireEvent.click(reviewCard);
      await pointer("pointerdown", 0);
      await pointer("pointermove", distance);
      await pointer("pointerup", distance);
      await pointer("pointerup", distance);
      expect(onAnswer).toHaveBeenCalledExactlyOnceWith({
        cardId: publicContent.id,
        decision,
      });
      expect(onComplete).toHaveBeenCalledTimes(1);
    },
  );

  it("does not complete an empty stack", () => {
    const onComplete = vi.fn();
    render(SwipeCards, { props: { wordList: [], onComplete } });
    expect(onComplete).not.toHaveBeenCalled();
  });

  it("completes only after the final card", async () => {
    const onComplete = vi.fn();
    render(SwipeCards, {
      props: {
        wordList: [
          publicContent,
          { ...publicContent, id: card.id, term: "second" },
        ],
        onComplete,
      },
    });
    await fireEvent.click(
      screen.getByRole("button", { name: "Question card for 続く" }),
    );
    await fireEvent.click(screen.getByRole("button", { name: "Knew it" }));
    expect(onComplete).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Question card for second" }),
      ).toBeVisible(),
    );
    await waitFor(
      async () => {
        await fireEvent.click(
          screen.getByRole("button", { name: "Question card for second" }),
        );
        expect(screen.getByRole("button", { name: "Knew it" })).toBeEnabled();
      },
      { timeout: 2000 },
    );
    await fireEvent.click(screen.getByRole("button", { name: "Knew it" }));
    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it("preserves private metadata while excluding command and owner state", () => {
    const study = toOwnedStudyCard({
      ...card,
      note: "informal",
      supplementary_note: "Private explanation",
    });
    expect(study).not.toHaveProperty("review_state");
    expect(study).not.toHaveProperty("deck");
    expect(study).not.toHaveProperty("version");
    expect(study.privateContext).toEqual({
      learned_on: card.learned_on,
      tags: card.tags,
      note: "informal",
      supplementary_note: "Private explanation",
    });
    render(SwipeCards, { props: { wordList: [study] } });
    expect(screen.getByText("backend")).toBeInTheDocument();
    expect(
      screen.getAllByText(
        new Date(card.learned_on!).toLocaleDateString("zh-TW"),
      ),
    ).toHaveLength(2);
    expect(screen.getByText("informal")).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: "Open supplementary info",
        hidden: true,
      }),
    ).toBeInTheDocument();
  });
});

describe("public content adapter", () => {
  it("projects approved content without private fields even when the source contains them", () => {
    const { targetLanguage, ...content } = publicContent;
    const study = toPublicStudyCard({
      ...content,
      target_language: targetLanguage,
      ...card,
    });
    expect(study.targetLanguage).toBe("ja");
    for (const key of [
      "deck",
      "review_state",
      "version",
      "note",
      "privateContext",
      "tags",
      "learned_on",
    ]) {
      expect(study).not.toHaveProperty(key);
    }
  });
});
