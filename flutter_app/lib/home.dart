/// Écran principal : barre latérale (conversations, dossiers, recherche),
/// zone de conversation et panneau Sources.
library;

import 'dart:async';

import 'package:flutter/material.dart';

import 'api.dart';
import 'chat.dart';
import 'design.dart';
import 'main.dart';
import 'models.dart';
import 'settings.dart';
import 'sources_panel.dart';
import 'tabler.dart';
import 'theme.dart';
import 'update.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => HomeScreenState();
}

class HomeScreenState extends State<HomeScreen> {
  final api = ApiClient();

  AppStatus? status;
  UpdateInfo? update;
  List<Conversation> conversations = [];
  List<Folder> folders = [];
  final Set<String> openFolders = {};

  String? currentConv;
  final GlobalKey<ChatViewState> chatKey = GlobalKey();

  // panneau sources
  List<Source>? panelSources;
  int? panelHighlight;

  String _search = '';
  Timer? _searchTimer;

  @override
  void initState() {
    super.initState();
    _refresh();
    _checkUpdate();
  }

  /// Vérifie discrètement s'il existe une mise à jour (jamais bloquant).
  Future<void> _checkUpdate() async {
    final info = await api.checkUpdate();
    if (mounted && info.available) setState(() => update = info);
  }

  @override
  void dispose() {
    _searchTimer?.cancel();
    api.close();
    super.dispose();
  }

  Future<void> _refresh() async {
    try {
      final results = await Future.wait([
        api.status(),
        api.listConversations(),
        api.listFolders(),
      ]);
      if (!mounted) return;
      setState(() {
        status = results[0] as AppStatus;
        conversations = results[1] as List<Conversation>;
        folders = results[2] as List<Folder>;
      });
    } catch (_) {
      // backend momentanément indisponible : on garde l'état affiché
    }
  }

  Future<void> refreshConversations() async {
    try {
      final list = await api.listConversations();
      if (mounted) setState(() => conversations = list);
    } catch (_) {}
  }

  void newChat() {
    setState(() {
      currentConv = null;
      panelSources = null;
      panelHighlight = null;
    });
    chatKey.currentState?.reset();
  }

  Future<void> openConversation(String id) async {
    setState(() {
      currentConv = id;
      panelSources = null;
      panelHighlight = null;
    });
    await chatKey.currentState?.load(id);
  }

  /// Une question vient d'être envoyée depuis l'accueil : la conversation
  /// existe désormais côté backend.
  void onConversationStarted(String id) {
    setState(() => currentConv = id);
    refreshConversations();
  }

  void showSources(List<Source> sources, [int? highlight]) {
    setState(() {
      panelSources = sources;
      panelHighlight = highlight;
    });
  }

  void closeSources() => setState(() {
        panelSources = null;
        panelHighlight = null;
      });

  void openSettings() {
    showSettingsDialog(
      context,
      api: api,
      onHistoryCleared: () {
        newChat();
        _refresh();
      },
    );
  }

  // ------------------------------------------------------------ actions

  Future<void> _renameDialog(Conversation c) async {
    final ctl = TextEditingController(text: c.title);
    final ok = await _prompt(
      title: 'Renommer la conversation',
      controller: ctl,
      confirmLabel: 'Renommer',
    );
    if (ok == true && ctl.text.trim().isNotEmpty) {
      await api.rename(c.id, ctl.text.trim());
      await refreshConversations();
    }
  }

