import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        bg: {
          DEFAULT: "#0b0f17",
          card: "#111826",
          elevated: "#162033",
          subtle: "#0e1422",
        },
        border: {
          DEFAULT: "#1f2a3d",
          strong: "#2a3950",
        },
        ink: {
          DEFAULT: "#e6edf6",
          muted: "#94a3b8",
          dim: "#64748b",
        },
        brand: {
          DEFAULT: "#3b82f6",
          dim: "#1d4ed8",
        },
        verdict: {
          buy: "#22c55e",
          watch: "#f59e0b",
          avoid: "#ef4444",
          hold: "#3b82f6",
          sell: "#ef4444",
          buymore: "#10b981",
          trim: "#f59e0b",
          stop: "#dc2626",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      boxShadow: {
        card: "0 1px 0 rgba(255,255,255,0.04) inset, 0 1px 2px rgba(0,0,0,0.4)",
      },
    },
  },
  plugins: [],
};

export default config;
