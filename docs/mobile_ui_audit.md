# Android app UI audit and redesign proposal (Phase 11b, step 1)

Status: **proposal, waiting for approval.** No app code has been changed.

Evidence: 133 screenshots of the current debug build on the owner's phone (OPPO CPH2269, Android 11,
360 x 800 dp), English and Hindi, light and dark, indexed in
[screenshots/mobile/before/README.md](screenshots/mobile/before/README.md). Font scales 1.3 and 2.0
could not be set over adb on this phone (ColorOS blocks `settings put`), so they were checked with a
throwaway widget-test probe at 360 dp instead (results in section 1, item 13).

## 1. Audit, ranked by impact

| # | Problem | Where | Evidence |
|---|---|---|---|
| 1 | **The gauge prints "Medium" at the top on every result**, including high and low. At a glance, a "Likely scam / High risk" result shows the word "Medium" first. It is the label of the top band, but it sits where the eye lands. | Results | `*-11-result-high-top`, `*-13-result-low-top` |
| 2 | **The answer is not the hero, and the next step is buried.** The gauge takes about 40% of the first screen. The verdict sits below it. "What to do" is the third section, about 1.5 screens down. A scared user has to read the AI explanation before they learn what to do. | Results | `*-11-result-high-*` |
| 3 | **Errors use the high-risk red.** "Please paste a message first" and "Couldn't reach the server" look like a scam warning. That mixes up "the app had a problem" with "this message is dangerous". | Home, Results | `*-04`, `*-15` |
| 4 | **The input error stays after you type.** "Please paste a message first" is still shown after text is entered. The error also appears below the form, away from the button that caused it. | Home | `en-dark-22-home-typed` |
| 5 | **One giant card with grey uppercase labels.** Warning signs, explanation, steps, pattern, links, extracted text and feedback all sit in one card. A high result scrolls about 3 screens and is hard to scan. "RESULT" repeats the app bar title. | Results | `*-09-*`, `*-11-*` |
| 6 | **Loading looks unfinished.** The progress indicator renders as a barely visible 20 px dot. The skeleton is static grey and does not match the result layout. Nothing reassures the user during a slow screenshot check (one real check took 30 s). | Results | `*-08`, `*-10` |
| 7 | **Feedback states are unclear.** After answering, both buttons go grey and disabled, so you can't tell which one you picked. An empty status line reserves a gap, then the layout jumps. The snackbar is unthemed and full-width. There is no haptic. | Results | `*-12`, `en-dark-19` |
| 8 | **Home has no single obvious action.** The hero and three bullets push the form below the fold (in Hindi the field starts about 60% down the screen). "Check message" needs a scroll. Seven tall sample cards (2-3 lines each) dominate the page. | Home | `*-01`, `*-02`, `*-03` |
| 9 | **Default Flutter launcher icon**, with no adaptive or monochrome layers. **White flash on launch in dark mode**: `launch_background.xml` is plain white and the night theme reuses it. | Android | `res/mipmap-*`, `res/drawable*/launch_background.xml` |
| 10 | **No motion at all** apart from the default page transition. The result pops in all at once, the gauge is static, and there's no feedback on button presses beyond ink. The web app already has a settling needle and staggered sections. | All | web `RiskGauge.tsx`, `ResultCard.tsx` |
| 11 | **No shared tokens.** Radii are used ad hoc (8/12/16/99), as is spacing (4, 6, 8, 10, 12, 14, 16, 20, 24, 28, 32). Section headings are uppercase and letter-spaced in English but plain in Hindi, so the two languages look like different apps. Content text (bodyLarge) is larger than interface text. | All | `lib/**` |
| 12 | **Safe results still say "Warning signs"** with a warning triangle above "No specific warning signs found". | Results | `*-13-result-low-top` |
| 13 | **Accessibility gaps (small).** "Result" is announced twice (app bar, then card heading). The gauge is read before the verdict. The selectable defanged link is 42 dp tall (below 48 dp; it only has a long-press action). The probe found **no overflow** at 1.0, 1.3 or 2.0 in English and Hindi at 360 dp, and no contrast or label failures. Real-device check at 1.3 and 2.0 is still to do. | Results | widget-test probe, uiautomator dump |
| 14 | **About is a wall of text** (5 screens). There are no section anchors, and the pipeline is a dense paragraph. | About | `*-16-about-*` |
| 15 | **Small polish issues.** The display options sheet has no title. "हिंदी" sits lower than "EN" in its segment. The OCR "Show the text" area leaves a large empty gap when collapsed. The licences page has no app version. | Various | `*-06`, `*-09-s2` |

