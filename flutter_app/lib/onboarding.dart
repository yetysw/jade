/// Premier lancement : acceptation des documents légaux (CGU + confidentialité)
/// puis parcours d'accueil guidé. Orchestré par [FirstRunFlow], affiché par
/// l'écran de démarrage tant que l'utilisateur n'a pas accepté / terminé.
library;

import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';

import 'api.dart';
import 'design.dart';
import 'home.dart';
import 'models.dart';
import 'tabler.dart';
import 'theme.dart';

/// Enchaîne les étapes de premier lancement puis remplace l'écran par [HomeScreen].
///
/// Étapes affichées uniquement si nécessaire, d'après [initial] :
/// acceptation légale (si version non acceptée) puis onboarding (si non terminé).
class FirstRunFlow extends StatefulWidget {
  final OnboardingState initial;
  const FirstRunFlow({super.key, required this.initial});

  @override
  State<FirstRunFlow> createState() => _FirstRunFlowState();
}

class _FirstRunFlowState extends State<FirstRunFlow> {
  final _api = ApiClient();
  late bool _legalDone = widget.initial.legalAccepted;
  late final bool _onboardingDone = widget.initial.onboardingDone;

  @override
  void dispose() {
    _api.close();
    super.dispose();
  }

  void _goHome() {
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(builder: (_) => const HomeScreen()),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (!_legalDone) {
      return _LegalGate(
        api: _api,
        onAccepted: () => setState(() => _legalDone = true),
      );
    }
    if (!_onboardingDone) {
      return _Onboarding(api: _api, onDone: _goHome);
    }
    // rien à afficher : on passe directement à l'accueil
    WidgetsBinding.instance.addPostFrameCallback((_) => _goHome());
    return const Scaffold(body: SizedBox.shrink());
  }
}

// ---------------------------------------------------- acceptation légale

/// Écran d'acceptation des CGU et de la politique de confidentialité, requis
/// avant toute utilisation au premier lancement (ou après mise à jour légale).
class _LegalGate extends StatefulWidget {
  final ApiClient api;
  final VoidCallback onAccepted;
  const _LegalGate({required this.api, required this.onAccepted});

  @override
  State<_LegalGate> createState() => _LegalGateState();
}

class _LegalGateState extends State<_LegalGate> {
  bool _checked = false;
  bool _busy = false;

