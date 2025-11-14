/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx,js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "Inter var", "system-ui", "sans-serif"],
      },
      colors: {
        brand: {
          accent: "#38bdf8",
          warn: "#f97316",
          critical: "#ef4444",
        },
      },
      boxShadow: {
        card: "0 25px 65px -28px rgba(15,23,42,0.7)",
      },
      backgroundImage: {
        mesh: "radial-gradient(100% 100% at 20% 0%, rgba(56,189,248,0.2) 0%, rgba(15,23,42,0) 60%), radial-gradient(80% 100% at 80% 10%, rgba(249,115,22,0.18) 0%, rgba(15,23,42,0) 65%)",
      },
    },
  },
  plugins: [],
};