Not UI, but worth knowing:
- The **extracted screenshot text shows links un-defanged** (for example `http://sbi-kyc-update.top/verify`). They are not tappable, and the web app does the same. It doesn't break the "not tappable" rule but does break "defanged". Decision for you: defang URLs in that text on mobile (display only)? I recommend yes.
- `<URL>` placeholders still appear in some warning signs and explanations. This is the known Phase 12 backend item and is not touched here.

## 2. Recommended direction: "Calm guardian"

**Feeling:** a steady, kind expert next to you. Neutral surfaces and plenty of space. Colour is used
only to say how risky something is, never for decoration. One answer, then one action, then details
on demand.

**Colour:**
- Keep the web palette exactly (indigo primary `#3B54D6` / `#93A5FF`, the same surfaces and the same risk colours).
- Risk colour appears only in the result hero, the risk chips and the warning-sign markers.
- Errors and problems move to neutral or primary styling: a tinted surface with a primary-coloured icon. Red then always means "risky message".
- Every new pair is added to `theme_contrast_test.dart` (AA in both themes).

**Typography** (Noto Sans / Noto Sans Devanagari as now; one scale, interface and content alike):

| Token | Size / weight | Used for |
|---|---|---|
| display | 30 / 700 | verdict on Results |
| headline | 24 / 700 | screen hero ("Is this message a scam?") |
| title | 18 / 600 | card and section titles |
| body | 16 / 400 | everything readable, including API content |
| label | 14 / 600 | buttons, chips, segment labels |
| caption | 13 / 400 | hints, disclaimers, AI note |

- Latin line height is 1.4 for titles and 1.5 for body.
- Devanagari keeps 1.75 on every style, with no letter spacing anywhere.
- Section titles become sentence case in both languages, which removes the uppercase/letter-spacing split.

**Spacing:** a 4 dp grid with named steps xs 4, sm 8, md 12, lg 16, xl 24, xxl 32. The page gutter is
16 dp (as now), with 24 dp between cards.

**Shapes** (aligned with the web `--radius: 12px` scale):

| Token | Radius | Used for |
|---|---|---|
| sm | 8 dp | chips, inner panels |
| md | 12 dp | inputs, panels, link boxes |
| lg | 16 dp | cards |
| xl | 28 dp | result hero, bottom sheet |
| pill | — | buttons and segments |

Cards stay flat, with a 1 px outline and no shadows.

