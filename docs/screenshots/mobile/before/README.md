# Mobile app screenshots: before Phase 11b

Debug build on the owner's phone (OPPO CPH2269, Android 11, 360 x 800 dp, font scale 1.0), captured with adb on 2026-10-03
against the local API. One file per scroll position: `-top`, then `-s1`, `-s2`, ... down the page.

Sets: `en-dark`, `en-light`, `hi-light`, `hi-dark` (interface language and theme). States 17+ were captured in `en-dark` only.
The test screenshot is a generated fake bank SMS (its `OTP` shows as boxes because the image font had no Latin glyphs).

| # | State | en-dark | en-light | hi-light | hi-dark |
|---|---|---|---|---|---|
| 01 | Home, top (hero + start of form) | [1](en-dark-01-home-top.png) | [1](en-light-01-home-top.png) | [1](hi-light-01-home-top.png) | [1](hi-dark-01-home-top.png) |
| 02 | Home, input form | [1](en-dark-02-home-form.png) | [1](en-light-02-home-form.png) | [1](hi-light-02-home-form.png) | [1](hi-dark-02-home-form.png) |
| 03 | Home, sample list | [1](en-dark-03-home-samples.png) | [1](en-light-03-home-samples.png) | [1](hi-light-03-home-samples.png) | [1](hi-dark-03-home-samples.png) |
| 04 | Home, 'Check' pressed with no text (input error) | [1](en-dark-04-home-empty-error.png) | [1](en-light-04-home-empty-error.png) | [1](hi-light-04-home-empty-error.png) | [1](hi-dark-04-home-empty-error.png) |
| 05 | Home, Screenshot mode, nothing picked | [1](en-dark-05-home-image-mode.png) | [1](en-light-05-home-image-mode.png) | [1](hi-light-05-home-image-mode.png) | [1](hi-dark-05-home-image-mode.png) |
| 06 | Display options sheet (language, theme) | [1](en-dark-06-display-options.png) | [1](en-light-06-display-options.png) | [1](hi-light-06-display-options.png) | [1](hi-dark-06-display-options.png) |
| 07 | Home, test screenshot picked | [1](en-dark-07-home-image-picked.png) | [1](en-light-07-home-image-picked.png) | [1](hi-light-07-home-image-picked.png) | [1](hi-dark-07-home-image-picked.png) |
| 08 | Results, loading (screenshot) | [1](en-dark-08-loading-image.png) | [1](en-light-08-loading-image.png) | [1](hi-light-08-loading-image.png) | [1](hi-dark-08-loading-image.png) |
| 09 | Results, screenshot result (high risk, extracted text) | [1](en-dark-09-result-image-top.png) [2](en-dark-09-result-image-s1.png) [3](en-dark-09-result-image-s2.png) | [1](en-light-09-result-image-top.png) [2](en-light-09-result-image-s1.png) [3](en-light-09-result-image-s2.png) [4](en-light-09-result-image-s3.png) [5](en-light-09-result-image-s4.png) | [1](hi-light-09-result-image-top.png) [2](hi-light-09-result-image-s1.png) [3](hi-light-09-result-image-s2.png) [4](hi-light-09-result-image-s3.png) | [1](hi-dark-09-result-image-top.png) [2](hi-dark-09-result-image-s1.png) [3](hi-dark-09-result-image-s2.png) [4](hi-dark-09-result-image-s3.png) |
| 10 | Results, loading (text) | [1](en-dark-10-loading-text.png) | [1](en-light-10-loading-text.png) | [1](hi-light-10-loading-text.png) | [1](hi-dark-10-loading-text.png) |
| 11 | Results, high risk (sample: fake KYC with link) | [1](en-dark-11-result-high-top.png) [2](en-dark-11-result-high-s1.png) [3](en-dark-11-result-high-s2.png) | [1](en-light-11-result-high-top.png) [2](en-light-11-result-high-s1.png) [3](en-light-11-result-high-s2.png) | [1](hi-light-11-result-high-top.png) [2](hi-light-11-result-high-s1.png) [3](hi-light-11-result-high-s2.png) | [1](hi-dark-11-result-high-top.png) [2](hi-dark-11-result-high-s1.png) [3](hi-dark-11-result-high-s2.png) [4](hi-dark-11-result-high-s3.png) [5](hi-dark-11-result-high-s4.png) [6](hi-dark-11-result-high-s5.png) [7](hi-dark-11-result-high-s6.png) |
| 12 | Feedback answered and saved (snackbar) | [1](en-dark-12-feedback-saved.png) | [1](en-light-12-feedback-saved.png) | [1](hi-light-12-feedback-saved.png) | [1](hi-dark-12-feedback-saved.png) |
| 13 | Results, low risk (sample: lunch) | [1](en-dark-13-result-low-top.png) [2](en-dark-13-result-low-s1.png) | [1](en-light-13-result-low-top.png) [2](en-light-13-result-low-s1.png) | [1](hi-light-13-result-low-top.png) [2](hi-light-13-result-low-s1.png) | [1](hi-dark-13-result-low-top.png) [2](hi-dark-13-result-low-s1.png) |
| 14 | Results, medium risk (typed text with a shortened link) | [1](en-dark-14-result-medium-top.png) [2](en-dark-14-result-medium-s1.png) [3](en-dark-14-result-medium-s2.png) | [1](en-light-14-result-medium-top.png) [2](en-light-14-result-medium-s1.png) [3](en-light-14-result-medium-s2.png) | [1](hi-light-14-result-medium-top.png) [2](hi-light-14-result-medium-s1.png) [3](hi-light-14-result-medium-s2.png) | [1](hi-dark-14-result-medium-top.png) [2](hi-dark-14-result-medium-s1.png) [3](hi-dark-14-result-medium-s2.png) |
| 15 | Results, network error with Try again | [1](en-dark-15-network-error.png) | [1](en-light-15-network-error.png) | [1](hi-light-15-network-error.png) | [1](hi-dark-15-network-error.png) |
| 16 | About / How it works | [1](en-dark-16-about-top.png) [2](en-dark-16-about-s1.png) [3](en-dark-16-about-s2.png) [4](en-dark-16-about-s3.png) [5](en-dark-16-about-s4.png) | [1](en-light-16-about-top.png) [2](en-light-16-about-s1.png) [3](en-light-16-about-s2.png) [4](en-light-16-about-s3.png) [5](en-light-16-about-s4.png) | [1](hi-light-16-about-top.png) [2](hi-light-16-about-s1.png) [3](hi-light-16-about-s2.png) [4](hi-light-16-about-s3.png) [5](hi-light-16-about-s4.png) | [1](hi-dark-16-about-top.png) [2](hi-dark-16-about-s1.png) [3](hi-dark-16-about-s2.png) [4](hi-dark-16-about-s3.png) [5](hi-dark-16-about-s4.png) |
| 17 | Home, picked screenshot, action buttons | [1](en-dark-17-home-image-picked-actions.png) | - | - | - |
| 18 | Screenshot result with link checks and extracted text expanded | [1](en-dark-18-result-image-expanded-top.png) [2](en-dark-18-result-image-expanded-s1.png) | - | - | - |
| 19 | Feedback, sending | [1](en-dark-19-feedback-sending.png) | - | - | - |
| 20 | Results, sample: asks to read out a code | [1](en-dark-20-result-otp-top.png) [2](en-dark-20-result-otp-s1.png) [3](en-dark-20-result-otp-s2.png) | - | - | - |
| 21 | Results, sample: real telecom offer | [1](en-dark-21-result-vi-offer-top.png) [2](en-dark-21-result-vi-offer-s1.png) [3](en-dark-21-result-vi-offer-s2.png) | - | - | - |
| 22 | Home, text typed (stale input error still shown) | [1](en-dark-22-home-typed.png) | - | - | - |
| 23 | Open-source licences page | [1](en-dark-23-licences.png) | - | - | - |
| 24 | Text shared from another app, loading | [1](en-dark-24-share-loading.png) | - | - | - |
| 25 | Text shared from another app, result | [1](en-dark-25-share-result-top.png) [2](en-dark-25-share-result-s1.png) [3](en-dark-25-share-result-s2.png) | - | - | - |
| 26 | Home, 'can't reach the analysis server' banner | [1](en-dark-26-home-unreachable.png) | - | - | - |