  Future<void> _deleteDialog(Conversation c) async {
    final jade = context.jade;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        shape:
            RoundedRectangleBorder(borderRadius: JadeRadius.all(JadeRadius.lg)),
        title: const Text('Supprimer la conversation ?'),
        content: Text('« ${c.title} » sera définitivement supprimée.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Annuler')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: jade.danger),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Supprimer'),
          ),
        ],
      ),
    );
    if (ok == true) {
      await api.delete(c.id);
      if (currentConv == c.id) newChat();
      await refreshConversations();
    }
  }

  Future<void> _newFolderDialog() async {
    final ctl = TextEditingController();
    final ok = await _prompt(
      title: 'Nouveau dossier',
      controller: ctl,
      hint: 'Nom du dossier',
      confirmLabel: 'Créer',
    );
    if (ok == true && ctl.text.trim().isNotEmpty) {
      final f = await api.createFolder(ctl.text.trim());
      openFolders.add(f.id);
      await _refresh();
    }
  }

  Future<bool?> _prompt({
    required String title,
    required TextEditingController controller,
    required String confirmLabel,
    String? hint,
  }) {
    return showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        shape:
            RoundedRectangleBorder(borderRadius: JadeRadius.all(JadeRadius.lg)),
        title: Text(title),
        content: TextField(
          controller: controller,
          autofocus: true,
          maxLength: 60,
          decoration: InputDecoration(hintText: hint),
          onSubmitted: (_) => Navigator.pop(ctx, true),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Annuler')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: Text(confirmLabel)),
        ],
      ),
    );
  }

  // ------------------------------------------------------------ rendu

  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    return Scaffold(
      backgroundColor: jade.bg,
      body: Row(
        children: [
          _Sidebar(state: this),
          Expanded(
            child: ChatView(key: chatKey, api: api, home: this),
          ),
          AnimatedContainer(
            duration: context.motion(const Duration(milliseconds: 200)),
            curve: Curves.easeOutCubic,
            width: panelSources == null ? 0 : 384,
            child: panelSources == null
                ? const SizedBox.shrink()
                : SourcesPanel(
                    sources: panelSources!,
                    highlight: panelHighlight,
                    onClose: closeSources,
                    onOpenFile: (s) =>
                        s.web ? api.openUrl(s.url) : api.openFile(s.path),
                  ),
          ),
        ],
      ),
    );
  }

  List<Conversation> get _filtered {
    if (_search.isEmpty) return conversations;
    final q = _search.toLowerCase();
    return conversations
        .where((c) => c.title.toLowerCase().contains(q))
        .toList();
  }

  void _onSearch(String v) {
    _searchTimer?.cancel();
    _searchTimer = Timer(const Duration(milliseconds: 180), () {
      if (mounted) setState(() => _search = v.trim());
    });
  }
}

// ================================================================ sidebar

class _Sidebar extends StatelessWidget {
  final HomeScreenState state;
  const _Sidebar({required this.state});

  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    return Container(
      width: 272,
      decoration: BoxDecoration(
        color: jade.panel,
        border: Border(right: BorderSide(color: jade.border)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // en-tête : marque + thème
          Padding(
            padding: const EdgeInsets.fromLTRB(
                JadeSpace.lg, JadeSpace.lg, JadeSpace.md, JadeSpace.md),
            child: Row(
              children: [
                const JadeMark(size: 32),
                const SizedBox(width: JadeSpace.md),
                Text('Jade', style: JadeType.title.copyWith(color: jade.text)),
                const Spacer(),
                _HeaderIcon(
                  icon: TablerIcons.settings,
                  tooltip: 'Réglages',
                  onTap: state.openSettings,
                ),
                _ThemeToggle(),
              ],
            ),
          ),
          // nouvelle conversation — CTA principal
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: JadeSpace.md),
            child: _NewChatButton(onTap: state.newChat),
          ),
          const SizedBox(height: JadeSpace.md),
          // recherche
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: JadeSpace.md),
            child: _SearchField(onChanged: state._onSearch),
          ),
          // liste conversations + dossiers
          Expanded(
            child: ListView(
              padding: const EdgeInsets.fromLTRB(
                  JadeSpace.md, JadeSpace.sm, JadeSpace.md, JadeSpace.md),
              children: _buildList(context),
            ),
          ),
          Divider(height: 1, color: jade.border),
          _Footer(state: state),
        ],
      ),
    );
  }

  List<Widget> _buildList(BuildContext context) {
    final jade = context.jade;
    final convs = state._filtered;
    final widgets = <Widget>[];

    widgets.add(_NavTile(
      icon: TablerIcons.folderPlus,
      label: 'Nouveau dossier',
      onTap: state._newFolderDialog,
      dense: true,
    ));

    // dossiers
    for (final f in state.folders) {
      final inFolder = convs.where((c) => c.folderId == f.id).toList();
      final open = state.openFolders.contains(f.id);
      widgets.add(_NavTile(
        leading: Icon(open ? TablerIcons.chevronDown : TablerIcons.chevronRight,
            size: 16, color: jade.faint),
        icon: TablerIcons.folder,
        iconColor: jade.secondary,
        label: f.name,
        bold: true,
        trailing: _CountBadge(inFolder.length),
        onTap: () {
          open
              ? state.openFolders.remove(f.id)
              : state.openFolders.add(f.id);
          // ignore: invalid_use_of_protected_member
          state.setState(() {});
        },
      ));
      if (open) {
        widgets.addAll(inFolder.map((c) => Padding(
              padding: const EdgeInsets.only(left: JadeSpace.lg),
              child: _ConvRow(state: state, conv: c),
            )));
      }
    }

    // épinglées puis le reste (hors dossiers)
    final loose = convs.where((c) =>
        c.folderId == null || !state.folders.any((f) => f.id == c.folderId));
    final pinned = loose.where((c) => c.pinned).toList();
    final others = loose.where((c) => !c.pinned).toList();
    if (pinned.isNotEmpty) {
      widgets.add(const SectionLabel('Épinglées'));
      widgets.addAll(pinned.map((c) => _ConvRow(state: state, conv: c)));
    }
    if (others.isNotEmpty) {
      widgets.add(const SectionLabel('Conversations'));
      widgets.addAll(others.map((c) => _ConvRow(state: state, conv: c)));
    }
    if (convs.isEmpty) {
      widgets.add(Padding(
        padding: const EdgeInsets.fromLTRB(
            JadeSpace.sm, JadeSpace.xxl, JadeSpace.sm, 0),
        child: Text(
          state._search.isEmpty
              ? 'Aucune conversation pour l’instant.'
              : 'Aucun résultat pour « ${state._search} ».',
          style: JadeType.caption.copyWith(color: jade.faint, height: 1.5),
        ),
      ));
    }
    return widgets;
  }
}