**Motion** (built-in Flutter only; curve `Cubic(0.22, 1, 0.36, 1)`, the web's easing):
- **Durations:** short 150 ms (presses, chips), medium 250 ms (cross-fades, expand), long 400 ms (hero entrance).
- **Screen transitions:** Material shared-axis style (fade and slide forward) via `PageTransitionsTheme`.
- **Gauge:** the needle settles into its band with one gentle spring (about 700 ms) and the active band brightens. It never points at an in-between position or passes a value on the way: it starts from the left edge of the gauge with the bands dimmed, so nothing reads as a score.
- **Result content:** the hero first, then the cards in order (60 ms stagger, fade plus 8 dp rise), like the web.
- **Buttons:** a press scale of 0.98. The feedback choice morphs to a filled state with a check mark.
- **Loading:** a soft shimmer over a skeleton shaped like the real result. For screenshots, a reassuring second line appears after about 8 s.
- **Reduced motion:** when `MediaQuery.disableAnimations` is on (Android "Remove animations"), every duration becomes zero. The needle is drawn in place and the shimmer becomes static. One `Motion` helper reads this, so no widget decides on its own.

**Haptics:** `HapticFeedback.mediumImpact` when a result arrives (heavy for high risk, light for low).
`selectionClick` on feedback sent, and on choosing a mode or language. Nothing on scroll.

**Results screen layout (the hero):**
1. **Hero panel** (full width, risk-tinted, 28 dp radius):
   - a compact gauge (about 160 dp wide, its three band labels below the arc, never above it);
   - the verdict in display size with the risk icon, and the risk level beneath;
   - straight below, a **"Do this first"** box holding the first `what_to_do` step, in high-contrast text on the surface colour.
2. **Warning signs** card (count in the title, coloured markers) and **What to do** (remaining steps).
3. **Why** card (explanation plus the AI-written note).
4. **Details**, as separate compact cards: closest known pattern, links (defanged, not tappable, collapsible checks), text read from the screenshot (collapsed).
5. Feedback card, then a sticky bottom bar with **Check another message** (always reachable). The disclaimer moves under the hero as a single caption line.

TalkBack order: verdict and risk level (one live-region announcement), then "Do this first", then
the gauge image ("Risk level: High"), then the cards in order. The duplicate "Result" heading is
removed.

**Home:**
- A shorter hero: the title plus one line. The three trust points move into a compact row of chips below the form.
- The form card comes first, with the text/screenshot segment, a larger input and a full-width primary button that is visible without scrolling at 1.0×.
- Input errors appear inline under the field (helper text style, neutral colour) and clear as soon as you type or switch mode.
- Samples become a tighter list: one line of title plus an "expected: scam/safe" tag, with each item a 56 dp row.
- The server banner becomes a slim, dismissible strip.

**Empty, loading and error states:** a shared `StatusPanel` (tinted icon circle, title, body, primary
action) for the empty screenshot picker, server unreachable, network error, rate-limited and
unsupported image. Rate-limited shows a countdown in the button text where `retryAfterS` is known.
That uses the existing error-message strings.

**App icon** (original, drawn as Android vector XML; no stock art):
- **Foreground:** a white rounded speech bubble with an indigo check-shield cut into it.
- **Background:** solid indigo `#3B54D6`.
- **Monochrome:** the same bubble-shield silhouette.

It sits inside the 66 dp safe zone, so it survives circle, squircle and teardrop masks. A legacy PNG
set is generated from the same vector for older launchers.

**Launch screen:**
- `launch_background` becomes `#FAFAFA` (light) / `#0B0D10` (dark) with the centred icon, with a `values-night` drawable.
- `NormalTheme` uses the same colours, so there is no white flash.
- Android 12+ gets `windowSplashScreenBackground` and an icon via `values-v31`.

## 3. Alternatives considered

- **B. "Traffic light":** the whole Results screen floods with the risk colour, with a huge icon and verdict and no gauge. It is the clearest possible signal. But it is alarming for "Looks safe", hard to keep AA on saturated backgrounds in dark mode, loses the gauge parity with the web app, and feels heavy for a calm product.
- **C. "Editorial":** text-first, almost no colour. The verdict is a big headline with a thin three-segment band bar, and sections are separated by dividers instead of cards. It is very compact and excellent at 2.0× text. But it is less glanceable for someone panicking and less "app-like", and the bar drifts from the web gauge.

**Recommendation: A, "Calm guardian".** It keeps the web app's look and gauge, puts one clear answer
and one action first, and uses colour only where it carries meaning. Its card structure also gives
TalkBack a clean reading order.

## 4. Packages

**None proposed.** Everything above uses Flutter's built-in widgets and animation APIs
(`AnimationController`, `TweenAnimationBuilder`, `PageTransitionsTheme`, `HapticFeedback`,
`MediaQuery.disableAnimations`) and plain Android resources for the icon and splash.

`flutter_launcher_icons` (MIT) and `flutter_native_splash` (MIT) would only generate the same resource
files. They are not needed, and adding them would add build-time dependencies for a one-off job. If
you prefer generated PNGs over hand-written vector XML, I would ask before adding
`flutter_launcher_icons` as a dev dependency.

## 5. New interface strings (drafts, for your review)

App-only strings go into `lib/i18n/mobile_strings.dart`, like the existing 21. The web app has no
equivalent of these.

| Key | English | Hindi draft |
|---|---|---|
| `mobile.firstStep` | Do this first | सबसे पहले यह करें |
| `mobile.detailsHeading` | More details | और जानकारी |
| `mobile.stillWorking` | Still working. Screenshots can take up to 30 seconds. | अभी जाँच चल रही है। स्क्रीनशॉट में 30 सेकंड तक लग सकते हैं। |
| `mobile.noWarningSignsTitle` | No warning signs | कोई चेतावनी संकेत नहीं |
| `mobile.displayOptionsTitle` | Display options | दिखावट के विकल्प |
| `mobile.retryIn` | Try again in {s} s | {s} सेकंड में फिर कोशिश करें |

The final list may shrink while building. Every string will be listed again in the step 2 report.

## 6. Baseline numbers (before)

- Release APK (universal, all ABIs, R8 on; built with the debug key **for measurement only**, then deleted together with the temporary `key.properties`): **54,170,182 bytes (51.7 MB)**.
- Widget-test probe at 360 dp, English and Hindi, text scale 1.0 / 1.3 / 2.0, on Home, Results, About and an error: **0 overflows**; contrast and label guidelines pass. 1 tap-target failure: the defanged link, 260 x 42 dp, at 1.0.
- Tests: 103 pass (Phase 11 figure; not re-run in this step).
