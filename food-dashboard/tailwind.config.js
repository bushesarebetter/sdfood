/** @type {import('tailwindcss').Config} */

/**
 * A civic broadsheet on warm paper: ink for everything structural, one
 * sequential ramp for the bands of a `bands` export. Fonts are the system's
 * own, so the site makes no request to a font service. `ink.3` and the amber
 * used as text are dark enough for 4.5:1 on paper.
 */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        serif: ["Georgia", "Cambria", '"Times New Roman"', "Times", "serif"],
        sans: ["system-ui", "-apple-system", '"Segoe UI"', "Roboto", '"Helvetica Neue"', "Arial", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", '"Liberation Mono"', "monospace"],
      },
      colors: {
        paper: {
          DEFAULT: "#FBF9F5",
          sunk: "#F2EEE6",
          edge: "#EAE4D9",
        },
        rule: {
          DEFAULT: "#DCD5C7",
          strong: "#B8AF9C",
        },
        ink: {
          DEFAULT: "#17150F",
          2: "#55503F",
          3: "#6B6457",
        },
        // The band ramp: swatches and dots. Amber as text uses amber.text.
        band: {
          1: "#7F1D1D",
          2: "#C2410C",
          3: "#D97706",
        },
        amber: {
          text: "#9A4A07",
        },
      },
      letterSpacing: {
        label: "0.14em",
      },
      boxShadow: {
        paper: "0 1px 2px rgba(23,21,15,0.06), 0 8px 24px -12px rgba(23,21,15,0.18)",
      },
      maxWidth: {
        measure: "34ch",
      },
    },
  },
  plugins: [],
};