// -------------------------------------------------------------- sous-widgets

class _HeaderIcon extends StatelessWidget {
  final IconData icon;
  final String tooltip;
  final VoidCallback onTap;
  const _HeaderIcon(
      {required this.icon, required this.tooltip, required this.onTap});

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
          hoverColor: jade.tile,
          focusColor: jade.tile,
          child: Padding(
            padding: const EdgeInsets.all(JadeSpace.sm),
            child: Icon(icon, size: 18, color: jade.muted),
          ),
        ),
      ),
    );
  }
}

class _ThemeToggle extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final mode = JadeApp.of(context).themeMode;
    final (icon, tip) = switch (mode) {
      ThemeMode.system => (TablerIcons.brightnessHalf, 'Thème : automatique'),
      ThemeMode.light => (TablerIcons.sun, 'Thème : clair'),
      ThemeMode.dark => (TablerIcons.moon, 'Thème : sombre'),
    };
    return _HeaderIcon(
      icon: icon,
      tooltip: tip,
      onTap: () => JadeApp.of(context).cycleTheme(),
    );
  }
}

class _NewChatButton extends StatelessWidget {
  final VoidCallback onTap;
  const _NewChatButton({required this.onTap});

  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    return FocusRing(
      radius: JadeRadius.md,
      child: Material(
        color: jade.primaryContainer,
        borderRadius: JadeRadius.all(JadeRadius.md),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          hoverColor: jade.primary.withValues(alpha: 0.10),
          child: Padding(
            padding: const EdgeInsets.symmetric(
                horizontal: JadeSpace.md, vertical: JadeSpace.md),
            child: Row(
              children: [
                Icon(TablerIcons.pencilPlus,
                    size: 17, color: jade.onPrimaryContainer),
                const SizedBox(width: JadeSpace.md),
                Text('Nouvelle conversation',
                    style: JadeType.label.copyWith(
                        color: jade.onPrimaryContainer,
                        fontWeight: FontWeight.w600)),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _SearchField extends StatelessWidget {
  final ValueChanged<String> onChanged;
  const _SearchField({required this.onChanged});

  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    return TextField(
      onChanged: onChanged,
      style: JadeType.label.copyWith(color: jade.text),
      decoration: InputDecoration(
        hintText: 'Rechercher…',
        hintStyle: JadeType.label.copyWith(color: jade.faint),
        prefixIcon: Icon(TablerIcons.search, size: 17, color: jade.faint),
        prefixIconConstraints:
            const BoxConstraints(minWidth: 38, minHeight: 34),
        isDense: true,
        filled: true,
        fillColor: jade.tile,
        contentPadding:
            const EdgeInsets.symmetric(vertical: JadeSpace.sm + 2),
        enabledBorder: OutlineInputBorder(
          borderRadius: JadeRadius.all(JadeRadius.md),
          borderSide: BorderSide.none,
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: JadeRadius.all(JadeRadius.md),
          borderSide: BorderSide(color: jade.primary, width: 1.5),
        ),
      ),
    );
  }
}

class _CountBadge extends StatelessWidget {
  final int count;
  const _CountBadge(this.count);
  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: JadeSpace.sm, vertical: 1),
      decoration: BoxDecoration(
        color: jade.tile,
        borderRadius: JadeRadius.all(JadeRadius.pill),
      ),
      child: Text('$count',
          style: JadeType.caption
              .merge(JadeType.tabular)
              .copyWith(color: jade.faint)),
    );
  }
}

/// Tuile de navigation générique — gère survol + focus clavier via InkWell.
class _NavTile extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final Widget? leading;
  final Widget? trailing;
  final Color? iconColor;
  final bool bold;
  final bool dense;
  const _NavTile({
    required this.icon,
    required this.label,
    required this.onTap,
    this.leading,
    this.trailing,
    this.iconColor,
    this.bold = false,
    this.dense = false,
  });

  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    return Material(
      color: Colors.transparent,
      borderRadius: JadeRadius.all(JadeRadius.md),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        hoverColor: jade.tile,
        focusColor: jade.tile,
        child: Padding(
          padding: EdgeInsets.symmetric(
              horizontal: JadeSpace.sm,
              vertical: dense ? JadeSpace.sm : JadeSpace.sm + 1),
          child: Row(
            children: [
              if (leading != null) ...[
                leading!,
                const SizedBox(width: JadeSpace.xs),
              ],
              Icon(icon, size: 16, color: iconColor ?? jade.body),
              const SizedBox(width: JadeSpace.sm + 1),
              Expanded(
                child: Text(label,
                    overflow: TextOverflow.ellipsis,
                    style: JadeType.label.copyWith(
                        color: jade.body,
                        fontWeight: bold ? FontWeight.w600 : FontWeight.w500)),
              ),
              if (trailing != null) trailing!,
            ],
          ),
        ),
      ),
    );
  }
}

