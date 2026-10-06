/**
 * Demo mode: real API responses recorded for the samples (scripts/record-demo.mjs).
 *
 * Demo mode must never pretend to analyze new input. The only way to get a result here is by
 * sample id, and the id must have a recorded response - there is no code path that takes
 * user-typed text or an uploaded file.
 */
import recorded from "@/demo/recorded.json";
import type { AnalyzeResponse } from "./types";

export interface DemoRecording {
  recorded_at: string;
  note: string;
  responses: Record<string, AnalyzeResponse>;
}

export const DEMO: DemoRecording = recorded as DemoRecording;

export class DemoUnavailableError extends Error {
  constructor(sampleId: string) {
    super(`No recorded demo response for sample "${sampleId}"`);
    this.name = "DemoUnavailableError";
  }
}

/** The recorded response for a sample. Throws for anything that is not a recorded sample. */
export function getDemoResponse(sampleId: string, demo: DemoRecording = DEMO): AnalyzeResponse {
  const response = Object.prototype.hasOwnProperty.call(demo.responses, sampleId)
    ? demo.responses[sampleId]
    : undefined;
  if (!response) throw new DemoUnavailableError(sampleId);
  return response;
}

export const hasDemoResponse = (sampleId: string, demo: DemoRecording = DEMO): boolean =>
  Object.prototype.hasOwnProperty.call(demo.responses, sampleId);

/** yyyy-mm-dd part of the recording timestamp, for the banner. */
export const demoRecordedDate = (demo: DemoRecording = DEMO): string => demo.recorded_at.slice(0, 10);
