"""Préférences utilisateur persistées dans le registre Windows (HKCU).

Utilisé pour retenir l'état du mode incognito d'une session à l'autre. Local à
l'utilisateur Windows courant (HKEY_CURRENT_USER) : aucune donnée de contenu,
seulement des drapeaux d'interface.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

_KEY = r"Software\Jade\Jade"


def get_bool(name: str, default: bool = False) -> bool:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KEY) as k:
            val, _ = winreg.QueryValueEx(k, name)
            return bool(val)
    except FileNotFoundError:
        return default
    except (OSError, ImportError):
        return default


def set_bool(name: str, value: bool) -> None:
    try:
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _KEY) as k:
            winreg.SetValueEx(k, name, 0, winreg.REG_DWORD, 1 if value else 0)
    except (OSError, ImportError) as e:
        log.warning("Écriture de la préférence « %s » dans le registre échouée : %s", name, e)
