export interface GeneratedQuestion {
  /** 원본 문제 (참고용 — 다운로드 PDF에는 포함하지 않습니다). */
  original: string;
  /** AI가 새로 생성한 동형 문제. */
  generated: string;
  /** 생성된 문제의 정답. */
  answer: string;
}

export interface GenerateResponse {
  questions: GeneratedQuestion[];
  /** 입력이 너무 길어 일부만 사용한 경우 사용자에게 안내하기 위한 메시지. */
  notice?: string;
}

export interface GenerateRequest {
  /** PDF에서 추출한 전체 텍스트. */
  text: string;
}

export type Status =
  | "idle"
  | "extracting"
  | "generating"
  | "done"
  | "error";
