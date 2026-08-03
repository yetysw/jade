/// Écran principal : barre latérale (conversations, dossiers, recherche),
/// zone de conversation et panneau Sources.
library;

import 'dart:async';

import 'package:flutter/material.dart';

import 'api.dart';
import 'chat.dart';
import 'design.dart';
import 'feedback.dart';
import 'main.dart';
import 'models.dart';
import 'settings.dart';
import 'sources_panel.dart';
import 'tabler.dart';
import 'theme.dart';
import 'update.dart';

/// Ecran principal : barre laterale (conversations, dossiers, reglages, mise a
/// jour) et zone de conversation active.
class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => HomeScreenState();
}

/// Etat de [HomeScreen] : detient le [ApiClient] partage et les listes
/// (conversations, dossiers, statut, mise a jour). Expose aux vues filles.
class HomeScreenState extends State<HomeScreen> {
  final api = ApiClient();

  AppStatus? status;
  UpdateInfo? update;
  List<Conversation> conversations = [];
  List<Folder> folders = [];
  final Set<String> openFolders = {};

  String? currentConv;
  final GlobalKey<ChatViewState> chatKey = GlobalKey();

  /// Vrai pendant le glisser-déposer d'une conversation dans la barre
  /// latérale : force l'affichage des en-têtes « Épinglées »/« Conversations »
  /// même vides, pour qu'elles restent des cibles de dépôt valides.
  bool _draggingConversation = false;

  // panneau sources
  List<Source>? panelSources;
  int? panelHighlight;

  String _search = '';
  Timer? _searchTimer;
  Timer? _statusTimer;

  @override
  void initState() {
    super.initState();
    _refresh();
    _checkUpdate();
    // rafraîchit périodiquement le statut : le bandeau de santé (LLM injoignable,
    // disque bas…) reflète l'état réel sans que l'utilisateur ait à recharger.
    _statusTimer =
        Timer.periodic(const Duration(seconds: 60), (_) => _refresh());
  }

  /// Vérifie discrètement s'il existe une mise à jour (jamais bloquant).
  Future<void> _checkUpdate() async {
    final info = await api.checkUpdate();
    if (mounted && info.available) setState(() => update = info);
  }

