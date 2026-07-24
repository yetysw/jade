"""Administration des licences (CLI locale — jamais exposée au réseau).

  python -m licsrv.manage add "Cabinet Durand" --plan monthly
  python -m licsrv.manage extend <id> --months 1
  python -m licsrv.manage revoke <id>
  python -m licsrv.manage reactivate <id>
  python -m licsrv.manage list

`add` affiche la clé EN CLAIR une seule fois : la transmettre au client, elle
n'est plus jamais récupérable (seul son hash est stocké).
"""

from __future__ import annotations

import argparse
import sys

from . import db


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="licsrv.manage", description="Gestion des licences Jade")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="Créer un client")
    a.add_argument("label")
    a.add_argument("--plan", choices=["monthly", "quarterly"], default="monthly")
    a.add_argument("--months", type=int, default=1, help="durée initiale (mois)")

    e = sub.add_parser("extend", help="Prolonger l'abonnement")
    e.add_argument("id")
    e.add_argument("--months", type=int, default=1)

    r = sub.add_parser("revoke", help="Désactiver (soft) une licence")
    r.add_argument("id")
    ra = sub.add_parser("reactivate", help="Réactiver une licence")
    ra.add_argument("id")

    sub.add_parser("list", help="Lister les licences")

    args = p.parse_args(argv)

    if args.cmd == "add":
        key = db.create_license(args.label, args.plan, args.months)
        print("Licence créée. CLÉ (à copier maintenant, non récupérable ensuite) :")
        print(f"\n    {key}\n")
        print(f"id = {key.split('.')[0]}  ·  plan = {args.plan}  ·  {args.months} mois")
        return 0
    if args.cmd == "extend":
        ok = db.extend(args.id, args.months)
        print("Prolongé." if ok else "id introuvable."); return 0 if ok else 1
    if args.cmd == "revoke":
        ok = db.set_active(args.id, False)
        print("Révoqué." if ok else "id introuvable."); return 0 if ok else 1
    if args.cmd == "reactivate":
        ok = db.set_active(args.id, True)
        print("Réactivé." if ok else "id introuvable."); return 0 if ok else 1
    if args.cmd == "list":
        rows = db.list_licenses()
        if not rows:
            print("(aucune licence)"); return 0
        for r in rows:
            state = "actif" if r["active"] else "REVOQUE"
            print(f"{r['id']}  {state:8}  {r['plan']:9}  exp {r['expires_at'][:10]}  "
                  f"vu {r['last_seen_at'][:10] if r['last_seen_at'] else '—'}  {r['label']}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
