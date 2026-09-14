/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef4ff",
          100: "#d9e6ff",
          200: "#bcd3ff",
          300: "#8eb4fc",
          400: "#5c8bf8",
          500: "#3b6ef5",
          600: "#2f5ae0",
          700: "#2647b4",
          800: "#233f8f",
          900: "#1e3670",
          950: "#152245",
        },
        // Semantic scoring colours. Extras alongside `brand`, never a replacement
        // for it — `brand` remains the primary accent.
        pass: "#2A9D8F",
        fail: "#E63946",
        skip: "#8D99AE",
        manual: "#6C63FF",
        "sev-blocker": "#E63946",
        "sev-major": "#F4A261",
        "sev-minor": "#E9C46A",
        "sev-info": "#8AB0AB",
      },
      boxShadow: {
        card: "0 2px 6px rgba(15,20,26,.06)",
      },
    },
  },
  plugins: [],
};
