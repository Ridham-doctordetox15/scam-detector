import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  try {
    window.localStorage.clear();
  } catch {
    /* storage unavailable in some environments */
  }
});

// --- Browser APIs jsdom lacks (used by Radix UI, Motion, next-themes and Sonner) ---

// jsdom has no object URLs; the image preview uses them.
if (!("createObjectURL" in URL)) {
  Object.assign(URL, { createObjectURL: () => "blob:preview", revokeObjectURL: () => undefined });
}

// matchMedia: report "no preference" for everything (light theme, motion allowed).
if (!window.matchMedia) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }),
  });
}

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
if (!("ResizeObserver" in window)) Object.assign(window, { ResizeObserver: ResizeObserverStub });
if (!("IntersectionObserver" in window)) {
  Object.assign(window, {
    IntersectionObserver: class {
      observe() {}
      unobserve() {}
      disconnect() {}
      takeRecords() {
        return [];
      }
    },
  });
}

// Pointer capture and scrollIntoView (Radix toggle/tabs/tooltip interactions).
const proto = window.HTMLElement.prototype as unknown as Record<string, unknown>;
proto.hasPointerCapture ??= () => false;
proto.setPointerCapture ??= () => undefined;
proto.releasePointerCapture ??= () => undefined;
proto.scrollIntoView ??= () => undefined;