  Future<void> _accept() async {
    setState(() => _busy = true);
    try {
      await widget.api.acceptLegal();
      widget.onAccepted();
    } catch (_) {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    return Scaffold(
      backgroundColor: jade.bg,
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(JadeSpace.xxl),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 520),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Center(child: const JadeMark(size: 64)),
                const SizedBox(height: JadeSpace.xl),
                Text('Bienvenue dans Jade',
                    textAlign: TextAlign.center,
                    style: JadeType.headline.copyWith(color: jade.text)),
                const SizedBox(height: JadeSpace.md),
                Text(
                  'Avant de commencer, veuillez prendre connaissance des '
                  'conditions générales d’utilisation et de la politique de '
                  'confidentialité. Vos documents restent sur ce poste.',
                  textAlign: TextAlign.center,
                  style: JadeType.label.copyWith(color: jade.muted, height: 1.55),
                ),
                const SizedBox(height: JadeSpace.xl),
                _DocButton(
                  icon: TablerIcons.fileText,
                  label: 'Lire les conditions générales',
                  onTap: () => _showDoc(context, widget.api, 'cgu',
                      'Conditions générales d’utilisation'),
                ),
                const SizedBox(height: JadeSpace.sm),
                _DocButton(
                  icon: TablerIcons.lock,
                  label: 'Lire la politique de confidentialité',
                  onTap: () => _showDoc(context, widget.api, 'privacy',
                      'Politique de confidentialité'),
                ),
                const SizedBox(height: JadeSpace.xl),
                InkWell(
                  onTap: () => setState(() => _checked = !_checked),
                  borderRadius: JadeRadius.all(JadeRadius.sm),
                  child: Padding(
                    padding: const EdgeInsets.all(JadeSpace.xs),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Checkbox(
                          value: _checked,
                          onChanged: (v) => setState(() => _checked = v ?? false),
                        ),
                        const SizedBox(width: JadeSpace.sm),
                        Expanded(
                          child: Padding(
                            padding: const EdgeInsets.only(top: JadeSpace.sm + 2),
                            child: Text(
                              'J’ai lu et j’accepte les conditions générales '
                              'd’utilisation et la politique de confidentialité.',
                              style: JadeType.label
                                  .copyWith(color: jade.body, height: 1.45),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: JadeSpace.lg),
                FilledButton(
                  onPressed: (_checked && !_busy) ? _accept : null,
                  style: FilledButton.styleFrom(
                    backgroundColor: jade.primary,
                    padding: const EdgeInsets.symmetric(vertical: JadeSpace.md),
                    shape: RoundedRectangleBorder(
                        borderRadius: JadeRadius.all(JadeRadius.md)),
                  ),
                  child: const Text('Accepter et continuer'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Ouvre le texte Markdown d'un document légal dans une boite de dialogue
/// défilante (chargé depuis le backend, embarqué dans l'application).
Future<void> _showDoc(
    BuildContext context, ApiClient api, String name, String title) async {
  final jade = context.jade;
  final size = MediaQuery.of(context).size;
  await showDialog<void>(
    context: context,
    builder: (ctx) => Dialog(
      backgroundColor: jade.bg,
      shape: RoundedRectangleBorder(borderRadius: JadeRadius.all(JadeRadius.lg)),
      child: ConstrainedBox(
        constraints: BoxConstraints(
            maxWidth: 720, maxHeight: size.height * 0.85),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(
                  JadeSpace.xxl, JadeSpace.lg, JadeSpace.md, JadeSpace.md),
              child: Row(
                children: [
                  Expanded(
                    child: Text(title,
                        style: JadeType.title.copyWith(color: jade.text)),
                  ),
                  IconButton(
                    icon: Icon(TablerIcons.x, size: 18, color: jade.muted),
                    onPressed: () => Navigator.of(ctx).pop(),
                  ),
                ],
              ),
            ),
            Divider(height: 1, color: jade.border),
            Flexible(
              child: FutureBuilder<String>(
                future: api.legalDoc(name),
                builder: (ctx, snap) {
                  if (!snap.hasData) {
                    return const Padding(
                      padding: EdgeInsets.all(JadeSpace.xxl),
                      child: Center(child: CircularProgressIndicator()),
                    );
                  }
                  return Markdown(
                    data: snap.data!,
                    padding: const EdgeInsets.all(JadeSpace.xxl),
                  );
                },
              ),
            ),
          ],
        ),
      ),
    ),
  );
}

class _DocButton extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  const _DocButton(
      {required this.icon, required this.label, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    return OutlinedButton.icon(
      onPressed: onTap,
      icon: Icon(icon, size: 16),
      label: Align(alignment: Alignment.centerLeft, child: Text(label)),
      style: OutlinedButton.styleFrom(
        foregroundColor: jade.primary,
        side: BorderSide(color: jade.borderStrong),
        padding: const EdgeInsets.symmetric(
            horizontal: JadeSpace.lg, vertical: JadeSpace.md),
        alignment: Alignment.centerLeft,
      ),
    );
  }
}

// ------------------------------------------------------------ onboarding

/// Parcours d'accueil simple en trois temps : présentation, choix d'un dossier
/// de documents (facultatif), puis invitation à poser une première question.
class _Onboarding extends StatefulWidget {
  final ApiClient api;
  final VoidCallback onDone;
  const _Onboarding({required this.api, required this.onDone});

  @override
  State<_Onboarding> createState() => _OnboardingState();
}

class _OnboardingState extends State<_Onboarding> {
  int _step = 0;
  final _pathCtl = TextEditingController();
  String? _folderNotice;
  String? _folderError;
  bool _busy = false;

  static const _last = 2;

  @override
  void dispose() {
    _pathCtl.dispose();
    super.dispose();
  }

  Future<void> _addFolder() async {
    final path = _pathCtl.text.trim();
    if (path.isEmpty) return;
    setState(() {
      _busy = true;
      _folderError = null;
    });
    try {
      await widget.api.addRoot(path);
      setState(() {
        _folderNotice = 'Dossier ajouté. L’indexation démarre en arrière-plan.';
        _pathCtl.clear();
      });
    } on ApiException catch (e) {
      setState(() => _folderError = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _finish() async {
    setState(() => _busy = true);
    try {
      await widget.api.completeOnboarding();
    } catch (_) {}
    widget.onDone();
  }

  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    return Scaffold(
      backgroundColor: jade.bg,
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(JadeSpace.xxl),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 520),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Center(child: const JadeMark(size: 56)),
                const SizedBox(height: JadeSpace.xl),
                _stepContent(context),
                const SizedBox(height: JadeSpace.xl),
                _dots(context),
                const SizedBox(height: JadeSpace.lg),
                Row(
                  children: [
                    if (_step > 0)
                      TextButton(
                        onPressed: _busy
                            ? null
                            : () => setState(() => _step -= 1),
                        child: Text('Précédent',
                            style: JadeType.label.copyWith(color: jade.muted)),
                      ),
                    const Spacer(),
                    if (_step < _last)
                      TextButton(
                        onPressed: _busy ? null : _finish,
                        child: Text('Passer',
                            style: JadeType.label.copyWith(color: jade.faint)),
                      ),
                    const SizedBox(width: JadeSpace.sm),
                    FilledButton(
                      onPressed: _busy
                          ? null
                          : (_step < _last
                              ? () => setState(() => _step += 1)
                              : _finish),
                      style: FilledButton.styleFrom(
                        backgroundColor: jade.primary,
                        padding: const EdgeInsets.symmetric(
                            horizontal: JadeSpace.xxl, vertical: JadeSpace.md),
                      ),
                      child: Text(_step < _last ? 'Suivant' : 'Commencer'),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _stepContent(BuildContext context) {
    switch (_step) {
      case 0:
        return _intro(context);
      case 1:
        return _folders(context);
      default:
        return _ready(context);
    }
  }

  Widget _intro(BuildContext context) {
    final jade = context.jade;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Jade, votre assistant documentaire local',
            textAlign: TextAlign.center,
            style: JadeType.headline.copyWith(color: jade.text)),
        const SizedBox(height: JadeSpace.lg),
        _point(context, TablerIcons.lock,
            'Local et privé : vos documents ne quittent jamais ce poste.'),
        _point(context, TablerIcons.fileText,
            'Jade lit vos dossiers et répond en citant ses sources.'),
        _point(context, TablerIcons.messages,
            'Posez vos questions en langage naturel, comme à un collègue.'),
      ],
    );
  }

  Widget _folders(BuildContext context) {
    final jade = context.jade;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Vos dossiers de documents',
            textAlign: TextAlign.center,
            style: JadeType.headline.copyWith(color: jade.text)),
        const SizedBox(height: JadeSpace.md),
        Text(
          'Indiquez un dossier (local ou réseau) à indexer. Vous pourrez en '
          'ajouter d’autres à tout moment dans les réglages. Cette étape est '
          'facultative : sans dossier, Jade répond comme un assistant général.',
          textAlign: TextAlign.center,
          style: JadeType.label.copyWith(color: jade.muted, height: 1.5),
        ),
        const SizedBox(height: JadeSpace.lg),
        TextField(
          controller: _pathCtl,
          onSubmitted: (_) => _addFolder(),
          decoration: InputDecoration(
            hintText: r'Chemin d’un dossier (ex. \\serveur\partage)',
            isDense: true,
            filled: true,
            fillColor: jade.tile,
            contentPadding: const EdgeInsets.symmetric(
                horizontal: JadeSpace.md, vertical: JadeSpace.md),
            enabledBorder: OutlineInputBorder(
              borderRadius: JadeRadius.all(JadeRadius.sm),
              borderSide: BorderSide.none,
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: JadeRadius.all(JadeRadius.sm),
              borderSide: BorderSide(color: jade.primary, width: 1.5),
            ),
          ),
          style: JadeType.label.copyWith(color: jade.text),
        ),
        const SizedBox(height: JadeSpace.sm),
        Align(
          alignment: Alignment.centerLeft,
          child: OutlinedButton.icon(
            onPressed: _busy ? null : _addFolder,
            icon: const Icon(TablerIcons.folderPlus, size: 16),
            label: const Text('Ajouter ce dossier'),
            style: OutlinedButton.styleFrom(
              foregroundColor: jade.primary,
              side: BorderSide(color: jade.borderStrong),
            ),
          ),
        ),
        if (_folderNotice != null)
          Padding(
            padding: const EdgeInsets.only(top: JadeSpace.sm),
            child: Text(_folderNotice!,
                style: JadeType.caption.copyWith(color: jade.success)),
          ),
        if (_folderError != null)
          Padding(
            padding: const EdgeInsets.only(top: JadeSpace.sm),
            child: Text(_folderError!,
                style: JadeType.caption.copyWith(color: jade.danger)),
          ),
      ],
    );
  }

  Widget _ready(BuildContext context) {
    final jade = context.jade;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Tout est prêt',
            textAlign: TextAlign.center,
            style: JadeType.headline.copyWith(color: jade.text)),
        const SizedBox(height: JadeSpace.md),
        Text(
          'Posez votre première question à Jade. Il cherchera dans vos '
          'documents et, si besoin, sur le web, en citant toujours ses sources.',
          textAlign: TextAlign.center,
          style: JadeType.label.copyWith(color: jade.muted, height: 1.5),
        ),
      ],
    );
  }

  Widget _point(BuildContext context, IconData icon, String text) {
    final jade = context.jade;
    return Padding(
      padding: const EdgeInsets.only(bottom: JadeSpace.md),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 18, color: jade.primary),
          const SizedBox(width: JadeSpace.md),
          Expanded(
            child: Text(text,
                style: JadeType.label.copyWith(color: jade.body, height: 1.45)),
          ),
        ],
      ),
    );
  }

  Widget _dots(BuildContext context) {
    final jade = context.jade;
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: List.generate(_last + 1, (i) {
        final active = i == _step;
        return AnimatedContainer(
          duration: context.motion(const Duration(milliseconds: 200)),
          curve: Curves.easeOutCubic,
          margin: const EdgeInsets.symmetric(horizontal: JadeSpace.xs),
          width: active ? 20 : 8,
          height: 8,
          decoration: BoxDecoration(
            color: active ? jade.primary : jade.border,
            borderRadius: JadeRadius.all(JadeRadius.pill),
          ),
        );
      }),
    );
  }
}