  @override
  void dispose() {
    _searchTimer?.cancel();
    _statusTimer?.cancel();
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
      // le nom affiché (pied de la barre latérale) doit refléter le profil
      // dès qu'il est modifié dans les réglages, sans réinitialiser le fil.
      onProfileChanged: _refresh,
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

  /// Déplace une conversation vers un dossier (ou la retire si `folderId` est
  /// nul) et déplie ce dossier pour que le résultat reste visible — sans quoi
  /// la conversation semblait disparaître silencieusement de la liste.
  Future<void> _moveToFolder(Conversation c, String? folderId) async {
    await api.moveConversation(c.id, folderId);
    if (folderId != null) openFolders.add(folderId);
    await refreshConversations();
  }

  /// Épingle une conversation déposée (glisser-déposer) sur la section
  /// « Épinglées » ; sans effet si elle l'est déjà.
  Future<void> _pinConversation(Conversation c) async {
    if (c.pinned) return;
    await api.setFlag(c.id, 'pinned', true);
    await refreshConversations();
  }

  /// Retire une conversation déposée (glisser-déposer) sur la section
  /// « Conversations » de son dossier et/ou la désépingle, selon ce qui
  /// s'applique.
  Future<void> _unassign(Conversation c) async {
    if (c.folderId != null) await api.moveConversation(c.id, null);
    if (c.pinned) await api.setFlag(c.id, 'pinned', false);
    await refreshConversations();
  }

  /// Bascule l'état plié/déplié d'un dossier.
  void _toggleFolder(String id) {
    setState(() {
      if (!openFolders.remove(id)) openFolders.add(id);
    });
  }

  /// Suivi de l'état de glisser-déposer d'une conversation — voir
  /// [_draggingConversation].
  void _setDragging(bool v) {
    if (_draggingConversation == v) return;
    setState(() => _draggingConversation = v);
  }

  Future<void> _renameFolderDialog(Folder f) async {
    final ctl = TextEditingController(text: f.name);
    final ok = await _prompt(
      title: 'Renommer le dossier',
      controller: ctl,
      confirmLabel: 'Renommer',
    );
    if (ok == true && ctl.text.trim().isNotEmpty) {
      await api.renameFolder(f.id, ctl.text.trim());
      await _refresh();
    }
  }

  Future<void> _deleteFolderDialog(Folder f) async {
    final jade = context.jade;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        shape:
            RoundedRectangleBorder(borderRadius: JadeRadius.all(JadeRadius.lg)),
        title: const Text('Supprimer le dossier ?'),
        content: Text(
            '« ${f.name} » sera supprimé. Les conversations qu’il contient ne '
            'sont pas supprimées : elles redeviennent des conversations sans '
            'dossier.'),
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
      await api.deleteFolder(f.id);
      openFolders.remove(f.id);
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
                  icon: TablerIcons.send,
                  tooltip: 'Donner mon avis',
                  onTap: () => showFeedbackDialog(context, state.api),
                ),
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

    // dossiers — clic droit pour renommer/supprimer, glisser-déposer une
    // conversation pour l'y classer (sinon jamais accessible)
    for (final f in state.folders) {
      final inFolder = convs.where((c) => c.folderId == f.id).toList();
      final open = state.openFolders.contains(f.id);
      widgets.add(_FolderTile(
          state: state, folder: f, open: open, count: inFolder.length));
      if (open) {
        widgets.addAll(inFolder.map((c) => Padding(
              padding: const EdgeInsets.only(left: JadeSpace.lg),
              child: _ConvRow(state: state, conv: c),
            )));
      }
    }

    // épinglées puis le reste (hors dossiers) — les en-têtes restent visibles
    // (même vides) pendant un glisser-déposer, pour rester des cibles valides
    final loose = convs.where((c) =>
        c.folderId == null || !state.folders.any((f) => f.id == c.folderId));
    final pinned = loose.where((c) => c.pinned).toList();
    final others = loose.where((c) => !c.pinned).toList();
    if (pinned.isNotEmpty || state._draggingConversation) {
      widgets.add(_SectionDropTarget(
        text: 'Épinglées',
        accepts: (c) => !c.pinned,
        onDrop: state._pinConversation,
      ));
      widgets.addAll(pinned.map((c) => _ConvRow(state: state, conv: c)));
    }
    if (others.isNotEmpty || state._draggingConversation) {
      widgets.add(_SectionDropTarget(
        text: 'Conversations',
        accepts: (c) => c.folderId != null || c.pinned,
        onDrop: state._unassign,
      ));
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

/// Ligne d'un dossier : déplier/replier au clic, menu contextuel au clic
/// droit, et cible de glisser-déposer pour y classer une conversation (sans
/// effet si elle s'y trouve déjà).
class _FolderTile extends StatelessWidget {
  final HomeScreenState state;
  final Folder folder;
  final bool open;
  final int count;
  const _FolderTile({
    required this.state,
    required this.folder,
    required this.open,
    required this.count,
  });

  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    return DragTarget<Conversation>(
      onWillAcceptWithDetails: (d) => d.data.folderId != folder.id,
      onAcceptWithDetails: (d) => state._moveToFolder(d.data, folder.id),
      builder: (context, candidates, rejected) {
        final hovering = candidates.isNotEmpty;
        return MouseRegion(
          cursor: hovering ? SystemMouseCursors.grabbing : MouseCursor.defer,
          child: GestureDetector(
            onSecondaryTapUp: (d) =>
                _showFolderMenu(context, state, folder, d.globalPosition),
            child: AnimatedContainer(
              duration: context.motion(const Duration(milliseconds: 130)),
              decoration: BoxDecoration(
                color: hovering ? jade.primaryContainer : Colors.transparent,
                borderRadius: JadeRadius.all(JadeRadius.md),
                border: Border.all(
                    color: hovering ? jade.primary : Colors.transparent,
                    width: 1.5),
              ),
              child: _NavTile(
                leading: Icon(
                    open ? TablerIcons.chevronDown : TablerIcons.chevronRight,
                    size: 16,
                    color: jade.faint),
                icon: TablerIcons.folder,
                iconColor: jade.secondary,
                label: folder.name,
                bold: true,
                trailing: _CountBadge(count),
                onTap: () => state._toggleFolder(folder.id),
              ),
            ),
          ),
        );
      },
    );
  }
}

/// En-tête de section (« Épinglées » / « Conversations ») servant aussi de
/// cible de glisser-déposer : y déposer une conversation applique [onDrop]
/// (épingler, ou retirer du dossier/désépingler selon la section).
class _SectionDropTarget extends StatelessWidget {
  final String text;
  final bool Function(Conversation) accepts;
  final void Function(Conversation) onDrop;
  const _SectionDropTarget({
    required this.text,
    required this.accepts,
    required this.onDrop,
  });

  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    return DragTarget<Conversation>(
      onWillAcceptWithDetails: (d) => accepts(d.data),
      onAcceptWithDetails: (d) => onDrop(d.data),
      builder: (context, candidates, rejected) {
        final hovering = candidates.isNotEmpty;
        return MouseRegion(
          cursor: hovering ? SystemMouseCursors.grabbing : MouseCursor.defer,
          child: AnimatedContainer(
            duration: context.motion(const Duration(milliseconds: 130)),
            decoration: BoxDecoration(
              color: hovering ? jade.primaryContainer : Colors.transparent,
              borderRadius: JadeRadius.all(JadeRadius.sm),
              border: Border.all(
                  color: hovering ? jade.primary : Colors.transparent,
                  width: 1.5),
            ),
            child: SectionLabel(text),
          ),
        );
      },
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
    final row = MouseRegion(
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: GestureDetector(
        // clic droit : menu contextuel complet (renommer, déplacer, épingler,
        // supprimer) — plus découvrable que les icônes de survol seules.
        onSecondaryTapUp: (d) =>
            _showConvMenu(context, widget.state, c, d.globalPosition),
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
                  if (_hover || active)
                    _RowActions(state: widget.state, conv: c),
                ],
              ),
            ),
          ),
        ),
      ),
    );

    // glisser-déposer : appui long puis déplacement (le clic simple reste
    // l'ouverture, le clic droit reste le menu — LongPressDraggable ne réagit
    // qu'au bouton primaire et n'intercepte ni l'un ni l'autre).
    return LongPressDraggable<Conversation>(
      data: c,
      dragAnchorStrategy: pointerDragAnchorStrategy,
      onDragStarted: () => widget.state._setDragging(true),
      onDragEnd: (_) => widget.state._setDragging(false),
      onDraggableCanceled: (_, __) => widget.state._setDragging(false),
      feedback: _ConvDragFeedback(conv: c),
      childWhenDragging: Opacity(opacity: 0.35, child: row),
      child: row,
    );
  }
}

