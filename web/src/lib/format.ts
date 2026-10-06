/** Replace `{name}` placeholders in an interface string. Unknown placeholders are left as-is. */
export function fmt(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (match, key: string) =>
    Object.prototype.hasOwnProperty.call(values, key) ? String(values[key]) : match,
  );
}

/**
 * Length the way the API counts it (Python `len`: Unicode code points), not UTF-16 units, so
 * emoji and other astral characters are not double-counted against the 5000 limit.
 */
export const charCount = (text: string): number => Array.from(text).length;
