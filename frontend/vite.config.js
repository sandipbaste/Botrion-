// import { defineConfig } from 'vite'
// import react from '@vitejs/plugin-react'
// import tailwindcss from '@tailwindcss/vite'

// export default defineConfig({
//   plugins: [react(), tailwindcss()],
//   server: {
//     port: 5173,
//     host: true
//   },
//   preview: {
//     port: 5173,
//     host: true
//   }
// })


import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],

  server: {
    host: true,
    port: 5173,
    allowedHosts: [
      "botrion-v2.onrender.com"
    ]
  },

  preview: {
    host: true,
    port: 5173,
    allowedHosts: [
      "botrion-v2.onrender.com"
    ]
  }
})