/// Aperçu flottant affiché sous le curseur pendant le glisser-déposer d'une
/// conversation.
class _ConvDragFeedback extends StatelessWidget {
  final Conversation conv;
  const _ConvDragFeedback({required this.conv});

  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    return Material(
      color: Colors.transparent,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 220),
        child: Container(
          padding: const EdgeInsets.symmetric(
              horizontal: JadeSpace.md, vertical: JadeSpace.sm + 1),
          decoration: BoxDecoration(
            color: jade.card,
            borderRadius: JadeRadius.all(JadeRadius.md),
            border: Border.all(color: jade.borderStrong),
            boxShadow: JadeElevation.lift(context),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(conv.pinned ? TablerIcons.pinned : TablerIcons.messages,
                  size: 14, color: jade.secondary),
              const SizedBox(width: JadeSpace.sm),
              Flexible(
                child: Text(conv.title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: JadeType.label.copyWith(
                        color: jade.text, fontWeight: FontWeight.w600)),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Ouvre le menu contextuel (clic droit) d'une conversation : renommer,
/// épingler, déplacer vers un dossier, supprimer. Regroupe les mêmes actions
/// que [_RowActions] (icônes au survol) dans un seul menu, plus visible.
Future<void> _showConvMenu(BuildContext context, HomeScreenState state,
    Conversation c, Offset globalPosition) async {
  final overlay = Overlay.of(context).context.findRenderObject() as RenderBox;
  final selected = await showMenu<String>(
    context: context,
    position: RelativeRect.fromRect(
      globalPosition & const Size(1, 1),
      Offset.zero & overlay.size,
    ),
    shape: RoundedRectangleBorder(borderRadius: JadeRadius.all(JadeRadius.md)),
    items: [
      PopupMenuItem(
        value: 'rename',
        child: _MenuRow(icon: TablerIcons.edit, label: 'Renommer'),
      ),
      PopupMenuItem(
        value: 'pin',
        child: _MenuRow(
          icon: c.pinned ? TablerIcons.pinned : TablerIcons.pin,
          label: c.pinned ? 'Désépingler' : 'Épingler',
        ),
      ),
      ...state.folders.map((f) => PopupMenuItem(
            value: 'folder:${f.id}',
            child: _MenuRow(
                icon: TablerIcons.folder, label: 'Déplacer vers « ${f.name} »'),
          )),
      if (c.folderId != null)
        PopupMenuItem(
          value: 'folder:',
          child: _MenuRow(icon: TablerIcons.x, label: 'Retirer du dossier'),
        ),
      const PopupMenuDivider(),
      PopupMenuItem(
        value: 'delete',
        child: _MenuRow(icon: TablerIcons.trash, label: 'Supprimer', danger: true),
      ),
    ],
  );
  if (selected == null || !context.mounted) return;
  if (selected == 'rename') {
    await state._renameDialog(c);
  } else if (selected == 'pin') {
    await state.api.setFlag(c.id, 'pinned', !c.pinned);
    await state.refreshConversations();
  } else if (selected == 'delete') {
    await state._deleteDialog(c);
  } else if (selected.startsWith('folder:')) {
    final fid = selected.substring(7);
    await state._moveToFolder(c, fid.isEmpty ? null : fid);
  }
}

/// Ligne icône + libellé pour les items de menu contextuel.
class _MenuRow extends StatelessWidget {
  final IconData icon;
  final String label;
  final bool danger;
  const _MenuRow(
      {required this.icon, required this.label, this.danger = false});

  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    final color = danger ? jade.danger : jade.body;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 15, color: color),
        const SizedBox(width: JadeSpace.sm + 2),
        Text(label, style: JadeType.label.copyWith(color: color)),
      ],
    );
  }
}

