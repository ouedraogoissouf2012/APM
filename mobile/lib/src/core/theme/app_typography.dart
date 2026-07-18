import 'package:flutter/material.dart';

/// Typographie — contrat DESIGN_SPEC §3.
///
/// Deux familles, deux rôles :
/// - **Fraunces** (300/400, + italique) : display, contenu émotionnel,
///   mots anglais, transcription de la voix de l'utilisateur.
/// - **Inter** (400/500) : UI fonctionnelle (labels, boutons, navigation).
///
/// Les polices sont bundlées en assets (voir pubspec.yaml) : rendu
/// hors-ligne dès le premier lancement, tests déterministes — pas de
/// téléchargement runtime.
///
/// Règles strictes : overlines en MAJUSCULES avec letter-spacing ;
/// jamais de graisse 600/700 — uniquement 300/400/500.
abstract final class AppType {
  static const _fraunces = 'Fraunces';
  static const _inter = 'Inter';

  /// Score du bilan (ex. « 82 »).
  static TextStyle displayXl(Color c) => TextStyle(
      fontFamily: _fraunces,
      fontSize: 52,
      fontWeight: FontWeight.w300,
      height: 1.0,
      color: c);

  /// Greeting (« Good evening, Seven. »).
  static TextStyle displayLg(Color c) => TextStyle(
      fontFamily: _fraunces,
      fontSize: 28,
      fontWeight: FontWeight.w300,
      height: 1.15,
      color: c);

  /// Titres de sections / cartes.
  static TextStyle displayMd(Color c) => TextStyle(
      fontFamily: _fraunces,
      fontSize: 20,
      fontWeight: FontWeight.w400,
      height: 1.2,
      color: c);

  /// Accents de marque et traductions, en italique.
  static TextStyle displayItalic(Color c, {double fontSize = 20}) => TextStyle(
      fontFamily: _fraunces,
      fontSize: fontSize,
      fontWeight: FontWeight.w300,
      fontStyle: FontStyle.italic,
      height: 1.2,
      color: c);

  /// Ce que dit l'utilisateur (transcription).
  static TextStyle transcript(Color c) => TextStyle(
      fontFamily: _fraunces,
      fontSize: 19,
      fontWeight: FontWeight.w300,
      fontStyle: FontStyle.italic,
      height: 1.45,
      color: c);

  /// Corps de texte fonctionnel.
  static TextStyle body(Color c) =>
      TextStyle(fontFamily: _inter, fontSize: 14, height: 1.55, color: c);

  /// Labels, boutons, stats.
  static TextStyle label(Color c) => TextStyle(
      fontFamily: _inter,
      fontSize: 12,
      fontWeight: FontWeight.w500,
      letterSpacing: 0.5,
      color: c);

  /// « JE T'ÉCOUTE », « MÉMOIRE » — toujours rendu en MAJUSCULES.
  static TextStyle overline(Color c) => TextStyle(
      fontFamily: _inter, fontSize: 11, letterSpacing: 1.2, color: c);
}
