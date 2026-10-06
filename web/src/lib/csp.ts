/**
 * Content-Security-Policy for the static site, delivered as a <meta> tag (static hosts can't all
 * set headers). Its job is data exfiltration control: even an injected script can only talk to
 * this site and the one configured API origin.
 *
 * script-src/style-src are deliberately not set: a Next.js static export hydrates through inline
 * scripts and has no per-request nonce, so restricting them would break the page. frame-ancestors
 * is ignored in <meta> tags, so it is not listed either.
 */
export function buildCsp(apiOrigin: string): string {
  const connect = ["'self'", apiOrigin].filter(Boolean).join(" ");
  return [
    `connect-src ${connect}`,
    "object-src 'none'",
    "form-action 'none'",
    "base-uri 'self'",
    "img-src 'self' blob: data:",
    "font-src 'self'",
    "worker-src 'none'",
    "manifest-src 'self'",
  ].join("; ");
}
