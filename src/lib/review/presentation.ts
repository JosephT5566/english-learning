import type { components } from "$lib/api/generated";
import type { DueCard, ReviewDecision } from "$lib/api/contracts";

export type StudyCard = Readonly<
  Pick<
    DueCard,
    | "id"
    | "term"
    | "meaning"
    | "pronunciation"
    | "reading"
    | "romanization"
    | "part_of_speech"
    | "part_of_speech_detail"
    | "target_language_definition"
    | "example_sentence"
    | "example_translation"
    | "synonyms"
    | "antonyms"
  > & {
    targetLanguage: DueCard["deck"]["target_language"];
    privateContext?: Pick<
      DueCard,
      "learned_on" | "tags" | "note" | "supplementary_note"
    >;
  }
>;

export type CardAnswer = Readonly<{ cardId: string; decision: ReviewDecision }>;

function contentFields(
  card: StudyCardContent,
): Omit<StudyCard, "targetLanguage" | "privateContext"> {
  return {
    id: card.id,
    term: card.term,
    meaning: card.meaning,
    pronunciation: card.pronunciation,
    reading: card.reading,
    romanization: card.romanization,
    part_of_speech: card.part_of_speech,
    part_of_speech_detail: card.part_of_speech_detail,
    target_language_definition: card.target_language_definition,
    example_sentence: card.example_sentence,
    example_translation: card.example_translation,
    synonyms: card.synonyms,
    antonyms: card.antonyms,
  };
}

type StudyCardContent = Omit<StudyCard, "targetLanguage" | "privateContext">;

export function toOwnedStudyCard(card: DueCard): StudyCard {
  return {
    ...contentFields(card),
    targetLanguage: card.deck.target_language,
    privateContext: {
      learned_on: card.learned_on,
      tags: card.tags,
      note: card.note,
      supplementary_note: card.supplementary_note,
    },
  };
}

export function toPublicStudyCard(
  card: components["schemas"]["PublicReviewCard"],
): StudyCard {
  return { ...contentFields(card), targetLanguage: card.target_language };
}
