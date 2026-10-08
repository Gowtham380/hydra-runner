/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        hydra: {
          bg: '#090d16',
          card: '#111827',
          border: '#1f293d',
          accent: '#0284c7',
          glow: '#38bdf8'
        }
      }
    },
  },
  plugins: [],
}
