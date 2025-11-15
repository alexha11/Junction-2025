import palette from "./theme/palette.json" assert { type: "json" };

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx,js,jsx}"],
  safelist: ["bg-brand-base"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "Inter var", "system-ui", "sans-serif"],
      },
      colors: {
        brand: {
          base: palette.base,
          surface: palette.surface,
          "surface-alt": palette.surfaceAlt,
          accent: palette.accent,
          hsy: palette.hsy,
          valmet: palette.valmet,
          "valmet-glow": palette.valmetGlow,
          warn: palette.warn,
          critical: palette.critical,
          "grid-strong": palette.gridStrong,
          "grid-muted": palette.gridMuted,
          "text-muted": palette.textMuted,
        },
      },
      boxShadow: {
        card: "0 25px 65px -28px rgba(15,23,42,0.7)",
      },
      backgroundImage: {
        mesh: "radial-gradient(100% 100% at 18% 0%, rgba(0,180,157,0.2) 0%, rgba(4,25,20,0) 60%), radial-gradient(85% 90% at 85% 10%, rgba(90,185,70,0.22) 0%, rgba(4,25,20,0) 65%)",
      },
    },
  },
  plugins: [],
};
