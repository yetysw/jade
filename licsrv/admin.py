"""Interface d'administration des licences — face INTERNE (port local uniquement).

Sert une web-UI minimaliste (une page, sans dépendance externe) et l'API de
gestion : lister, créer, prolonger, révoquer, réactiver. À exposer UNIQUEMENT en
local (le docker-compose publie ce port sur 127.0.0.1). Une protection facultative
par jeton (`LICSRV_ADMIN_TOKEN`) ajoute un garde-fou si le port venait à fuiter.

Lancer (via serve.py, avec l'app publique) : python -m licsrv.serve
"""

from __future__ import annotations

import hmac
import os

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from . import db

_ADMIN_TOKEN = os.environ.get("LICSRV_ADMIN_TOKEN", "").strip()

app = FastAPI(title="Jade License Admin", docs_url=None, redoc_url=None)


def require_admin(x_admin_token: str = Header(default="")) -> None:
    """Garde facultatif : si `LICSRV_ADMIN_TOKEN` est défini, exige l'en-tête
    `X-Admin-Token` correspondant (comparaison à temps constant). Sinon, aucun
    contrôle (le port n'est censé être joignable qu'en local)."""
    if _ADMIN_TOKEN and not hmac.compare_digest(x_admin_token, _ADMIN_TOKEN):
        raise HTTPException(401, "unauthorized")


# Borne haute des durées : 1200 mois = 100 ans. Au-delà, timedelta(days=30*n)
# déclencherait un OverflowError (erreur 500 brute) sur une saisie absurde.
_MAX_MONTHS = 1200


def _clamp_months(months: int) -> int:
    return min(max(1, months), _MAX_MONTHS)


class CreateRequest(BaseModel):
    label: str
    plan: str = "monthly"
    months: int = 1


class ExtendRequest(BaseModel):
    months: int = 1


@app.get("/api/licenses", dependencies=[Depends(require_admin)])
def list_licenses():
    """Liste des licences (sans secret : seul le hash est stocké)."""
    return {"auth": bool(_ADMIN_TOKEN), "licenses": [dict(r) for r in db.list_licenses()]}


@app.post("/api/licenses", dependencies=[Depends(require_admin)])
def create_license(req: CreateRequest):
    """Crée une licence et renvoie la clé EN CLAIR (affichée une seule fois)."""
    label = req.label.strip()
    if not label:
        raise HTTPException(400, "Le libellé est requis.")
    try:
        key = db.create_license(label, req.plan, _clamp_months(req.months))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"key": key, "id": key.split(".")[0]}


@app.post("/api/licenses/{cid}/extend", dependencies=[Depends(require_admin)])
def extend_license(cid: str, req: ExtendRequest):
    if not db.extend(cid, _clamp_months(req.months)):
        raise HTTPException(404, "Licence introuvable.")
    return {"ok": True}


@app.post("/api/licenses/{cid}/revoke", dependencies=[Depends(require_admin)])
def revoke_license(cid: str):
    if not db.set_active(cid, False):
        raise HTTPException(404, "Licence introuvable.")
    return {"ok": True}


@app.post("/api/licenses/{cid}/reactivate", dependencies=[Depends(require_admin)])
def reactivate_license(cid: str):
    if not db.set_active(cid, True):
        raise HTTPException(404, "Licence introuvable.")
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _PAGE


# --------------------------------------------------------------- web-UI