/// Menu contextuel (clic droit) d'un dossier : renommer, supprimer. Ces
/// actions existaient déjà côté API (`renameFolder`/`deleteFolder`) mais
/// n'étaient reliées à aucune interface — corrigé ici.
Future<void> _showFolderMenu(BuildContext context, HomeScreenState state,
    Folder f, Offset globalPosition) async {
  final overlay = Overlay.of(context).context.findRenderObject() as RenderBox;
  final selected = await showMenu<String>(
    context: context,
    position: RelativeRect.fromRect(
      globalPosition & const Size(1, 1),
      Offset.zero & overlay.size,
    ),
    shape: RoundedRectangleBorder(borderRadius: JadeRadius.all(JadeRadius.md)),
    items: [
      PopupMenuItem(
        value: 'rename',
        child: _MenuRow(icon: TablerIcons.edit, label: 'Renommer le dossier'),
      ),
      PopupMenuItem(
        value: 'delete',
        child: _MenuRow(
            icon: TablerIcons.trash,
            label: 'Supprimer le dossier',
            danger: true),
      ),
    ],
  );
  if (selected == null || !context.mounted) return;
  if (selected == 'rename') {
    await state._renameFolderDialog(f);
  } else if (selected == 'delete') {
    await state._deleteFolderDialog(f);
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
            padding: const EdgeInsets.all(JadeSpace.xs),
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
            width: JadeSpace.xxl,
            height: JadeSpace.xxl,
            child: PopupMenuButton<String>(
              padding: EdgeInsets.zero,
              tooltip: 'Déplacer',
              icon: Icon(TablerIcons.folder, size: 15, color: jade.muted),
              position: PopupMenuPosition.under,
              shape: RoundedRectangleBorder(
                  borderRadius: JadeRadius.all(JadeRadius.md)),
              onSelected: (v) async {
                final fid = v.substring(7);
                await state._moveToFolder(conv, fid.isEmpty ? null : fid);
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

class _LicenseBanner extends StatelessWidget {
  final LicenseInfo info;
  const _LicenseBanner({required this.info});

  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    final color = info.isBlocking ? jade.danger : jade.secondary;
    return Container(
      padding: const EdgeInsets.symmetric(
          horizontal: JadeSpace.md, vertical: JadeSpace.sm + 1),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: JadeRadius.all(JadeRadius.sm),
        border: Border.all(color: color.withValues(alpha: 0.35)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(info.isBlocking ? TablerIcons.alertTriangle : TablerIcons.alertCircle,
              size: 15, color: color),
          const SizedBox(width: JadeSpace.sm),
          Expanded(
            child: Text(
              info.detail.isNotEmpty
                  ? info.detail
                  : (info.isBlocking
                      ? 'Abonnement Jade à renouveler — contactez Jade.'
                      : 'Vérification de licence indisponible.'),
              style: JadeType.caption.copyWith(color: jade.body, height: 1.4),
            ),
          ),
        ],
      ),
    );
  }
}

/// Bandeau rouge d'alerte système : affiché quand un point de santé mérite
/// l'attention (serveur d'IA injoignable, modèles absents, disque bas). Un appui
/// ouvre les réglages, où le panneau d'état détaille le diagnostic.
class _HealthBanner extends StatelessWidget {
  final HealthInfo info;
  final VoidCallback onOpenSettings;
  const _HealthBanner({required this.info, required this.onOpenSettings});

  @override
  Widget build(BuildContext context) {
    final jade = context.jade;
    return Material(
      color: Colors.transparent,
      borderRadius: JadeRadius.all(JadeRadius.sm),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onOpenSettings,
        child: Container(
          padding: const EdgeInsets.symmetric(
              horizontal: JadeSpace.md, vertical: JadeSpace.sm + 1),
          decoration: BoxDecoration(
            color: jade.danger.withValues(alpha: 0.12),
            borderRadius: JadeRadius.all(JadeRadius.sm),
            border: Border.all(color: jade.danger.withValues(alpha: 0.35)),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(TablerIcons.alertTriangle, size: 15, color: jade.danger),
              const SizedBox(width: JadeSpace.sm),
              Expanded(
                child: Text(info.summary,
                    style:
                        JadeType.caption.copyWith(color: jade.body, height: 1.4)),
              ),
            ],
          ),
        ),
      ),
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
          if (state.status?.health.hasIssue == true) ...[
            _HealthBanner(
                info: state.status!.health, onOpenSettings: state.openSettings),
            const SizedBox(height: JadeSpace.sm + 2),
          ],
          if (state.status?.license.showBanner == true) ...[
            _LicenseBanner(info: state.status!.license),
            const SizedBox(height: JadeSpace.sm + 2),
          ],
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
