import { describe, it, expect } from 'vitest';
import { resolveProfile, profileSettings, detectProfile } from '../../src/quality.js';

describe('quality profiles (F5.3)', () => {
  it('respecte le choix explicite de l’utilisateur', () => {
    const p = resolveProfile('low');
    expect(p.name).toBe('low');
    expect(p.pixelRatio).toBe(1);
    expect(p.shadows).toBe(false);
  });

  it('tombe sur la détection auto si choix = auto', () => {
    const p = resolveProfile('auto');
    expect(['low', 'medium', 'high']).toContain(p.name);
  });

  it('profileSettings renvoie des réglages cohérents', () => {
    expect(profileSettings('high').pixelRatio).toBe(2);
    expect(profileSettings('inconnu').pixelRatio).toBe(2); // défaut high
  });

  it('detectProfile renvoie un profil valide', () => {
    expect(['low', 'medium', 'high']).toContain(detectProfile());
  });
});
