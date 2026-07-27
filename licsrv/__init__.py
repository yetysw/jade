"""Serveur de licences Jade (Jade) — composant INTERNE, jamais livré au client.

Auto-hébergé (FastAPI + SQLite), exposé via Cloudflare Tunnel + Access token,
comme SearXNG. Chaque client Jade détient une clé opaque `LICENSE_KEY` ; le
serveur vérifie l'abonnement en base et renvoie un JWT Ed25519 à courte durée de
vie (« bail ») que le client vérifie hors ligne (clé publique embarquée) avec
période de grâce. Le kill-switch dur reste la révocation du service token
Cloudflare par client — la licence gère le cycle commercial, pas la coercition.

Ne fait PAS partie du package `ragagent` livré : à déployer séparément côté Jade.
"""

__version__ = "0.2.0"
