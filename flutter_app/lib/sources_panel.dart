/// Panneau Sources — liste des extraits (documents ou pages web) cités par la
/// réponse ; ouverture du fichier / de la page d'un clic.
library;

import 'package:flutter/material.dart';

import 'design.dart';
import 'models.dart';
import 'tabler.dart';
import 'theme.dart';

/// Panneau lateral listant les sources citees d'une reponse, avec surlignage
/// de la source active et ouverture du document d'origine.
class SourcesPanel extends StatelessWidget {
  final List<Source> sources;
  final int? highlight;
  final VoidCallback onClose;
  final void Function(Source) onOpenFile;

  const SourcesPanel({
    super.key,
    required this.sources,
    required this.highlight,
    required this.onClose,
    required this.onOpenFile,
  });

  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    return Container(
      decoration: BoxDecoration(
        color: jade.panel,
        border: Border(left: BorderSide(color: jade.border)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // en-tête
          Container(
            height: 52,
            padding: const EdgeInsets.fromLTRB(
                JadeSpace.xl, 0, JadeSpace.sm, 0),
            decoration: BoxDecoration(
              border: Border(bottom: BorderSide(color: jade.border)),
            ),
            child: Row(
              children: [
                Text('Sources',
                    style: JadeType.subtitle.copyWith(color: jade.text)),
                const SizedBox(width: JadeSpace.sm),
                Container(
                  padding: const EdgeInsets.symmetric(
                      horizontal: JadeSpace.sm, vertical: 1),
                  decoration: BoxDecoration(
                    color: jade.tile,
                    borderRadius: JadeRadius.all(JadeRadius.pill),
                  ),
                  child: Text('${sources.length}',
                      style: JadeType.caption
                          .merge(JadeType.tabular)
                          .copyWith(color: jade.muted)),
                ),
                const Spacer(),
                Material(
                  color: Colors.transparent,
                  shape: const CircleBorder(),
                  clipBehavior: Clip.antiAlias,
                  child: InkWell(
                    onTap: onClose,
                    hoverColor: jade.tile,
                    focusColor: jade.tile,
                    child: Padding(
                      padding: const EdgeInsets.all(JadeSpace.sm),
                      child: Icon(TablerIcons.x, size: 17, color: jade.muted),
                    ),
                  ),
                ),
              ],
            ),
          ),
          // liste
          Expanded(
            child: ListView.separated(
              padding: const EdgeInsets.all(JadeSpace.md),
              itemCount: sources.length,
              separatorBuilder: (_, __) => const SizedBox(height: JadeSpace.sm),
              itemBuilder: (ctx, i) => _SourceCard(
                source: sources[i],
                selected: highlight == sources[i].n,
                onTap: () => onOpenFile(sources[i]),
              ),
            ),
          ),
          // motif de confiance
          Container(
            padding: const EdgeInsets.all(JadeSpace.lg),
            decoration: BoxDecoration(
              border: Border(top: BorderSide(color: jade.border)),
            ),
            child: Row(
              children: [
                Icon(TablerIcons.lock, size: 14, color: jade.secondary),
                const SizedBox(width: JadeSpace.sm),
                Expanded(
                  child: Text(
                    'Ces fichiers sont lus sur place — ils ne quittent jamais '
                    'ce poste.',
                    style: JadeType.caption
                        .copyWith(color: jade.muted, height: 1.5),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _SourceCard extends StatelessWidget {
  final Source source;
  final bool selected;
  final VoidCallback onTap;
  const _SourceCard({
    required this.source,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    final s = source;
    return Hoverable(
      builder: (context, hover) => GestureDetector(
        onTap: onTap,
        child: AnimatedContainer(
          duration: context.motion(const Duration(milliseconds: 140)),
          padding: const EdgeInsets.all(JadeSpace.md),
          decoration: BoxDecoration(
            color: selected ? jade.primaryContainer : jade.card,
            borderRadius: JadeRadius.all(JadeRadius.md),
            border: Border.all(
                color: selected
                    ? jade.primary.withValues(alpha: 0.4)
                    : (hover ? jade.borderStrong : jade.border)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    width: 22,
                    height: 22,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                      color: selected ? jade.primary : jade.tile,
                      borderRadius: JadeRadius.all(JadeRadius.sm),
                    ),
                    child: Text('${s.n}',
                        style: JadeType.caption.merge(JadeType.tabular).copyWith(
                            fontWeight: FontWeight.w700,
                            color: selected ? Colors.white : jade.body)),
                  ),
                  const SizedBox(width: JadeSpace.sm + 1),
                  Expanded(
                    child: Text(s.filename,
                        overflow: TextOverflow.ellipsis,
                        style: JadeType.label.copyWith(
                            color: jade.text, fontWeight: FontWeight.w600)),
                  ),
                  Icon(s.web ? TablerIcons.world : TablerIcons.fileText,
                      size: 14, color: jade.faint),
                ],
              ),
              if (s.detail.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(left: 31, top: 2),
                  child: Text(s.detail,
                      style: JadeType.caption.copyWith(color: jade.muted)),
                ),
              if (s.text.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(left: 31, top: JadeSpace.sm),
                  child: Text(s.text,
                      maxLines: 3,
                      overflow: TextOverflow.ellipsis,
                      style: JadeType.caption
                          .copyWith(color: jade.muted, height: 1.55)),
                ),
              Padding(
                padding: const EdgeInsets.only(left: 31, top: JadeSpace.sm),
                child: Row(
                  children: [
                    Text(s.web ? 'Consulter la page' : 'Ouvrir le fichier',
                        style: JadeType.caption.copyWith(
                            color: jade.primary, fontWeight: FontWeight.w600)),
                    const SizedBox(width: JadeSpace.xs),
                    Icon(TablerIcons.arrowRight, size: 12, color: jade.primary),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