_PAGE = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Jade — Licences</title>
<style>
  :root {
    --bg:#0f1419; --panel:#171e26; --border:#26303c; --text:#e6edf3;
    --muted:#8b98a5; --primary:#3b82f6; --ok:#22c55e; --danger:#ef4444;
    --radius:10px;
  }
  * { box-sizing:border-box; }
  body { margin:0; font:14px/1.5 system-ui,Segoe UI,Roboto,sans-serif;
         background:var(--bg); color:var(--text); }
  .wrap { max-width:960px; margin:0 auto; padding:32px 20px 64px; }
  h1 { font-size:20px; font-weight:600; margin:0 0 4px; }
  .sub { color:var(--muted); margin:0 0 24px; font-size:13px; }
  .card { background:var(--panel); border:1px solid var(--border);
          border-radius:var(--radius); padding:18px; margin-bottom:20px; }
  .card h2 { font-size:14px; font-weight:600; margin:0 0 14px; }
  .row { display:flex; gap:10px; flex-wrap:wrap; align-items:flex-end; }
  label { display:block; font-size:12px; color:var(--muted); margin-bottom:4px; }
  input, select { background:var(--bg); color:var(--text); border:1px solid var(--border);
    border-radius:8px; padding:9px 10px; font:inherit; }
  input:focus, select:focus { outline:none; border-color:var(--primary); }
  .grow { flex:1; min-width:160px; }
  button { border:0; border-radius:8px; padding:9px 14px; font:inherit; font-weight:600;
    cursor:pointer; background:var(--primary); color:#fff; }
  button.ghost { background:transparent; border:1px solid var(--border); color:var(--text);
    font-weight:500; padding:6px 10px; }
  button.danger { color:var(--danger); }
  button:disabled { opacity:.5; cursor:default; }
  table { width:100%; border-collapse:collapse; }
  th, td { text-align:left; padding:10px 8px; border-bottom:1px solid var(--border);
    font-size:13px; vertical-align:middle; }
  th { color:var(--muted); font-weight:500; font-size:12px; }
  td.mono, .mono { font-family:ui-monospace,SFMono-Regular,Consolas,monospace; font-size:12px; }
  .pill { display:inline-block; padding:2px 8px; border-radius:999px; font-size:11px;
    font-weight:600; }
  .pill.ok { background:rgba(34,197,94,.15); color:var(--ok); }
  .pill.off { background:rgba(239,68,68,.15); color:var(--danger); }
  .pill.exp { background:rgba(239,68,68,.15); color:var(--danger); }
  .keybox { background:rgba(59,130,246,.1); border:1px solid var(--primary);
    border-radius:8px; padding:12px; margin-top:12px; }
  .keybox .k { font-family:ui-monospace,monospace; font-size:13px; word-break:break-all;
    user-select:all; display:block; margin-top:6px; }
  .muted { color:var(--muted); }
  .empty { color:var(--muted); padding:24px 8px; text-align:center; }
  .err { color:var(--danger); font-size:13px; margin-top:8px; }
  .actions { display:flex; gap:6px; justify-content:flex-end; }
</style>
</head>
<body>
<div class="wrap">
  <h1>Jade — Gestion des licences</h1>
  <p class="sub">Interface interne Jade. Facturation gérée manuellement dans Odoo :
     créez une licence à l'émission d'une facture, prolongez au renouvellement,
     révoquez en cas de non-paiement.</p>

  <div class="card">
    <h2>Nouvelle licence</h2>
    <div class="row">
      <div class="grow">
        <label>Libellé (nom du client)</label>
        <input id="label" class="grow" placeholder="Cabinet Durand" style="width:100%">
      </div>
      <div>
        <label>Formule</label>
        <select id="plan">
          <option value="monthly">Mensuel</option>
          <option value="quarterly">Trimestriel</option>
        </select>
      </div>
      <div>
        <label>Durée (mois)</label>
        <input id="months" type="number" min="1" value="1" style="width:90px">
      </div>
      <button id="create">Créer</button>
    </div>
    <div id="createErr" class="err" style="display:none"></div>
    <div id="keybox" class="keybox" style="display:none">
      <strong>Clé créée — copiez-la maintenant (non récupérable ensuite) :</strong>
      <span class="k" id="newkey"></span>
    </div>
  </div>

  <div class="card">
    <h2>Licences</h2>
    <table>
      <thead><tr>
        <th>Client</th><th>Formule</th><th>Expiration</th><th>État</th>
        <th>Dernière activité</th><th></th>
      </tr></thead>
      <tbody id="rows"><tr><td colspan="6" class="empty">Chargement…</td></tr></tbody>
    </table>
  </div>
</div>

<script>
const TKEY = 'licsrv_admin_token';
function headers() {
  const h = {'Content-Type':'application/json'};
  const t = localStorage.getItem(TKEY);
  if (t) h['X-Admin-Token'] = t;
  return h;
}
async function api(method, path, body) {
  const res = await fetch(path, {method, headers:headers(),
    body: body ? JSON.stringify(body) : undefined});
  if (res.status === 401) {
    const t = prompt('Jeton d\\'administration (LICSRV_ADMIN_TOKEN) :');
    if (t) { localStorage.setItem(TKEY, t); return api(method, path, body); }
    throw new Error('Authentification requise.');
  }
  if (!res.ok) {
    let d = 'Erreur ' + res.status;
    try { d = (await res.json()).detail || d; } catch(e) {}
    throw new Error(d);
  }
  return res.status === 204 ? null : res.json();
}
function fmtDate(s) { return s ? s.slice(0,10) : '—'; }
function statePill(r) {
  if (!r.active) return '<span class="pill off">révoquée</span>';
  const exp = new Date(r.expires_at);
  if (exp < new Date()) return '<span class="pill exp">expirée</span>';
  return '<span class="pill ok">active</span>';
}
async function refresh() {
  const tbody = document.getElementById('rows');
  try {
    const data = await api('GET', '/api/licenses');
    const rows = data.licenses || [];
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="empty">Aucune licence.</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(r => `
      <tr>
        <td>${escapeHtml(r.label)}<div class="mono muted">${r.id}</div></td>
        <td>${r.plan === 'quarterly' ? 'Trimestriel' : 'Mensuel'}</td>
        <td>${fmtDate(r.expires_at)}</td>
        <td>${statePill(r)}</td>
        <td class="muted">${fmtDate(r.last_seen_at)}</td>
        <td><div class="actions">
          <button class="ghost" onclick="extend('${r.id}')">+1 mois</button>
          ${r.active
            ? `<button class="ghost danger" onclick="setActive('${r.id}','revoke')">Révoquer</button>`
            : `<button class="ghost" onclick="setActive('${r.id}','reactivate')">Réactiver</button>`}
        </div></td>
      </tr>`).join('');
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty">${escapeHtml(e.message)}</td></tr>`;
  }
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => (
    {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
document.getElementById('create').onclick = async () => {
  const btn = document.getElementById('create');
  const err = document.getElementById('createErr');
  err.style.display = 'none';
  btn.disabled = true;
  try {
    const label = document.getElementById('label').value.trim();
    const plan = document.getElementById('plan').value;
    const months = parseInt(document.getElementById('months').value || '1', 10);
    const res = await api('POST', '/api/licenses', {label, plan, months});
    document.getElementById('newkey').textContent = res.key;
    document.getElementById('keybox').style.display = 'block';
    document.getElementById('label').value = '';
    refresh();
  } catch (e) { err.textContent = e.message; err.style.display = 'block'; }
  finally { btn.disabled = false; }
};
async function extend(id) { try { await api('POST', `/api/licenses/${id}/extend`, {months:1}); refresh(); } catch(e){ alert(e.message);} }
async function setActive(id, action) {
  if (action === 'revoke' && !confirm('Révoquer cette licence ? Le poste client se bloquera (après la période de grâce).')) return;
  try { await api('POST', `/api/licenses/${id}/${action}`); refresh(); } catch(e){ alert(e.message);} }
refresh();
</script>
</body>
</html>"""
