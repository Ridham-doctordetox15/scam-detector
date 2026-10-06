# Real screenshots (manual OCR check)

Everything in this folder except this README is gitignored. Never commit real screenshots.

1. Take 3-5 screenshots on your phone of real SMS/WhatsApp messages: a mix of scam and safe ones.
2. **Before copying them here, crop or blur any personal details**: your name and number, contact
   names and photos, OTPs, account numbers, addresses. The scam sender's text and links can stay.
3. Name each file `scam_<something>.png` or `safe_<something>.png` (PNG, JPEG or WebP, up to 5 MB).
   The prefix is your own label, and the summary shows it next to the verdict.
4. Run:

   ```
   python -m src.ocr.check_real_screenshots
   ```

   The OCR text is printed to your terminal only. It is not logged, saved or sent to any API
   (add `--llm` if you also want the Groq/Gemini explanation). The final summary table contains no
   message text, so it can be pasted into `results.md`.
