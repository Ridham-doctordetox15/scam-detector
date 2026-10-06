/** Mirrors api/schemas.py. No probability or numeric score exists in any of these on purpose. */

export type Verdict = "safe" | "suspicious" | "scam";
export type RiskLevel = "low" | "medium" | "high";
export type ContentLanguage = "en" | "hi" | "hinglish";
export type ExplainerPath = "groq" | "gemini" | "template";

export interface URLFinding {
  url_defanged: string;
  risk_band: RiskLevel;
  reasons: string[];
}

export interface OCRInfo {
  extracted_text: string;
  quality: "good" | "fair" | "poor";
  dark_mode: boolean;
}

export interface AnalyzeResponse {
  prediction_id: string;
  input_type: "text" | "image";
  verdict: Verdict;
  risk_level: RiskLevel;
  red_flags: string[];
  explanation: string;
  what_to_do: string[];
  matched_pattern: string | null;
  url_findings: URLFinding[];
  explainer_path: ExplainerPath;
  language: ContentLanguage;
  classifier_model: string;
  timings_ms: Record<string, number>;
  ocr: OCRInfo | null;
  disclaimer: string;
}

export interface HealthResponse {
  status: "ok" | "degraded" | "unavailable";
  components: Record<string, { ready: boolean; detail: string }>;
}

export type UserVerdict = "correct" | "incorrect";
