/// Réglages : dossiers à indexer (admin, protégé par mot de passe), état de
/// l'index, réindexation, et suppression des données de l'utilisateur
/// (historique de conversations, mémoire).
library;

import 'package:flutter/material.dart';

import 'api.dart';
import 'design.dart';
import 'models.dart';
import 'tabler.dart';
import 'theme.dart';

Future<void> showSettingsDialog(
  BuildContext context, {
  required ApiClient api,
  required VoidCallback onHistoryCleared,
}) {
  return showDialog(
    context: context,
    builder: (_) => Dialog(
      backgroundColor: Colors.transparent,
      insetPadding: const EdgeInsets.all(JadeSpace.xxl),
      child: SettingsView(api: api, onHistoryCleared: onHistoryCleared),
    ),
  );
}

class SettingsView extends StatefulWidget {
  final ApiClient api;
  final VoidCallback onHistoryCleared;
  const SettingsView(
      {super.key, required this.api, required this.onHistoryCleared});

  @override
  State<SettingsView> createState() => _SettingsViewState();
}

class _SettingsViewState extends State<SettingsView> {
  IndexSettings? _settings;
  bool _unlocked = false;
  bool _busy = false;
  String? _pwdError;
  String? _rootError;
  String _notice = '';

  final _pwdCtl = TextEditingController();
  final _pathCtl = TextEditingController();