class _ConvRow extends StatefulWidget {
  final HomeScreenState state;
  final Conversation conv;
  const _ConvRow({required this.state, required this.conv});

  @override
  State<_ConvRow> createState() => _ConvRowState();
}

class _ConvRowState extends State<_ConvRow> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    final c = widget.conv;
    final active = widget.state.currentConv == c.id;
    return MouseRegion(
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: Material(
        color: active ? jade.primaryContainer : Colors.transparent,
        borderRadius: JadeRadius.all(JadeRadius.md),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: () => widget.state.openConversation(c.id),
          hoverColor: active ? Colors.transparent : jade.tile,
          focusColor: jade.tile,
          child: Padding(
            padding: const EdgeInsets.symmetric(
                horizontal: JadeSpace.sm + 1, vertical: JadeSpace.sm + 1),
            child: Row(
              children: [
                if (c.pinned) ...[
                  Icon(TablerIcons.pin, size: 12,
                      color: active ? jade.primary : jade.faint),
                  const SizedBox(width: JadeSpace.xs + 1),
                ],
                Expanded(
                  child: Text(
                    c.title,
                    overflow: TextOverflow.ellipsis,
                    style: JadeType.label.copyWith(
                      fontWeight: active ? FontWeight.w600 : FontWeight.w400,
                      color: active ? jade.onPrimaryContainer : jade.body,
                    ),
                  ),
                ),
                if (_hover || active) _RowActions(state: widget.state, conv: c),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Actions d'une conversation en icônes (au survol) : épingler, renommer,
/// déplacer vers un dossier (si des dossiers existent), supprimer.
class _RowActions extends StatelessWidget {
  final HomeScreenState state;
  final Conversation conv;
  const _RowActions({required this.state, required this.conv});

  Widget _btn(BuildContext context, IconData icon, String tip, VoidCallback onTap,
      {bool danger = false}) {
    final jade = context.jade;
    return Tooltip(
      message: tip,
      child: Material(
        color: Colors.transparent,
        shape: const CircleBorder(),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          hoverColor: danger
              ? jade.danger.withValues(alpha: 0.14)
              : jade.borderStrong.withValues(alpha: 0.5),
          focusColor: jade.tile,
          child: Padding(
            padding: const EdgeInsets.all(4),
            child: Icon(icon, size: 15, color: danger ? jade.danger : jade.muted),
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        _btn(
          context,
          conv.pinned ? TablerIcons.pinned : TablerIcons.pin,
          conv.pinned ? 'Désépingler' : 'Épingler',
          () async {
            await state.api.setFlag(conv.id, 'pinned', !conv.pinned);
            await state.refreshConversations();
          },
        ),
        _btn(context, TablerIcons.edit, 'Renommer',
            () => state._renameDialog(conv)),
        if (state.folders.isNotEmpty || conv.folderId != null)
          SizedBox(
            width: 23,
            height: 23,
            child: PopupMenuButton<String>(
              padding: EdgeInsets.zero,
              tooltip: 'Déplacer',
              icon: Icon(TablerIcons.folder, size: 15, color: jade.muted),
              position: PopupMenuPosition.under,
              shape: RoundedRectangleBorder(
                  borderRadius: JadeRadius.all(JadeRadius.md)),
              onSelected: (v) async {
                final fid = v.substring(7);
                await state.api
                    .moveConversation(conv.id, fid.isEmpty ? null : fid);
                await state.refreshConversations();
              },
              itemBuilder: (ctx) => [
                ...state.folders.map((f) => PopupMenuItem(
                    value: 'folder:${f.id}',
                    child: Text('Déplacer vers « ${f.name} »'))),
                if (conv.folderId != null)
                  const PopupMenuItem(
                      value: 'folder:', child: Text('Retirer du dossier')),
              ],
            ),
          ),
        _btn(context, TablerIcons.trash, 'Supprimer',
            () => state._deleteDialog(conv), danger: true),
      ],
    );
  }
}

class _Footer extends StatelessWidget {
  final HomeScreenState state;
  const _Footer({required this.state});

  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    return Padding(
      padding: const EdgeInsets.all(JadeSpace.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (state.update?.showButton == true) ...[
            UpdateButton(api: state.api, info: state.update!),
            const SizedBox(height: JadeSpace.sm + 2),
          ],
          Row(
            children: [
              CircleAvatar(
                radius: 15,
                backgroundColor: jade.primaryContainer,
                child: Text(
                  _initials(state.status?.username ?? '?'),
                  style: JadeType.caption.copyWith(
                      fontWeight: FontWeight.w700,
                      color: jade.onPrimaryContainer),
                ),
              ),
              const SizedBox(width: JadeSpace.sm + 2),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(state.status?.username ?? '',
                        overflow: TextOverflow.ellipsis,
                        style: JadeType.label.copyWith(color: jade.body)),
                    Text('Version ${state.status?.appVersion ?? '—'}',
                        style: JadeType.caption
                            .merge(JadeType.tabular)
                            .copyWith(color: jade.faint)),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: JadeSpace.md),
          // motif de confiance — au cœur du sujet de Jade
          Container(
            padding: const EdgeInsets.symmetric(
                horizontal: JadeSpace.md, vertical: JadeSpace.sm),
            decoration: BoxDecoration(
              color: jade.tile,
              borderRadius: JadeRadius.all(JadeRadius.sm),
            ),
            child: Row(
              children: [
                Icon(TablerIcons.lock, size: 13, color: jade.secondary),
                const SizedBox(width: JadeSpace.sm),
                Expanded(
                  child: Text('Local et privé — rien ne quitte ce poste.',
                      style: JadeType.caption.copyWith(color: jade.muted)),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  static String _initials(String name) {
    final words = name.trim().split(RegExp(r'\s+'));
    if (words.length > 1) return (words[0][0] + words[1][0]).toUpperCase();
    return name.isEmpty
        ? '?'
        : name.substring(0, name.length.clamp(0, 2)).toUpperCase();
  }
}
