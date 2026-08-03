/// Système de design de Jade — source unique des valeurs visuelles.
///
/// Aucun widget ne doit coder en dur une taille, un espacement, un rayon ou une
/// durée : tout vient d'ici (ou de la palette `context.jade` dans theme.dart).
/// Distillé des principes Anthropic (frontend-design), Vercel (Web Interface
/// Guidelines) et Material 3. Voir `.claude/skills/jade-ui-design`.
library;

import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';

import 'theme.dart';

// ─────────────────────────────────────────────────────────────── espacements
/// Grille de 4 px. N'utiliser que ces pas.
abstract final class JadeSpace {
  static const double xs = 4;
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 16;
  static const double xl = 20;
  static const double xxl = 24;
  static const double xxxl = 32;
  static const double huge = 40;
}

// ─────────────────────────────────────────────────────────────────── rayons
abstract final class JadeRadius {
  static const double xs = 6;
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 16;
  static const double xl = 20;
  static const double pill = 999;

  static BorderRadius all(double r) => BorderRadius.circular(r);
}

// ──────────────────────────────────────────────────────────── échelle de type
/// Une seule échelle typographique. Recolorer avec `.copyWith(color: …)`.
abstract final class JadeType {
  static const _tabular = [FontFeature.tabularFigures()];

  // Geomini pour tout (police variable). Titres : poids marqué, tracking serré.
  static const display = TextStyle(
      fontSize: 32,
      fontWeight: FontWeight.w600,
      letterSpacing: -0.5,
      height: 1.12);
  static const headline = TextStyle(
      fontSize: 22,
      fontWeight: FontWeight.w600,
      letterSpacing: -0.2,
      height: 1.2);
  static const title =
      TextStyle(fontSize: 17, fontWeight: FontWeight.w600, height: 1.3);
  static const subtitle =
      TextStyle(fontSize: 15, fontWeight: FontWeight.w600, height: 1.35);
  static const body = TextStyle(fontSize: 14.5, height: 1.6);
  static const label =
      TextStyle(fontSize: 13, fontWeight: FontWeight.w500, height: 1.4);
  static const caption =
      TextStyle(fontSize: 11.5, fontWeight: FontWeight.w500, height: 1.4);
  static const eyebrow = TextStyle(
      fontSize: 10.5, fontWeight: FontWeight.w700, letterSpacing: 0.7, height: 1.3);

  /// Chiffres alignés (compteurs, versions, colonnes de nombres).
  static const tabular = TextStyle(fontFeatures: _tabular);
}

// ──────────────────────────────────────────────────────────────── élévation
abstract final class JadeElevation {
  /// Ombre douce à deux couches (contact + diffusion) pour un relief crédible.
  static List<BoxShadow> soft(BuildContext context) {
    final d = context.isDark;
    return [
      BoxShadow(
        color: Colors.black.withValues(alpha: d ? 0.30 : 0.04),
        blurRadius: 3,
        offset: const Offset(0, 1),
      ),
      BoxShadow(
        color: Colors.black.withValues(alpha: d ? 0.38 : 0.07),
        blurRadius: 24,
        offset: const Offset(0, 10),
      ),
    ];
  }

  static List<BoxShadow> lift(BuildContext context) {
    final d = context.isDark;
    return [
      BoxShadow(
        color: Colors.black.withValues(alpha: d ? 0.34 : 0.06),
        blurRadius: 4,
        offset: const Offset(0, 2),
      ),
      BoxShadow(
        color: Colors.black.withValues(alpha: d ? 0.46 : 0.12),
        blurRadius: 32,
        offset: const Offset(0, 16),
      ),
    ];
  }
}

// ──────────────────────────────────────────────────────────────────── motion
extension JadeMotion on BuildContext {
  /// Respecte « réduire les animations » du système : renvoie 0 si désactivé.
  Duration motion(Duration d) =>
      MediaQuery.maybeOf(this)?.disableAnimations == true ? Duration.zero : d;

  bool get isDark => Theme.of(this).brightness == Brightness.dark;
}

// ─────────────────────────────────────────────────────────── survol (hover)
/// Reconstruit son enfant selon l'état de survol. Curseur main par défaut.
class Hoverable extends StatefulWidget {
  final Widget Function(BuildContext context, bool hovering) builder;
  final bool clickable;
  const Hoverable({super.key, required this.builder, this.clickable = true});

  @override
  State<Hoverable> createState() => _HoverableState();
}

class _HoverableState extends State<Hoverable> {
  bool _h = false;
  @override
  Widget build(BuildContext context) => MouseRegion(
        cursor: widget.clickable
            ? SystemMouseCursors.click
            : MouseCursor.defer,
        onEnter: (_) => setState(() => _h = true),
        onExit: (_) => setState(() => _h = false),
        child: widget.builder(context, _h),
      );
}

// ─────────────────────────────────────────────────── anneau de focus clavier
/// Entoure un enfant d'un anneau visible quand il reçoit le focus clavier.
class FocusRing extends StatefulWidget {
  final Widget child;
  final double radius;
  const FocusRing({super.key, required this.child, this.radius = JadeRadius.lg});

  @override
  State<FocusRing> createState() => _FocusRingState();
}

