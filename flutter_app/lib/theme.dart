/// Thème Jade — jetons de couleur communs aux applications yety.
///
/// Sombre d'abord : terrain quasi noir, surfaces neutres, contours en cheveu.
/// Le bleu yety #004AAD porte les boutons et surfaces principales (texte blanc,
/// contraste 8:1) ; #7AA7F0 sert au texte d'accent et aux liens sur fond sombre.
/// Les teintes de statut gardent leur sens. Aucun composant ne code de couleur
/// en dur : tout passe par `context.jade`.
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
  final Color primary; // marque yety #004AAD : boutons, surfaces principales
  final Color accent; // texte d'accent, liens, icônes actives (lisible sur le fond)
  final Color primaryHover;
  final Color onPrimary; // texte et icônes posés sur `primary`
  final Color primaryContainer; // fond tonal de la marque (sélection, survol)
  final Color onPrimaryContainer;
  final Color secondary; // documents / citations / liens (info)
  final Color success;
  final Color advisory; // avertissement
  final Color danger; // pire cas : à utiliser avec parcimonie
  final Color ring; // anneau de focus clavier

  /// Texte posé sur `danger` : sombre sur le rouge clair du thème sombre.
  Color get onDanger => danger.computeLuminance() > 0.3 ? bg : onPrimary;

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
    required this.accent,
    required this.primaryHover,
    required this.onPrimary,
    required this.primaryContainer,
    required this.onPrimaryContainer,
    required this.secondary,
    required this.success,
    required this.advisory,
    required this.danger,
    required this.ring,
  });

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
    faint: Color(0xFF76746B),
    primary: Color(0xFF004AAD),
    accent: Color(0xFF004AAD),
    primaryHover: Color(0xFF003A8A),
    onPrimary: Color(0xFFFFFFFF),
    primaryContainer: Color(0xFFE4ECF9),
    onPrimaryContainer: Color(0xFF00265F),
    secondary: Color(0xFF004AAD), // info
    success: Color(0xFF0C7C5A),
    advisory: Color(0xFFC07A12),
    danger: Color(0xFFB23A2C),
    ring: Color(0xFF004AAD),
  );

  static const dark = JadeColors(
    bg: Color(0xFF07080A),
    panel: Color(0xFF0B0D10),
    tile: Color(0xFF111419),
    card: Color(0xFF0B0D10),
    border: Color(0xFF16191E),
    borderStrong: Color(0xFF23272E),
    text: Color(0xFFECEEF1),
    body: Color(0xFFC2C8D0),
    muted: Color(0xFF8A919C),
    faint: Color(0xFF7A818C),
    primary: Color(0xFF004AAD),
    accent: Color(0xFF7AA7F0),
    primaryHover: Color(0xFF0A5CCB),
    onPrimary: Color(0xFFFFFFFF),
    primaryContainer: Color(0xFF0E2A52),
    onPrimaryContainer: Color(0xFFCFE0FF),
    secondary: Color(0xFF7AA7F0), // info
    success: Color(0xFF2FD17C),
    advisory: Color(0xFFF2B033),
    danger: Color(0xFFFF5C5C),
    ring: Color(0xFF7AA7F0),
  );

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
    seedColor: const Color(0xFF004AAD),
    brightness: brightness,
    surface: jade.bg,
    primary: jade.primary,
    onPrimary: jade.onPrimary,
    error: jade.danger,
  );
  // Cibles de clic d'au moins 40 px et rayon de bouton de 8 px, partout.
  const minTarget = Size(40, 40);
  final buttonShape = RoundedRectangleBorder(borderRadius: BorderRadius.circular(8));
  return ThemeData(
    useMaterial3: true,
    brightness: brightness,
    colorScheme: scheme,
    scaffoldBackgroundColor: jade.bg,
    fontFamily: 'Geomini',
    extensions: [jade],
    splashFactory: NoSplash.splashFactory,
    focusColor: jade.ring.withValues(alpha: 0.18),
    dividerTheme: DividerThemeData(color: jade.border, thickness: 1, space: 1),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: minTarget,
        shape: buttonShape,
        backgroundColor: jade.primary,
        foregroundColor: jade.onPrimary,
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: minTarget,
        shape: buttonShape,
        side: BorderSide(color: jade.borderStrong),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(minimumSize: minTarget, shape: buttonShape),
    ),
    iconButtonTheme: IconButtonThemeData(
      style: IconButton.styleFrom(minimumSize: minTarget),
    ),
    tooltipTheme: TooltipThemeData(
      waitDuration: const Duration(milliseconds: 450),
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: jade.text.withValues(alpha: 0.92),
        borderRadius: BorderRadius.circular(7),
      ),
      textStyle: TextStyle(fontSize: 12, color: jade.bg),
    ),
  );
}

extension JadeTheme on BuildContext {
  JadeColors get jade => Theme.of(this).extension<JadeColors>()!;
}
