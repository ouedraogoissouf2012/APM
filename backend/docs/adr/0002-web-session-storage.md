# ADR 0002 — Session web : native-first, PWA en beta XSS

- **Statut** : accepté (2026-08-27, #495)
- **Portée** : stockage des JWT access/refresh sur Flutter web vs natif.

## Contexte

Les tokens passent en `Authorization: Bearer`. Sur natif,
`flutter_secure_storage` utilise Keystore/Keychain. Sur web, le plugin
exporte la clé AES en clair dans `localStorage` : XSS ou DevTools
déballent la session (#318 / #436).

Deux options :

- **A** — cookies httpOnly same-site (nouvelle archi auth, CSRF, CORS pincé).
- **B** — produit = apps natives. Web/PWA = canal de **dev / beta**, pas une
  session sécurisée.

## Décision

**B.** Chrome reste le client de développement. Le canal consommateur est
Play Store d'abord (#505). Les cookies httpOnly sont reportés tant que le
web n'est pas un produit.

## Conséquences

- Ne pas promettre un stockage « sécurisé » sur web.
- Ne pas implémenter Set-Cookie / withCredentials dans ce cycle.
- Voice takes ne persistent déjà pas sur web (#436).
