import { defineConfig } from 'vitest/config';

// Tests unitaires frontend (F5.3). Environnement jsdom pour navigator/document.
export default defineConfig({
  test: {
    environment: 'jsdom',
    include: ['test/unit/**/*.test.js'],
  },
});
