import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        ink: "#1d1d1f",
        subtle: "#6e6e73",
        line: "#e5e5ea",
        accent: "#0071e3",
        accentHover: "#0077ed",
      },
      fontFamily: {
        sans: [
          "Pretendard",
          "-apple-system",
          "BlinkMacSystemFont",
          "system-ui",
          "Segoe UI",
          "Apple SD Gothic Neo",
          "Roboto",
          "Helvetica Neue",
          "sans-serif",
        ],
      },
      boxShadow: {
        soft: "0 1px 3px rgba(0,0,0,0.04), 0 8px 30px rgba(0,0,0,0.05)",
        card: "0 2px 8px rgba(0,0,0,0.04)",
      },
      borderRadius: {
        xl2: "1.25rem",
      },
      keyframes: {
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
