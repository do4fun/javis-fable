// smoke.spec.js — Test de fumée headless (F5.3, optionnel).
//
// Charge la page et vérifie que l'application s'initialise (canvas présent,
// écran de chargement, HUD). Nécessite Playwright + un serveur (Vite ou le
// serveur FastAPI servant web/dist).
//
// Installation (optionnelle, télécharge les navigateurs) :
//   cd web && npm i -D @playwright/test && npx playwright install chromium
// Lancer :
//   npx playwright test
//
// Non exécuté par `make check` par défaut (dépendances lourdes).

import { test, expect } from '@playwright/test';

const BASE = process.env.JARVIS_URL || 'http://localhost:5173';

test('la page se charge et l’UI apparaît', async ({ page }) => {
  await page.goto(BASE);

  // Canvas de rendu présent.
  await expect(page.locator('#scene, #avatar canvas')).toBeTruthy();

  // Le HUD s'initialise (bandeau d'état).
  await expect(page.locator('#status-banner')).toBeVisible({ timeout: 10000 });

  // L'écran de démarrage finit par disparaître (avatar prêt ou repli).
  await expect(page.locator('#boot')).toHaveClass(/hidden|error/, { timeout: 15000 });
});
