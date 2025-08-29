export type ReviewStage = 1|2|3|4|5;

export interface WordItem {
  id: string;
  lessonDate: string; // ISO
  content: string;
  type: string; // vocabulary, phrase, ...
  phonics?: string; // 音標
  chineseExplain: string;
  engExplain?: string;
  tags?: string;      // 逗號分隔；要改成 string[] 也可
  supplementary?: string;
  status?: string; // active, deleted
  example?: string;
  synonyms?: string;  // 逗號分隔；要改成 string[] 也可
  antonyms?: string;
  note?: string;
  reviewStage: ReviewStage;
  easeFactor: number; // 1.3 ~ 2.5
  intervalDays: number; // 間隔天數
  lastReview?: string;  // ISO
  nextReview?: string;  // ISO
  createdDate?: string; // ISO
}

export interface WordListResponse { ok: true; result: WordItem[]; }
