/// Mise à jour de l'application (postes clients, mode « manual »).
///
/// La détection vit côté backend (interroge les *releases* Gitea) ; l'UI se
/// contente d'afficher un bouton quand une version est disponible, puis un
/// dialogue qui télécharge l'installateur (progression) et le lance. Sur les
/// serveurs RDS (mode « scheduled »), rien ne s'affiche : une tâche planifiée
/// applique la mise à jour hors session.
library;

import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';

import 'api.dart';
import 'design.dart';
import 'models.dart';
import 'tabler.dart';
import 'theme.dart';

/// Pastille « Mise à jour disponible » à placer dans la barre latérale.
class UpdateButton extends StatelessWidget {
  final ApiClient api;
  final UpdateInfo info;
  const UpdateButton({super.key, required this.api, required this.info});

  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    return FocusRing(
      radius: JadeRadius.md,
      child: Material(
        color: jade.secondary.withValues(alpha: 0.12),
        borderRadius: JadeRadius.all(JadeRadius.md),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: () => showUpdateDialog(context, api, info),
          hoverColor: jade.secondary.withValues(alpha: 0.10),
          child: Padding(
            padding: const EdgeInsets.symmetric(
                horizontal: JadeSpace.md, vertical: JadeSpace.sm + 2),
            child: Row(
              children: [
                Icon(TablerIcons.download, size: 16, color: jade.secondary),
                const SizedBox(width: JadeSpace.sm + 1),
                Expanded(
                  child: Text('Mise à jour disponible',
                      overflow: TextOverflow.ellipsis,
                      style: JadeType.label.copyWith(
                          color: jade.secondary, fontWeight: FontWeight.w600)),
                ),
                Text(info.latest,
                    style: JadeType.caption
                        .merge(JadeType.tabular)
                        .copyWith(color: jade.secondary)),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

Future<void> showUpdateDialog(
    BuildContext context, ApiClient api, UpdateInfo info) {
  return showDialog<void>(
    context: context,
    barrierDismissible: false,
    builder: (_) => _UpdateDialog(api: api, info: info),
  );
}

enum _Phase { intro, downloading, ready, installing, error }

class _UpdateDialog extends StatefulWidget {
  final ApiClient api;
  final UpdateInfo info;
  const _UpdateDialog({required this.api, required this.info});

  @override
  State<_UpdateDialog> createState() => _UpdateDialogState();
}

class _UpdateDialogState extends State<_UpdateDialog> {
  _Phase _phase = _Phase.intro;
  DownloadProgress? _progress;
  Timer? _poll;
  String _error = '';

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  Future<void> _startDownload() async {
    setState(() {
      _phase = _Phase.downloading;
      _error = '';
    });
    try {
      await widget.api.startDownload();
    } catch (e) {
      return _fail(e.toString());
    }
    _poll = Timer.periodic(const Duration(milliseconds: 600), (_) => _tick());
  }

  Future<void> _tick() async {
    final DownloadProgress p;
    try {
      p = await widget.api.downloadProgress();
    } catch (_) {
      return; // souci momentané : on retentera au prochain tick
    }
    if (!mounted) return;
    setState(() => _progress = p);
    if (p.state == 'ready') {
      _poll?.cancel();
      setState(() => _phase = _Phase.ready);
    } else if (p.state == 'error') {
      _poll?.cancel();
      _fail(p.error.isEmpty ? 'Téléchargement échoué.' : p.error);
    }
  }

  void _fail(String msg) {
    if (!mounted) return;
    setState(() {
      _phase = _Phase.error;
      _error = msg;
    });
  }

  Future<void> _install() async {
    setState(() => _phase = _Phase.installing);
    try {
      await widget.api.applyUpdate();
    } catch (e) {
      return _fail(e.toString());
    }
    // L'installateur (Inno) prend la main : on laisse un instant puis on ferme
    // l'application pour libérer les fichiers.
    await Future<void>.delayed(const Duration(milliseconds: 1400));
    exit(0);
  }

  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    return AlertDialog(
      shape: RoundedRectangleBorder(borderRadius: JadeRadius.all(JadeRadius.lg)),
      title: Row(
        children: [
          Icon(TablerIcons.download, size: 20, color: jade.secondary),
          const SizedBox(width: JadeSpace.sm + 2),
          const Text('Mise à jour de Jade'),
        ],
      ),
      content: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 420),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: _body(context),
        ),
      ),
      actions: _actions(context),
    );
  }

  List<Widget> _body(BuildContext context) {
    final jade = context.jade;
    final info = widget.info;
    final versions = Row(
      children: [
        _VersionChip(label: info.current, muted: true),
        const SizedBox(width: JadeSpace.sm),
        Icon(TablerIcons.arrowRight, size: 15, color: jade.faint),
        const SizedBox(width: JadeSpace.sm),
        _VersionChip(label: info.latest),
      ],
    );
    switch (_phase) {
      case _Phase.intro:
        return [
          versions,
          const SizedBox(height: JadeSpace.md),
          if (info.assetSize > 0)
            Text('Téléchargement : ${_fmtSize(info.assetSize)}',
                style: JadeType.caption.copyWith(color: jade.faint)),
          if (info.notes.isNotEmpty) ...[
            const SizedBox(height: JadeSpace.md),
            const SectionLabel('Nouveautés'),
            const SizedBox(height: JadeSpace.xs),
            Container(
              constraints: const BoxConstraints(maxHeight: 180),
              padding: const EdgeInsets.all(JadeSpace.md),
              decoration: BoxDecoration(
                color: jade.tile,
                borderRadius: JadeRadius.all(JadeRadius.sm),
              ),
              child: SingleChildScrollView(
                child: Text(info.notes,
                    style: JadeType.caption.copyWith(color: jade.body, height: 1.5)),
              ),
            ),
          ],
        ];
      case _Phase.downloading:
        final f = _progress?.fraction;
        return [
          versions,
          const SizedBox(height: JadeSpace.lg),
          ClipRRect(
            borderRadius: JadeRadius.all(JadeRadius.pill),
            child: LinearProgressIndicator(
              value: f,
              minHeight: 8,
              backgroundColor: jade.tile,
              valueColor: AlwaysStoppedAnimation(jade.secondary),
            ),
          ),
          const SizedBox(height: JadeSpace.sm),
          Text(
            f == null
                ? 'Téléchargement…'
                : 'Téléchargement… ${(f * 100).round()} %'
                    '${_progress!.total > 0 ? '  ·  ${_fmtSize(_progress!.done)} / ${_fmtSize(_progress!.total)}' : ''}',
            style: JadeType.caption.copyWith(color: jade.faint),
          ),
        ];
      case _Phase.ready:
        return [
          versions,
          const SizedBox(height: JadeSpace.lg),
          Row(
            children: [
              Icon(TablerIcons.circleCheck, size: 18, color: jade.secondary),
              const SizedBox(width: JadeSpace.sm),
              Expanded(
                child: Text(
                    'Téléchargé. L’installation va fermer puis rouvrir Jade.',
                    style: JadeType.label.copyWith(color: jade.body)),
              ),
            ],
          ),
        ];
      case _Phase.installing:
        return [
          const SizedBox(height: JadeSpace.sm),
          Row(
            children: [
              SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(
                    strokeWidth: 2.4, color: jade.secondary),
              ),
              const SizedBox(width: JadeSpace.md),
              Expanded(
                child: Text('Installation en cours — fermeture de Jade…',
                    style: JadeType.label.copyWith(color: jade.body)),
              ),
            ],
          ),
        ];
      case _Phase.error:
        return [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(TablerIcons.alertTriangle, size: 18, color: jade.danger),
              const SizedBox(width: JadeSpace.sm),
              Expanded(
                child: Text(_error,
                    style: JadeType.label.copyWith(color: jade.body, height: 1.4)),
              ),
            ],
          ),
        ];
    }
  }

  List<Widget> _actions(BuildContext context) {
    switch (_phase) {
      case _Phase.intro:
        return [
          TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Plus tard')),
          FilledButton.icon(
            onPressed: _startDownload,
            icon: const Icon(TablerIcons.download, size: 16),
            label: const Text('Télécharger'),
          ),
        ];
      case _Phase.downloading:
      case _Phase.installing:
        return [
          TextButton(
              onPressed: null, child: const Text('Fermer')),
        ];
      case _Phase.ready:
        return [
          TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Plus tard')),
          FilledButton.icon(
            onPressed: _install,
            icon: const Icon(TablerIcons.refresh, size: 16),
            label: const Text('Installer et redémarrer'),
          ),
        ];
      case _Phase.error:
        return [
          TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Fermer')),
          FilledButton(
              onPressed: _startDownload, child: const Text('Réessayer')),
        ];
    }
  }
}

class _VersionChip extends StatelessWidget {
  final String label;
  final bool muted;
  const _VersionChip({required this.label, this.muted = false});

  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    return Container(
      padding:
          const EdgeInsets.symmetric(horizontal: JadeSpace.sm + 2, vertical: 3),
      decoration: BoxDecoration(
        color: muted ? jade.tile : jade.secondary.withValues(alpha: 0.14),
        borderRadius: JadeRadius.all(JadeRadius.sm),
      ),
      child: Text(label,
          style: JadeType.label.merge(JadeType.tabular).copyWith(
              color: muted ? jade.faint : jade.secondary,
              fontWeight: FontWeight.w600)),
    );
  }
}

String _fmtSize(int bytes) {
  if (bytes >= 1 << 20) return '${(bytes / (1 << 20)).toStringAsFixed(1)} Mo';
  if (bytes >= 1 << 10) return '${(bytes / (1 << 10)).toStringAsFixed(0)} Ko';
  return '$bytes o';
}
