/// Réglages : dossiers à indexer, état de l'index, réindexation, et
/// suppression des données de l'utilisateur (historique, mémoire).
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
  VoidCallback? onProfileChanged,
}) {
  return showDialog(
    context: context,
    builder: (_) => Dialog(
      backgroundColor: Colors.transparent,
      insetPadding: const EdgeInsets.all(JadeSpace.xxl),
      child: SettingsView(
        api: api,
        onHistoryCleared: onHistoryCleared,
        onProfileChanged: onProfileChanged,
      ),
    ),
  );
}

/// Contenu de la boite de dialogue des reglages : dossiers a indexer,
/// reindexation, suppression de l'historique. Ouverte via [showSettingsDialog].
class SettingsView extends StatefulWidget {
  final ApiClient api;
  final VoidCallback onHistoryCleared;
  /// Rappelé après un changement de nom affiché — permet à l'écran hôte de
  /// rafraîchir le statut (le pied de la barre latérale affiche ce nom).
  final VoidCallback? onProfileChanged;
  const SettingsView(
      {super.key,
      required this.api,
      required this.onHistoryCleared,
      this.onProfileChanged});

  @override
  State<SettingsView> createState() => _SettingsViewState();
}

class _SettingsViewState extends State<SettingsView> {
  IndexSettings? _settings;
  HealthInfo? _health;
  Profile? _profile;
  bool _busy = false;
  String? _rootError;
  String _notice = '';

