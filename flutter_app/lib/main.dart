/// Jade 2.0 — application de bureau native (Flutter Windows).
///
/// L'interface est 100 % native ; toute la logique documentaire (RAG,
/// indexation, sécurité, création de fichiers) reste dans le backend local
/// Python, inchangé (localhost:8765).
library;

import 'dart:async';

import 'package:flutter/material.dart';

import 'api.dart';
import 'backend.dart';
import 'design.dart';
import 'home.dart';
import 'models.dart';
import 'tabler.dart';
import 'theme.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const JadeApp());
}

/// Racine de l'application : construit le [MaterialApp], applique le theme Jade
/// (clair / sombre / auto) et heberge l'ecran principal.
class JadeApp extends StatefulWidget {
  const JadeApp({super.key});

  /// Retrouve l'etat racine depuis un [BuildContext] descendant (ex. bascule
  /// du mode de theme).
  static JadeAppState of(BuildContext context) =>
      context.findAncestorStateOfType<JadeAppState>()!;

  @override
  State<JadeApp> createState() => JadeAppState();
}

/// Etat de [JadeApp] : conserve le [ThemeMode] courant et le rafraichit.
class JadeAppState extends State<JadeApp> {
  ThemeMode _mode = ThemeMode.system;

  ThemeMode get themeMode => _mode;

  void cycleTheme() {
    setState(() {
      _mode = switch (_mode) {
        ThemeMode.system => ThemeMode.light,
        ThemeMode.light => ThemeMode.dark,
        ThemeMode.dark => ThemeMode.system,
      };
    });
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Jade',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(Brightness.light),
      darkTheme: buildTheme(Brightness.dark),
      themeMode: _mode,
      home: const _Boot(),
    );
  }
}

/// Écran de démarrage : s'assure que le backend local répond avant d'ouvrir
/// l'interface (le lance s'il est installé à côté de l'application).
class _Boot extends StatefulWidget {
  const _Boot();

  @override
  State<_Boot> createState() => _BootState();
}

class _BootState extends State<_Boot> {
  final _backend = BackendManager();
  final _api = ApiClient();
  String? _error;
  InitStatus? _init;

  @override
  void initState() {
    super.initState();
    _start();
  }

  @override
  void dispose() {
    _api.close();
    super.dispose();
  }

  Future<void> _start() async {
    // 1) démarrer / joindre le moteur local (répond vite : chargement paresseux)
    final err = await _backend.ensureRunning();
    if (!mounted) return;
    if (err != null) {
      setState(() => _error = err);
      return;
    }
    // 2) attendre que les modèles soient prêts (télécharge au 1er lancement),
    //    en affichant la progression. Aucun timeout : le 1er téléchargement
    //    (~2 Go) peut durer plusieurs minutes.
    while (mounted) {
      InitStatus? s;
      try {
        s = await _api.initStatus();
      } catch (_) {
        // moteur momentanément injoignable : on retente
      }
      if (!mounted) return;
      if (s != null) setState(() => _init = s);
      if (s?.ready == true) break;
      await Future<void>.delayed(const Duration(milliseconds: 500));
    }
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      PageRouteBuilder(
        transitionDuration: context.motion(const Duration(milliseconds: 260)),
        pageBuilder: (_, __, ___) => const HomeScreen(),
        transitionsBuilder: (_, anim, __, child) => FadeTransition(
          opacity: CurvedAnimation(parent: anim, curve: Curves.easeOut),
          child: child,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    final ok = _error == null;
    return Scaffold(
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 360),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              // le logo tourne pendant le démarrage (indicateur de chargement)
              JadeMark(size: 76, animate: ok),
              const SizedBox(height: JadeSpace.xxl),
              if (ok)
                ..._progress(jade)
              else
                ..._errorView(jade),
            ],
          ),
        ),
      ),
    );
  }

  List<Widget> _progress(JadeColors jade) {
    final init = _init;
    final title = init == null || !init.ready
        ? 'Préparation de Jade…'
        : 'Prêt';
    return [
      Text(title, style: JadeType.title.copyWith(color: jade.text)),
      const SizedBox(height: JadeSpace.lg),
      // barre déterminée en téléchargement (fraction connue), sinon indéterminée
      SizedBox(
        width: 280,
        child: ClipRRect(
          borderRadius: JadeRadius.all(JadeRadius.pill),
          child: LinearProgressIndicator(
            value: init?.fraction,
            minHeight: 6,
            backgroundColor: jade.tile,
            valueColor: AlwaysStoppedAnimation(jade.primary),
          ),
        ),
      ),
      const SizedBox(height: JadeSpace.sm),
      // mini-journal : ce que fait le démarrage, en une ligne
      Text(
        _logLine(init),
        textAlign: TextAlign.center,
        maxLines: 2,
        overflow: TextOverflow.ellipsis,
        style: JadeType.caption.copyWith(color: jade.faint, height: 1.45),
      ),
    ];
  }

  String _logLine(InitStatus? init) {
    if (init == null) return 'Démarrage du moteur local…';
    if (init.totalMb > 0) {
      return '${init.detail}  ${init.downloadedMb} / ${init.totalMb} Mo';
    }
    return init.detail;
  }

  List<Widget> _errorView(JadeColors jade) {
    return [
      Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(TablerIcons.alertCircle, size: 18, color: jade.danger),
          const SizedBox(width: JadeSpace.sm),
          Text('Moteur indisponible',
              style: JadeType.title.copyWith(color: jade.text)),
        ],
      ),
      const SizedBox(height: JadeSpace.md),
      Text(
        _error!,
        textAlign: TextAlign.center,
        style: JadeType.label.copyWith(color: jade.muted, height: 1.55),
      ),
      const SizedBox(height: JadeSpace.xl),
      FilledButton(
        style: FilledButton.styleFrom(
          backgroundColor: jade.primary,
          padding: const EdgeInsets.symmetric(
              horizontal: JadeSpace.xxl, vertical: JadeSpace.md),
          shape:
              RoundedRectangleBorder(borderRadius: JadeRadius.all(JadeRadius.md)),
        ),
        onPressed: () {
          setState(() => _error = null);
          _start();
        },
        child: const Text('Réessayer'),
      ),
    ];
  }
}
