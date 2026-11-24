// WCAG 2.x relative luminance and contrast ratio, shared by the ground
// contrast test and the team mark's number ink (#592).

/**
 * Relative luminance of a 6-digit hex colour.
 * @param {string} hex e.g. "#1c2230"
 * @returns {number}
 */
export function luminance(hex) {
  const [r, g, b] = hex.slice(1).match(/../g).map((part) => {
    const channel = parseInt(part, 16) / 255;
    return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return r * 0.2126 + g * 0.7152 + b * 0.0722;
}

/**
 * Contrast ratio between two 6-digit hex colours, from 1 to 21.
 * @param {string} first
 * @param {string} second
 * @returns {number}
 */
export function contrast(first, second) {
  const a = luminance(first), b = luminance(second);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}
