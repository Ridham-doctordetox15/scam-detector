# Screenshots

- `before/` and `after/`: the Phase 10 visual redesign, captured on 2026-10-01 by the same script against
  production builds. Desktop shots are 1440 px wide; mobile shots are 360 px wide at 2x. Animations were reduced
  (`prefers-reduced-motion`) so each shot shows the final state.
  - `analyze_demo_*`, `about_*`, `result_*`, `analyze_hindi_*`, `result_hindi_*`: the demo-only build (no API URL),
    showing the real responses recorded on 2026-09-30.
  - `analyze_live_empty_*`, `loading_*`, `error_rate_limited_*`, `feedback_201`, `feedback_404` and
    `demo_unreachable`: a build pointed at a local API address, with the API **stubbed in the browser**. It
    returned the recorded real responses and documented error bodies, so no LLM calls were made. The
    rate-limit error uses `Retry-After: 37`.
  - Result levels: `result_low_*` = "lunch" sample, `result_medium_*` = OTP-call sample, `result_high_*` = KYC
    link sample.
- `web_*.png` (top level): the Phase 10 walkthrough screenshots of the first design (local API, real Groq).
