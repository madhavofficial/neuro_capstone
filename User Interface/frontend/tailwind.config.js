/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: "#172033",
        paper: "#F7F8F6",
        white: "#FFFFFF",

        teal: {
          50: "#EEF9F7",
          100: "#D8F1ED",
          200: "#B4E3DC",
          300: "#7CCFC4",
          400: "#45B8AA",
          500: "#159A8C",
          600: "#0B7F73",
          700: "#09675F",
          800: "#09534E",
          900: "#083F3C",
        },

        slate: {
          50: "#F8FAFA",
          100: "#F1F4F4",
          200: "#E3E8E7",
          300: "#CBD4D3",
          400: "#98A5A3",
          500: "#687673",
          600: "#4D5B58",
          700: "#374441",
          800: "#26322F",
          900: "#17201E",
        },

        amber: {
          50: "#FFF9E8",
          100: "#FFF0BF",
          200: "#F9DD7A",
          500: "#C58A16",
          700: "#8A610C",
          800: "#6F4D08",
        },

        red: {
          50: "#FEF2F2",
          100: "#FEE2E2",
          200: "#FECACA",
          600: "#DC2626",
          700: "#B91C1C",
          800: "#991B1B",
        },
      },

      fontFamily: {
        sans: [
          "DM Sans",
          "Inter",
          "system-ui",
          "sans-serif",
        ],
        display: [
          "DM Sans",
          "Inter",
          "system-ui",
          "sans-serif",
        ],
        mono: [
          "IBM Plex Mono",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "monospace",
        ],
      },

      boxShadow: {
        soft: "0 1px 2px rgba(23,32,51,0.04), 0 8px 30px rgba(23,32,51,0.06)",
        lift: "0 12px 40px rgba(23,32,51,0.10)",
        focus: "0 0 0 4px rgba(21,154,140,0.12)",
      },

      borderRadius: {
        xl: "1rem",
        "2xl": "1.25rem",
        "3xl": "1.5rem",
      },

      letterSpacing: {
        tightest: "-0.045em",
      },
    },
  },
  plugins: [],
};