  String get _pwd => _pwdCtl.text;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _pwdCtl.dispose();
    _pathCtl.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final s = await widget.api.getSettings();
      if (mounted) setState(() => _settings = s);
    } catch (_) {}
  }

  Future<void> _unlock() async {
    setState(() {
      _busy = true;
      _pwdError = null;
    });
    try {
      final ok = await widget.api.unlockSettings(_pwd);
      setState(() {
        _unlocked = ok;
        _pwdError = ok ? null : 'Mot de passe incorrect.';
      });
    } catch (e) {
      setState(() => _pwdError = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _addRoot() async {
    final path = _pathCtl.text.trim();
    if (path.isEmpty) return;
    setState(() {
      _busy = true;
      _rootError = null;
    });
    try {
      final s = await widget.api.addRoot(_pwd, path);
      setState(() {
        _settings = s;
        _pathCtl.clear();
      });
    } on ApiException catch (e) {
      setState(() => _rootError = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _removeRoot(String path) async {
    setState(() => _busy = true);
    try {
      final s = await widget.api.removeRoot(_pwd, path);
      setState(() => _settings = s);
    } catch (_) {
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _reindex({bool full = false}) async {
    setState(() => _busy = true);
    try {
      await widget.api.reindex(_pwd, full: full);
      setState(() => _notice = full
          ? 'Réindexation complète lancée en arrière-plan.'
          : 'Réindexation lancée en arrière-plan.');
      await _load();
    } catch (_) {
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _clearHistory() async {
    final ok = await _confirm(
      'Supprimer tout l’historique ?',
      'Toutes vos conversations et dossiers seront définitivement supprimés. '
          'Cette action est irréversible.',
      'Tout supprimer',
    );
    if (ok != true) return;
    setState(() => _busy = true);
    try {
      final n = await widget.api.clearConversations();
      widget.onHistoryCleared();
      setState(() => _notice = '$n conversation(s) supprimée(s).');
    } catch (_) {
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _clearMemory() async {
    final ok = await _confirm(
      'Effacer la mémoire ?',
      'Les faits mémorisés sur vous entre conversations seront supprimés.',
      'Effacer',
    );
    if (ok != true) return;
    setState(() => _busy = true);
    try {
      await widget.api.clearMemory();
      setState(() => _notice = 'Mémoire effacée.');
    } catch (_) {
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<bool?> _confirm(String title, String body, String confirmLabel) {
    final jade = context.jade;
    return showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        shape:
            RoundedRectangleBorder(borderRadius: JadeRadius.all(JadeRadius.lg)),
        title: Text(title),
        content: Text(body),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Annuler')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: jade.danger),
            onPressed: () => Navigator.pop(ctx, true),
            child: Text(confirmLabel),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    return Container(
      width: 560,
      constraints: BoxConstraints(
          maxHeight: MediaQuery.of(context).size.height * 0.86),
      decoration: BoxDecoration(
        color: jade.bg,
        borderRadius: JadeRadius.all(JadeRadius.lg),
        border: Border.all(color: jade.border),
        boxShadow: JadeElevation.lift(context),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // en-tête
          Padding(
            padding: const EdgeInsets.fromLTRB(
                JadeSpace.xxl, JadeSpace.lg, JadeSpace.md, JadeSpace.md),
            child: Row(
              children: [
                Icon(TablerIcons.settings, size: 19, color: jade.primary),
                const SizedBox(width: JadeSpace.md),
                Text('Réglages',
                    style: JadeType.title.copyWith(color: jade.text)),
                const Spacer(),
                _IconBtn(
                  icon: TablerIcons.x,
                  tooltip: 'Fermer',
                  onTap: () => Navigator.of(context).pop(),
                ),
              ],
            ),
          ),
          Divider(height: 1, color: jade.border),
          Flexible(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(JadeSpace.xxl),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (_notice.isNotEmpty) _NoticeBar(_notice),
                  _indexSection(context),
                  const SizedBox(height: JadeSpace.xxl),
                  _dataSection(context),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  // -------------------------------------------------- section indexation

  Widget _indexSection(BuildContext context) {
    return _Card(
      icon: TablerIcons.folder,
      title: 'Dossiers indexés',
      subtitle: 'Administrateur',
      child: !_unlocked ? _lockGate(context) : _rootsEditor(context),
    );
  }

  Widget _lockGate(BuildContext context) {
    final jade = context.jade;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'La configuration de l’indexation est protégée par le mot de passe '
          'administrateur.',
          style: JadeType.label.copyWith(color: jade.muted, height: 1.5),
        ),
        const SizedBox(height: JadeSpace.md),
        Row(
          children: [
            Expanded(
              child: TextField(
                controller: _pwdCtl,
                obscureText: true,
                onSubmitted: (_) => _unlock(),
                decoration: _fieldDecoration(context, 'Mot de passe'),
                style: JadeType.label.copyWith(color: jade.text),
              ),
            ),
            const SizedBox(width: JadeSpace.sm),
            FilledButton(
              onPressed: _busy ? null : _unlock,
              style: FilledButton.styleFrom(
                backgroundColor: jade.primary,
                padding: const EdgeInsets.symmetric(
                    horizontal: JadeSpace.lg, vertical: JadeSpace.md),
              ),
              child: const Text('Déverrouiller'),
            ),
          ],
        ),
        if (_pwdError != null)
          Padding(
            padding: const EdgeInsets.only(top: JadeSpace.sm),
            child: Text(_pwdError!,
                style: JadeType.caption.copyWith(color: jade.danger)),
          ),
      ],
    );
  }

  Widget _rootsEditor(BuildContext context) {
    final jade = context.jade;
    final roots = _settings?.roots ?? const [];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // état de l'index
        Row(
          children: [
            Icon(
                _settings?.indexing == true
                    ? TablerIcons.refresh
                    : TablerIcons.fileText,
                size: 14,
                color: jade.muted),
            const SizedBox(width: JadeSpace.sm),
            Text(
              _settings == null
                  ? '…'
                  : '${_settings!.chunksIndexed} extraits indexés'
                      '${_settings!.indexing ? ' · indexation en cours…' : ''}',
              style: JadeType.caption
                  .merge(JadeType.tabular)
                  .copyWith(color: jade.muted),
            ),
          ],
        ),
        const SizedBox(height: JadeSpace.md),
        // liste des dossiers
        if (roots.isEmpty)
          Container(
            padding: const EdgeInsets.all(JadeSpace.md),
            decoration: BoxDecoration(
              color: jade.tile,
              borderRadius: JadeRadius.all(JadeRadius.sm),
            ),
            child: Row(
              children: [
                Icon(TablerIcons.messages, size: 15, color: jade.secondary),
                const SizedBox(width: JadeSpace.sm),
                Expanded(
                  child: Text(
                    'Aucun dossier indexé — Jade répond comme un assistant '
                    'général (web + connaissances), sans documents.',
                    style: JadeType.caption
                        .copyWith(color: jade.muted, height: 1.5),
                  ),
                ),
              ],
            ),
          )
        else
          for (final r in roots) _rootRow(context, r),
        const SizedBox(height: JadeSpace.md),
        // ajout d'un dossier
        Row(
          children: [
            Expanded(
              child: TextField(
                controller: _pathCtl,
                onSubmitted: (_) => _addRoot(),
                decoration: _fieldDecoration(
                    context, r'Chemin d’un dossier (ex. \\serveur\partage)'),
                style: JadeType.label.copyWith(color: jade.text),
              ),
            ),
            const SizedBox(width: JadeSpace.sm),
            OutlinedButton.icon(
              onPressed: _busy ? null : _addRoot,
              icon: const Icon(TablerIcons.folderPlus, size: 16),
              label: const Text('Ajouter'),
              style: OutlinedButton.styleFrom(
                foregroundColor: jade.primary,
                side: BorderSide(color: jade.borderStrong),
                padding: const EdgeInsets.symmetric(
                    horizontal: JadeSpace.md, vertical: JadeSpace.md),
              ),
            ),
          ],
        ),
        if (_rootError != null)
          Padding(
            padding: const EdgeInsets.only(top: JadeSpace.sm),
            child: Text(_rootError!,
                style: JadeType.caption.copyWith(color: jade.danger)),
          ),
        const SizedBox(height: JadeSpace.lg),
        // réindexation
        Row(
          children: [
            FilledButton.icon(
              onPressed: _busy ? null : () => _reindex(),
              icon: const Icon(TablerIcons.refresh, size: 16),
              label: const Text('Réindexer'),
              style: FilledButton.styleFrom(
                backgroundColor: jade.primary,
                padding: const EdgeInsets.symmetric(
                    horizontal: JadeSpace.lg, vertical: JadeSpace.md),
              ),
            ),
            const SizedBox(width: JadeSpace.sm),
            TextButton(
              onPressed: _busy ? null : () => _reindex(full: true),
              child: Text('Réindexation complète',
                  style: JadeType.label.copyWith(color: jade.muted)),
            ),
          ],
        ),
      ],
    );
  }

  Widget _rootRow(BuildContext context, IndexRoot r) {
    final jade = context.jade;
    return Padding(
      padding: const EdgeInsets.only(bottom: JadeSpace.sm),
      child: Container(
        padding: const EdgeInsets.fromLTRB(
            JadeSpace.md, JadeSpace.sm, JadeSpace.sm, JadeSpace.sm),
        decoration: BoxDecoration(
          color: jade.card,
          borderRadius: JadeRadius.all(JadeRadius.sm),
          border: Border.all(color: jade.border),
        ),
        child: Row(
          children: [
            Container(
              width: 8,
              height: 8,
              decoration: BoxDecoration(
                color: r.online ? jade.success : jade.faint,
                shape: BoxShape.circle,
              ),
            ),
            const SizedBox(width: JadeSpace.md),
            Expanded(
              child: Text(r.path,
                  overflow: TextOverflow.ellipsis,
                  style: JadeType.label.copyWith(color: jade.body)),
            ),
            if (!r.online)
              Padding(
                padding: const EdgeInsets.only(right: JadeSpace.sm),
                child: Text('hors ligne',
                    style: JadeType.caption.copyWith(color: jade.faint)),
              ),
            _IconBtn(
              icon: TablerIcons.trash,
              tooltip: 'Retirer',
              danger: true,
              onTap: _busy ? null : () => _removeRoot(r.path),
            ),
          ],
        ),
      ),
    );
  }

  // -------------------------------------------------- section données

  Widget _dataSection(BuildContext context) {
    final jade = context.jade;
    return _Card(
      icon: TablerIcons.trash,
      title: 'Mes données',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _DangerRow(
            title: 'Supprimer tout l’historique',
            subtitle: 'Toutes les conversations et dossiers de ce compte.',
            buttonLabel: 'Supprimer',
            onTap: _busy ? null : _clearHistory,
          ),
          Divider(height: JadeSpace.xxl, color: jade.border),
          _DangerRow(
            title: 'Effacer la mémoire',
            subtitle: 'Faits mémorisés sur vous entre conversations.',
            buttonLabel: 'Effacer',
            onTap: _busy ? null : _clearMemory,
          ),
        ],
      ),
    );
  }

  InputDecoration _fieldDecoration(BuildContext context, String hint) {
    final jade = context.jade;
    return InputDecoration(
      hintText: hint,
      hintStyle: JadeType.label.copyWith(color: jade.faint),
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
    );
  }
}

// ---------------------------------------------------------------- widgets

class _Card extends StatelessWidget {
  final IconData icon;
  final String title;
  final String? subtitle;
  final Widget child;
  const _Card(
      {required this.icon,
      required this.title,
      this.subtitle,
      required this.child});

  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    return Container(
      padding: const EdgeInsets.all(JadeSpace.lg),
      decoration: BoxDecoration(
        color: jade.panel,
        borderRadius: JadeRadius.all(JadeRadius.md),
        border: Border.all(color: jade.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, size: 16, color: jade.body),
              const SizedBox(width: JadeSpace.sm),
              Text(title, style: JadeType.subtitle.copyWith(color: jade.text)),
              if (subtitle != null) ...[
                const SizedBox(width: JadeSpace.sm),
                Container(
                  padding: const EdgeInsets.symmetric(
                      horizontal: JadeSpace.sm, vertical: 1),
                  decoration: BoxDecoration(
                    color: jade.tile,
                    borderRadius: JadeRadius.all(JadeRadius.pill),
                  ),
                  child: Text(subtitle!,
                      style: JadeType.caption.copyWith(color: jade.muted)),
                ),
              ],
            ],
          ),
          const SizedBox(height: JadeSpace.lg),
          child,
        ],
      ),
    );
  }
}

class _DangerRow extends StatelessWidget {
  final String title;
  final String subtitle;
  final String buttonLabel;
  final VoidCallback? onTap;
  const _DangerRow(
      {required this.title,
      required this.subtitle,
      required this.buttonLabel,
      required this.onTap});

  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    return Row(
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: JadeType.label.copyWith(color: jade.text)),
              const SizedBox(height: 2),
              Text(subtitle,
                  style: JadeType.caption.copyWith(color: jade.muted)),
            ],
          ),
        ),
        const SizedBox(width: JadeSpace.md),
        OutlinedButton(
          onPressed: onTap,
          style: OutlinedButton.styleFrom(
            foregroundColor: jade.danger,
            side: BorderSide(color: jade.danger.withValues(alpha: 0.5)),
            padding: const EdgeInsets.symmetric(
                horizontal: JadeSpace.lg, vertical: JadeSpace.sm + 2),
          ),
          child: Text(buttonLabel),
        ),
      ],
    );
  }
}

class _NoticeBar extends StatelessWidget {
  final String text;
  const _NoticeBar(this.text);
  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    return Container(
      margin: const EdgeInsets.only(bottom: JadeSpace.lg),
      padding: const EdgeInsets.all(JadeSpace.md),
      decoration: BoxDecoration(
        color: jade.primaryContainer,
        borderRadius: JadeRadius.all(JadeRadius.sm),
      ),
      child: Text(text,
          style: JadeType.caption.copyWith(color: jade.onPrimaryContainer)),
    );
  }
}

class _IconBtn extends StatelessWidget {
  final IconData icon;
  final String tooltip;
  final VoidCallback? onTap;
  final bool danger;
  const _IconBtn(
      {required this.icon,
      required this.tooltip,
      required this.onTap,
      this.danger = false});

  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    return Tooltip(
      message: tooltip,
      child: Material(
        color: Colors.transparent,
        shape: const CircleBorder(),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          hoverColor: danger
              ? jade.danger.withValues(alpha: 0.14)
              : jade.tile,
          child: Padding(
            padding: const EdgeInsets.all(JadeSpace.sm),
            child: Icon(icon,
                size: 16, color: danger ? jade.danger : jade.muted),
          ),
        ),
      ),
    );
  }
}
