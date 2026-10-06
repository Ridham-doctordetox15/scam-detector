/// Client-side limits and timeouts. They mirror web/src/lib/config.ts and the API's own
/// limits; the API still enforces its own.
library;

const int maxTextChars = 5000;
const int maxImageBytes = 5 * 1024 * 1024;

const Duration healthTimeout = Duration(seconds: 4);
const Duration textTimeout = Duration(seconds: 30);
const Duration imageTimeout = Duration(seconds: 60);
const Duration feedbackTimeout = Duration(seconds: 10);
