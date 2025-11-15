import palette from "../../theme/palette.json";

export const BRAND_COLORS = {
  base: palette.base,
  surface: palette.surface,
  surfaceAlt: palette.surfaceAlt,
  accent: palette.accent,
  hsy: palette.hsy,
  valmet: palette.valmet,
  valmetGlow: palette.valmetGlow,
  warn: palette.warn,
  critical: palette.critical,
  gridStrong: palette.gridStrong,
  gridMuted: palette.gridMuted,
  textMuted: palette.textMuted,
} as const;

export type BrandColorName = keyof typeof BRAND_COLORS;

const hexToRgba = (hex: string): { r: number; g: number; b: number } => {
  const normalized = hex.replace("#", "");
  const value =
    normalized.length === 3
      ? normalized
          .split("")
          .map((char) => `${char}${char}`)
          .join("")
      : normalized;
  const r = parseInt(value.slice(0, 2), 16);
  const g = parseInt(value.slice(2, 4), 16);
  const b = parseInt(value.slice(4, 6), 16);
  return { r, g, b };
};

export const withOpacity = (hex: string, alpha: number): string => {
  const { r, g, b } = hexToRgba(hex);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
};

export const brandColorWithOpacity = (
  name: BrandColorName,
  alpha: number
): string => withOpacity(BRAND_COLORS[name], alpha);
