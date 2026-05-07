/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        qumulo: {
          blue:   '#0057b8',
          teal:   '#00b4b4',
          dark:   '#0a1628',
          panel:  '#111c2e',
          border: '#1e3050',
        },
      },
    },
  },
  plugins: [],
}