  final _pathCtl = TextEditingController();
  final _restoreCtl = TextEditingController();
  final _ollamaCtl = TextEditingController();
  final _searxngCtl = TextEditingController();
  final _cfIdCtl = TextEditingController();
  final _cfSecretCtl = TextEditingController();
  final _nameCtl = TextEditingController();
  ConnConfig? _conn;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _pathCtl.dispose();
    _restoreCtl.dispose();
    _ollamaCtl.dispose();
    _searxngCtl.dispose();
    _cfIdCtl.dispose();
    _cfSecretCtl.dispose();
    _nameCtl.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final s = await widget.api.getSettings();
      if (mounted) setState(() => _settings = s);
    } catch (_) {}
    try {
      final h = await widget.api.health();
      if (mounted) setState(() => _health = h);
    } catch (_) {}
    try {
      final c = await widget.api.getConfig();
      if (mounted) {
        setState(() => _conn = c);
        _ollamaCtl.text = c.ollamaUrl;
        _searxngCtl.text = c.searxngUrl;
        _cfIdCtl.text = c.cfClientId;
      }
    } catch (_) {}
    try {
      final p = await widget.api.getProfile();
      if (mounted) {
        setState(() => _profile = p);
        _nameCtl.text = p.isCustom ? p.displayName : '';
      }
    } catch (_) {}
  }

  // ---------------------------------------------------------------- profil

  Future<void> _saveProfile([String? overrideName]) async {
    setState(() => _busy = true);
    try {
      final p = await widget.api.setProfile(overrideName ?? _nameCtl.text.trim());
      if (!mounted) return;
      setState(() {
        _profile = p;
        _nameCtl.text = p.isCustom ? p.displayName : '';
        _notice = p.isCustom
            ? 'Jade vous appellera désormais « ${p.displayName} ».'
            : 'Nom réinitialisé — Jade utilise votre nom Windows.';
      });
      widget.onProfileChanged?.call();
    } on ApiException catch (e) {
      setState(() => _notice = 'Enregistrement impossible : ${e.message}');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _saveConfig() async {
    setState(() => _busy = true);
    try {
      final res = await widget.api.setConfig(
        ollamaUrl: _ollamaCtl.text.trim(),
        searxngUrl: _searxngCtl.text.trim(),
        cfClientId: _cfIdCtl.text.trim(),
        cfSecret: _cfSecretCtl.text.trim(),
      );
      _cfSecretCtl.clear();
      final ok = res['llm_ok'] == true;
      if (!mounted) return;
      setState(() => _notice = ok
          ? 'Identifiants enregistrés — serveur d’IA joignable.'
          : 'Identifiants enregistrés, mais le serveur d’IA reste injoignable : '
              '${res['llm_error'] ?? 'vérifiez les valeurs'}.');
      await _load();
    } on ApiException catch (e) {
      setState(() => _notice = 'Enregistrement impossible : ${e.message}');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  // ---------------------------------------------- sauvegarde / restauration

  Future<void> _backup() async {
    setState(() => _busy = true);
    try {
      final res = await widget.api.backupChats();
      final path = (res['path'] ?? '').toString();
      final n = res['conversations'] ?? 0;
      if (!mounted) return;
      setState(() => _notice =
          '$n conversation(s) sauvegardée(s).\nFichier : $path');
      // révèle le fichier dans l'Explorateur pour que l'utilisateur le récupère
      if (path.isNotEmpty) {
        try {
          await widget.api.openFile(path, reveal: true);
        } catch (_) {}
      }
    } on ApiException catch (e) {
      setState(() => _notice = 'Sauvegarde impossible : ${e.message}');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _restore() async {
    final path = _restoreCtl.text.trim();
    if (path.isEmpty) return;
    final ok = await _confirm(
      'Restaurer cette sauvegarde ?',
      'Les conversations du fichier seront ajoutées à celles déjà présentes '
          '(aucune conversation existante n’est supprimée).',
      'Restaurer',
      danger: false,
    );
    if (ok != true) return;
    setState(() => _busy = true);
    try {
      final res = await widget.api.restoreChats(path);
      widget.onHistoryCleared(); // recharge la liste des conversations
      if (!mounted) return;
      setState(() {
        _notice = '${res['conversations'] ?? 0} conversation(s) et '
            '${res['folders'] ?? 0} dossier(s) restauré(s).';
        _restoreCtl.clear();
      });
    } on ApiException catch (e) {
      setState(() => _notice = 'Restauration impossible : ${e.message}');
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
      final s = await widget.api.addRoot(path);
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
      final s = await widget.api.removeRoot(path);
      setState(() => _settings = s);
    } catch (_) {
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _reindex({bool full = false}) async {
    setState(() => _busy = true);
    try {
      await widget.api.reindex(full: full);
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

  Future<bool?> _confirm(String title, String body, String confirmLabel,
      {bool danger = true}) {
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
            style: FilledButton.styleFrom(
                backgroundColor: danger ? jade.danger : jade.primary),
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
    final size = MediaQuery.of(context).size;
    return Container(
      // largeur bornée (et non fixe) : évite le débordement horizontal sur une
      // fenêtre étroite (< 560 px + marges).
      width: size.width < 620 ? size.width - JadeSpace.xxl * 2 : 560,
      constraints: BoxConstraints(maxHeight: size.height * 0.86),
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
                  _statusSection(context),
                  const SizedBox(height: JadeSpace.xxl),
                  _profileSection(context),
                  const SizedBox(height: JadeSpace.xxl),
                  _connSection(context),
                  const SizedBox(height: JadeSpace.xxl),
                  _indexSection(context),
                  const SizedBox(height: JadeSpace.xxl),
                  _backupSection(context),
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
      child: _rootsEditor(context),
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

  // -------------------------------------------------- section état système

  Widget _statusSection(BuildContext context) {
    final jade = context.jade;
    final h = _health;
    return _Card(
      icon: TablerIcons.activity,
      title: 'État du système',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (h == null)
            Text('Diagnostic en cours…',
                style: JadeType.caption.copyWith(color: jade.muted))
          else ...[
            _statusRow(
              context,
              "Serveur d'IA",
              h.llmOk != false,
              h.llmOk == false
                  ? (h.llmError.isNotEmpty ? 'injoignable' : 'injoignable')
                  : 'joignable',
            ),
            _statusRow(context, 'Modèles de recherche', h.modelsReady,
                h.modelsReady ? 'prêts' : 'en préparation'),
            _statusRow(context, 'Espace disque', !h.diskLow,
                '${h.diskFreeGb.toStringAsFixed(1)} Go libres'),
            _statusRow(context, 'Index documentaire', true,
                '${h.chunksIndexed} extraits${h.indexing ? ' · indexation…' : ''}'),
            if (h.llmOk == false && h.llmError.isNotEmpty) ...[
              const SizedBox(height: JadeSpace.sm),
              Text(h.llmError,
                  style: JadeType.caption.copyWith(color: jade.muted, height: 1.5)),
            ],
          ],
          const SizedBox(height: JadeSpace.md),
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              onPressed: _busy ? null : _load,
              icon: const Icon(TablerIcons.refresh, size: 15),
              label: const Text('Actualiser'),
              style: TextButton.styleFrom(foregroundColor: jade.muted),
            ),
          ),
        ],
      ),
    );
  }

  Widget _statusRow(BuildContext context, String label, bool ok, String value) {
    final jade = context.jade;
    final color = ok ? jade.success : jade.danger;
    return Padding(
      padding: const EdgeInsets.only(bottom: JadeSpace.sm),
      child: Row(
        children: [
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          ),
          const SizedBox(width: JadeSpace.md),
          Expanded(
            child: Text(label, style: JadeType.label.copyWith(color: jade.body)),
          ),
          Text(value,
              style: JadeType.caption
                  .merge(JadeType.tabular)
                  .copyWith(color: ok ? jade.muted : jade.danger)),
        ],
      ),
    );
  }

  // -------------------------------------------------------- section profil

  Widget _profileSection(BuildContext context) {
    final jade = context.jade;
    final p = _profile;
    return _Card(
      icon: TablerIcons.edit,
      title: 'Nom affiché',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            'Le nom que Jade utilise pour s’adresser à vous. Laissez vide pour '
            'utiliser le nom de votre compte Windows.',
            style: JadeType.caption.copyWith(color: jade.muted, height: 1.5),
          ),
          const SizedBox(height: JadeSpace.md),
          TextField(
            controller: _nameCtl,
            onSubmitted: (_) {
              if (!_busy) _saveProfile();
            },
            decoration: _fieldDecoration(
              context,
              p == null
                  ? '…'
                  : (p.isCustom
                      ? ''
                      : 'Actuellement : « ${p.displayName} » (nom Windows)'),
            ),
            style: JadeType.label.copyWith(color: jade.text),
          ),
          const SizedBox(height: JadeSpace.md),
          Row(
            children: [
              FilledButton.icon(
                onPressed: _busy ? null : () => _saveProfile(),
                icon: const Icon(TablerIcons.circleCheck, size: 16),
                label: const Text('Enregistrer'),
                style: FilledButton.styleFrom(
                  backgroundColor: jade.primary,
                  padding: const EdgeInsets.symmetric(
                      horizontal: JadeSpace.lg, vertical: JadeSpace.md),
                ),
              ),
              if (p?.isCustom == true) ...[
                const SizedBox(width: JadeSpace.sm),
                TextButton(
                  onPressed: _busy ? null : () => _saveProfile(''),
                  child: Text('Réinitialiser au nom Windows',
                      style: JadeType.label.copyWith(color: jade.muted)),
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }

  // ---------------------------------------- section connexion aux services

  Widget _connSection(BuildContext context) {
    final jade = context.jade;
    return _Card(
      icon: TablerIcons.world,
      title: 'Connexion aux services',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            'Adresses et identifiants Cloudflare Access fournis par Jade. '
            'Le même couple Client ID / Secret sert au serveur d’IA et à la '
            'recherche web. Modifiable sans réinstaller.',
            style: JadeType.caption.copyWith(color: jade.muted, height: 1.5),
          ),
          const SizedBox(height: JadeSpace.md),
          _field(context, 'Serveur d’IA (OLLAMA_URL)', _ollamaCtl,
              hint: 'https://llm.example.com'),
          const SizedBox(height: JadeSpace.md),
          _field(context, 'Recherche web (SEARXNG_URL, facultatif)', _searxngCtl,
              hint: 'https://search.example.com'),
          const SizedBox(height: JadeSpace.md),
          _field(context, 'Cloudflare Access — Client ID', _cfIdCtl),
          const SizedBox(height: JadeSpace.md),
          _field(
            context,
            'Cloudflare Access — Secret',
            _cfSecretCtl,
            obscure: true,
            hint: _conn?.cfSecretSet == true
                ? 'Défini — laisser vide pour conserver'
                : 'Non défini',
          ),
          const SizedBox(height: JadeSpace.lg),
          Align(
            alignment: Alignment.centerLeft,
            child: FilledButton.icon(
              onPressed: _busy ? null : _saveConfig,
              icon: const Icon(TablerIcons.circleCheck, size: 16),
              label: const Text('Enregistrer et tester'),
              style: FilledButton.styleFrom(
                backgroundColor: jade.primary,
                padding: const EdgeInsets.symmetric(
                    horizontal: JadeSpace.lg, vertical: JadeSpace.md),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _field(BuildContext context, String label, TextEditingController ctl,
      {String? hint, bool obscure = false}) {
    final jade = context.jade;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: JadeType.caption.copyWith(color: jade.muted)),
        const SizedBox(height: JadeSpace.xs + 2),
        TextField(
          controller: ctl,
          obscureText: obscure,
          decoration: _fieldDecoration(context, hint ?? ''),
          style: JadeType.label.copyWith(color: jade.text),
        ),
      ],
    );
  }

  // ---------------------------------------- section sauvegarde / migration

  Widget _backupSection(BuildContext context) {
    final jade = context.jade;
    return _Card(
      icon: TablerIcons.database,
      title: 'Sauvegarde et migration',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            'Exportez vos conversations dans un fichier que vous conservez '
            '(clé USB, dossier réseau) pour les restaurer sur un autre poste. '
            'Ce fichier contient vos échanges en clair : gardez-le en lieu sûr.',
            style: JadeType.caption.copyWith(color: jade.muted, height: 1.5),
          ),
          const SizedBox(height: JadeSpace.md),
          Align(
            alignment: Alignment.centerLeft,
            child: FilledButton.icon(
              onPressed: _busy ? null : _backup,
              icon: const Icon(TablerIcons.download, size: 16),
              label: const Text('Sauvegarder mes conversations'),
              style: FilledButton.styleFrom(
                backgroundColor: jade.primary,
                padding: const EdgeInsets.symmetric(
                    horizontal: JadeSpace.lg, vertical: JadeSpace.md),
              ),
            ),
          ),
          const SizedBox(height: JadeSpace.lg),
          Text('Restaurer depuis un fichier de sauvegarde (.jadebak) :',
              style: JadeType.caption.copyWith(color: jade.muted)),
          const SizedBox(height: JadeSpace.sm),
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _restoreCtl,
                  onSubmitted: (_) => _restore(),
                  decoration: _fieldDecoration(
                      context, r'Chemin complet du fichier .jadebak'),
                  style: JadeType.label.copyWith(color: jade.text),
                ),
              ),
              const SizedBox(width: JadeSpace.sm),
              OutlinedButton.icon(
                onPressed: _busy ? null : _restore,
                icon: const Icon(TablerIcons.upload, size: 16),
                label: const Text('Restaurer'),
                style: OutlinedButton.styleFrom(
                  foregroundColor: jade.primary,
                  side: BorderSide(color: jade.borderStrong),
                  padding: const EdgeInsets.symmetric(
                      horizontal: JadeSpace.md, vertical: JadeSpace.md),
                ),
              ),
            ],
          ),
        ],
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
  final Widget child;
  const _Card({required this.icon, required this.title, required this.child});

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
