import { fireEvent, render, screen } from "@testing-library/svelte";
import { describe, expect, it, vi } from "vitest";
import AssistantClarification from "$lib/components/AssistantClarification.svelte";
import type { ClarificationQuestion } from "$lib/api/client";
import {
  clarificationAnswerFor,
  latestUnansweredClarification,
  makeClarificationAnswer,
  type HistoryTurn,
} from "$lib/assistant/history";

const question: ClarificationQuestion = {
  question_id: "q1",
  question: "Which meaning of bank?",
  purpose: "term",
  allow_free_text: true,
  options: [
    "Financial institution",
    "River bank",
    "A row",
    "Deposit money",
  ].map((label, index) => ({ id: `o${index}`, label })),
};

describe("clarification card", () => {
  it("offers four native tap-to-send buttons and both optional text controls", async () => {
    const onanswer = vi.fn();
    render(AssistantClarification, { question, onanswer });
    const chips = screen.getAllByRole("button", { pressed: false });
    expect(chips).toHaveLength(4);
    expect(chips.every((chip) => chip.tagName === "BUTTON")).toBe(true);
    await fireEvent.click(screen.getByRole("button", { name: "River bank" }));
    expect(onanswer).toHaveBeenCalledWith({ optionId: "o1" });
    const submit = screen.getByRole("button", { name: "Send description" });
    expect(submit).toBeDisabled();
    await fireEvent.click(submit);
    expect(onanswer).toHaveBeenCalledTimes(1);
    await fireEvent.input(screen.getByLabelText("Or describe it yourself"), {
      target: { value: "   " },
    });
    expect(submit).toBeDisabled();
    await fireEvent.input(screen.getByLabelText("Or describe it yourself"), {
      target: { value: " River edge " },
    });
    await fireEvent.click(submit);
    expect(onanswer).toHaveBeenLastCalledWith({ text: "River edge" });
    for (const button of screen.getAllByRole("button")) {
      expect(button.className).not.toMatch(/confirm|orange/);
      expect(button.getAttribute("style") ?? "").not.toContain("#ff3e00");
    }
  });

  it("hides free text when forbidden and disables all sends while guarded", async () => {
    const onanswer = vi.fn();
    render(AssistantClarification, {
      question: { ...question, allow_free_text: false },
      disabled: true,
      onanswer,
    });
    expect(
      screen.queryByLabelText("Or describe it yourself"),
    ).not.toBeInTheDocument();
    for (const chip of screen.getAllByRole("button")) {
      expect(chip).toBeDisabled();
      await fireEvent.click(chip);
    }
    expect(onanswer).not.toHaveBeenCalled();
  });

  it("single-selects listed decks without sending until the labelled confirm", async () => {
    const onanswer = vi.fn();
    render(AssistantClarification, {
      question: {
        ...question,
        purpose: "deck",
        allow_free_text: false,
        options: Array.from({ length: 20 }, (_, index) => ({
          id: `d${index}`,
          label: `Deck ${index}`,
          deck_id: `deck-${index}`,
        })),
      },
      onanswer,
    });
    expect(
      screen.getByRole("radiogroup", { name: question.question }),
    ).toHaveClass("deck-list");
    expect(screen.getAllByRole("radio")).toHaveLength(20);
    const confirm = screen.getByRole("button", { name: "Use this deck" });
    expect(confirm).toBeDisabled();
    await fireEvent.click(screen.getByRole("radio", { name: "Deck 2" }));
    await fireEvent.click(screen.getByRole("radio", { name: "Deck 12" }));
    expect(screen.getByRole("radio", { name: "Deck 2" })).not.toBeChecked();
    expect(screen.getByRole("radio", { name: "Deck 12" })).toBeChecked();
    expect(onanswer).not.toHaveBeenCalled();
    await fireEvent.click(confirm);
    expect(onanswer).toHaveBeenCalledWith({ optionId: "d12" });
  });

  it("renders an empty deck question without an empty confirm", () => {
    render(AssistantClarification, {
      question: {
        ...question,
        purpose: "deck",
        options: [],
        allow_free_text: false,
      },
      onanswer: vi.fn(),
    });
    expect(
      screen.getByRole("heading", { name: question.question }),
    ).toBeVisible();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it.each(["chip", "text", "deck"])(
    "restores a locked %s answer from the same in-memory turns on remount",
    async (kind) => {
      const q =
        kind === "deck"
          ? {
              ...question,
              purpose: "deck" as const,
              allow_free_text: false,
              options: [
                { id: "o1", label: "Travel English", deck_id: "deck-1" },
              ],
            }
          : question;
      const answer = makeClarificationAnswer(
        q,
        kind === "text" ? { text: "River edge" } : { optionId: "o1" },
      );
      const turns: HistoryTurn[] = [
        {
          question: "Add bank",
          reply: "Please choose",
          complete: true,
          cardIds: [],
          clarificationQuestions: [q],
        },
        {
          question: "Chosen label",
          reply: "Next reply",
          complete: true,
          cardIds: [],
          clarificationAnswer: answer,
        },
      ];
      expect(latestUnansweredClarification(turns)).toBeUndefined();
      const onanswer = vi.fn();
      const mount = () =>
        render(AssistantClarification, {
          question: q,
          answer: clarificationAnswerFor(turns, q),
          onanswer,
        });
      const first = mount();
      first.unmount();
      mount();
      expect(
        screen.getByText(
          `Answered: ${kind === "text" ? "River edge" : kind === "deck" ? "Travel English" : "River bank"}`,
        ),
      ).toHaveAttribute("aria-live", "polite");
      for (const control of [
        ...screen.getAllByRole("button"),
        ...screen.queryAllByRole("textbox"),
        ...screen.queryAllByRole("radio"),
      ]) {
        expect(control).toBeDisabled();
        await fireEvent.click(control);
      }
      if (kind === "chip")
        expect(
          screen.getByRole("button", { name: "River bank" }),
        ).toHaveAttribute("aria-pressed", "true");
      if (kind === "deck") expect(screen.getByRole("radio")).toBeChecked();
      expect(onanswer).not.toHaveBeenCalled();
    },
  );
});
