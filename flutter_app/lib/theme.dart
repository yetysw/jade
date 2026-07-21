/// Thème Jade — palette sémantique « quiet document intelligence ».
///
/// Bleu profond Jade (#00357F) comme voix unique du produit ; surfaces tonales
/// (canvas → panneau → tuile → carte), contours en cheveu, rampe d'encre à
/// quatre niveaux. Voir `.claude/skills/jade-ui-design`.
library;

import 'package:flutter/material.dart';

/// Couleurs sémantiques de Jade, exposées via `context.jade`.
class JadeColors extends ThemeExtension<JadeColors> {
  final Color bg; // canvas de conversation
  final Color panel; // barre latérale
  final Color tile; // tuiles / survol neutre
  final Color card; // cartes, surfaces flottantes
  final Color border; // contour en cheveu
  final Color borderStrong; // contour appuyé
  final Color text; // encre principale
  final Color body; // texte courant
  final Color muted; // texte secondaire
  final Color faint; // texte tertiaire
  final Color primary; // voix du produit
  final Color primaryHover;
  final Color primaryContainer; // fond tonal de l'accent
  final Color onPrimaryContainer;
  final Color secondary; // documents / citations (teal)
  final Color success;
  final Color danger;
  final Color ring; // anneau de focus clavier

  const JadeColors({
    required this.bg,
    required this.panel,
    required this.tile,
    required this.card,
    required this.border,
    required this.borderStrong,
    required this.text,
    required this.body,
    required this.muted,
    required this.faint,
    required this.primary,
    required this.primaryHover,
    required this.primaryContainer,
    required this.onPrimaryContainer,
    required this.secondary,
    required this.success,
    required this.danger,
    required this.ring,
  });

  // Langage chromatique : bleu Jade = ancre (agir sur le système) ; vert jade
  // = couleur vivante du produit (documents, savoir, confiance). Surfaces en
  // papier neutre légèrement chaud plutôt que gris Material par défaut.
  static const light = JadeColors(
    bg: Color(0xFFFCFCFB),
    panel: Color(0xFFF5F4F1),
    tile: Color(0xFFECEBE6),
    card: Color(0xFFFFFFFF),
    border: Color(0xFFE7E5DF),
    borderStrong: Color(0xFFD6D3CA),
    text: Color(0xFF1A1A17),
    body: Color(0xFF45443E),
    muted: Color(0xFF6F6E66),
    faint: Color(0xFF9C9A90),
    primary: Color(0xFF00357F),
    primaryHover: Color(0xFF002B67),
    primaryContainer: Color(0xFFE4ECF9),
    onPrimaryContainer: Color(0xFF00265F),
    secondary: Color(0xFF0C7C5A), // jade
    success: Color(0xFF0C7C5A),
    danger: Color(0xFFB23A2C),
    ring: Color(0x5500357F),
  );

  static const dark = JadeColors(
    bg: Color(0xFF0C0F13),
    panel: Color(0xFF12161C),
    tile: Color(0xFF1C222B),
    card: Color(0xFF161B22),
    border: Color(0xFF242B35),
    borderStrong: Color(0xFF333B47),
    text: Color(0xFFECEEF1),
    body: Color(0xFFC2C8D0),
    muted: Color(0xFF929AA4),
    faint: Color(0xFF6A717B),
    primary: Color(0xFF6AA5FF),
    primaryHover: Color(0xFF89B8FF),
    primaryContainer: Color(0xFF10305C),
    onPrimaryContainer: Color(0xFFCFE0FF),
    secondary: Color(0xFF34C89A), // jade lumineux
    success: Color(0xFF34C89A),
    danger: Color(0xFFE77E6E),
    ring: Color(0x886AA5FF),
  );

  /// Teinte jade plus profonde (dégradés de la gemme, accents appuyés).
  Color get jadeDeep =>
      bg.computeLuminance() > 0.5 ? const Color(0xFF064A36) : const Color(0xFF1E9C78);
  Color get jadeLight =>
      bg.computeLuminance() > 0.5 ? const Color(0xFF39B98E) : const Color(0xFF7FE6C2);

  @override
  JadeColors copyWith() => this;

  @override
  JadeColors lerp(ThemeExtension<JadeColors>? other, double t) =>
      t < 0.5 ? this : (other as JadeColors? ?? this);
}

/// Couleur d'icône par type de fichier (façon Gemini).
Color fileTypeColor(String name) {
  final ext = name.split('.').last.toLowerCase();
  if (['xlsx', 'xls', 'csv', 'xlsm'].contains(ext)) return const Color(0xFF10A05A);
  if (['docx', 'doc', 'odt', 'rtf'].contains(ext)) return const Color(0xFF1A73E8);
  if (ext == 'pdf') return const Color(0xFFEA4335);
  if (['pptx', 'ppt'].contains(ext)) return const Color(0xFFF29900);
  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'].contains(ext)) {
    return const Color(0xFF7C4DFF);
  }
  if (['txt', 'md', 'log', 'html', 'htm', 'json', 'eml', 'msg'].contains(ext)) {
    return const Color(0xFF7C8591);
  }
  return const Color(0xFF5F6368);
}

String fileTypeLabel(String name) {
  final ext = name.split('.').last.toLowerCase();
  if (['xlsx', 'xls', 'csv', 'xlsm'].contains(ext)) return 'Feuille de calcul';
  if (['docx', 'doc', 'odt', 'rtf'].contains(ext)) return 'Document';
  if (ext == 'pdf') return 'Document PDF';
  if (['pptx', 'ppt'].contains(ext)) return 'Présentation';
  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'].contains(ext)) return 'Image';
  if (['txt', 'md', 'log', 'html', 'htm', 'json'].contains(ext)) {
    return 'Fichier texte';
  }
  return 'Fichier';
}

ThemeData buildTheme(Brightness brightness) {
  final jade = brightness == Brightness.light ? JadeColors.light : JadeColors.dark;
  final scheme = ColorScheme.fromSeed(
    seedColor: const Color(0xFF00357F),
    brightness: brightness,
    surface: jade.bg,
    primary: jade.primary,
  );
  return ThemeData(
    useMaterial3: true,
    brightness: brightness,
    colorScheme: scheme,
    scaffoldBackgroundColor: jade.bg,
    fontFamily: 'Geomini',
    extensions: [jade],
    splashFactory: NoSplash.splashFactory,
    dividerTheme: DividerThemeData(color: jade.border, thickness: 1, space: 1),
    tooltipTheme: TooltipThemeData(
      waitDuration: const Duration(milliseconds: 450),
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: jade.text.withValues(alpha: 0.92),
        borderRadius: BorderRadius.circular(7),
      ),
      textStyle: TextStyle(
        fontSize: 12,
        color: brightness == Brightness.light ? Colors.white : jade.bg,
      ),
    ),
  );
}

extension JadeTheme on BuildContext {
  JadeColors get jade => Theme.of(this).extension<JadeColors>()!;
}