class _FocusRingState extends State<FocusRing> {
  bool _focused = false;
  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    return Focus(
      canRequestFocus: false,
      descendantsAreFocusable: true,
      onFocusChange: (f) => setState(() => _focused = f),
      child: AnimatedContainer(
        duration: context.motion(const Duration(milliseconds: 140)),
        decoration: BoxDecoration(
          borderRadius: JadeRadius.all(widget.radius + 3),
          border: Border.all(
            color: _focused ? jade.ring : Colors.transparent,
            width: 2,
          ),
        ),
        child: widget.child,
      ),
    );
  }
}

// ──────────────────────────────────────────────────────────── marque (logo)
/// Marque du produit : le logo spirale de Jade.
class JadeMark extends StatelessWidget {
  final double size;
  final bool animate;
  const JadeMark({super.key, this.size = 38, this.animate = false});

  @override
  Widget build(BuildContext context) {
    final logo = Image.asset(
      'assets/jade-logo.png',
      width: size,
      height: size,
      filterQuality: FilterQuality.medium,
    );
    if (!animate) return logo;
    return _SpinningLogo(size: size, child: logo);
  }
}

/// Rotation continue du logo — indicateur « génération en cours ».
class _SpinningLogo extends StatefulWidget {
  final double size;
  final Widget child;
  const _SpinningLogo({required this.size, required this.child});

  @override
  State<_SpinningLogo> createState() => _SpinningLogoState();
}

class _SpinningLogoState extends State<_SpinningLogo>
    with SingleTickerProviderStateMixin {
  late final AnimationController _c;

  @override
  void initState() {
    super.initState();
    _c = AnimationController(
        vsync: this, duration: const Duration(milliseconds: 1400))
      ..repeat();
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // respecte « réduire les animations » : logo fixe si désactivé
    if (context.motion(const Duration(milliseconds: 1)) == Duration.zero) {
      return widget.child;
    }
    return RotationTransition(turns: _c, child: widget.child);
  }
}

// ─────────────────────────────────────────────────────────────── markdown
/// Feuille de style Markdown commune à tout rendu Markdown de Jade (réponses
/// de l'assistant, documents légaux) : cohérente avec le design system,
/// lisible en thème clair et sombre. Ne jamais afficher un [Markdown] /
/// [MarkdownBody] sans cette feuille — les styles par défaut du paquet
/// (`MarkdownStyleSheet.fromTheme`) figent certaines couleurs (citations
/// notamment) et ne s'adaptent pas au thème sombre.
MarkdownStyleSheet jadeMarkdownStyleSheet(BuildContext context) {
  final jade = context.jade;
  return MarkdownStyleSheet(
    p: JadeType.body.copyWith(color: jade.body, height: 1.65),
    h1: JadeType.headline.copyWith(color: jade.text),
    h2: JadeType.title.copyWith(color: jade.text),
    h3: JadeType.subtitle.copyWith(color: jade.text),
    h1Padding: const EdgeInsets.only(top: JadeSpace.md, bottom: JadeSpace.xs),
    h2Padding: const EdgeInsets.only(top: JadeSpace.md, bottom: JadeSpace.xs),
    h3Padding: const EdgeInsets.only(top: JadeSpace.sm, bottom: JadeSpace.xs),
    listBullet: JadeType.body.copyWith(color: jade.body),
    listIndent: JadeSpace.xl,
    strong: const TextStyle(fontWeight: FontWeight.w700),
    em: const TextStyle(fontStyle: FontStyle.italic),
    code: TextStyle(
        fontSize: 12.5,
        fontFamily: 'Consolas',
        backgroundColor: jade.tile,
        color: jade.text),
    codeblockPadding: const EdgeInsets.all(JadeSpace.md),
    codeblockDecoration: BoxDecoration(
      color: jade.tile,
      borderRadius: JadeRadius.all(JadeRadius.md),
      border: Border.all(color: jade.border),
    ),
    blockquote: JadeType.body.copyWith(color: jade.body, height: 1.6),
    blockquotePadding: const EdgeInsets.fromLTRB(
        JadeSpace.md, JadeSpace.sm, JadeSpace.md, JadeSpace.sm),
    blockquoteDecoration: BoxDecoration(
      color: jade.tile,
      borderRadius: JadeRadius.all(JadeRadius.sm),
      border: Border(left: BorderSide(color: jade.secondary, width: 3)),
    ),
    horizontalRuleDecoration: BoxDecoration(
      border: Border(top: BorderSide(color: jade.border)),
    ),
    tableBorder: TableBorder.all(color: jade.border, width: 0.8),
    tableHead:
        JadeType.label.copyWith(color: jade.text, fontWeight: FontWeight.w700),
    tableBody: JadeType.label.copyWith(color: jade.body),
    tableCellsPadding: const EdgeInsets.symmetric(
        horizontal: JadeSpace.md, vertical: JadeSpace.sm),
    a: TextStyle(color: jade.primary, fontWeight: FontWeight.w600),
  );
}

// ───────────────────────────────────────────────── libellé de section (eyebrow)
class SectionLabel extends StatelessWidget {
  final String text;
  const SectionLabel(this.text, {super.key});
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(
            JadeSpace.sm, JadeSpace.lg, JadeSpace.sm, JadeSpace.xs),
        child: Text(text.toUpperCase(),
            style: JadeType.eyebrow.copyWith(color: context.jade.faint)),
      );
}
