# Serveur de licences Jade (INTERNE — jamais livré au client).
# Un seul conteneur, deux ports : public (verify) + admin local (web-UI).
# Contexte de build = ce dossier (licsrv/). La base et la clé privée vivent dans
# le volume /data (jamais dans l'image) : voir .dockerignore et docker-compose.yml.
FROM python:3.12-slim

WORKDIR /app

# dépendances d'abord (cache de couche)
COPY requirements.txt /app/licsrv/requirements.txt
RUN pip install --no-cache-dir -r /app/licsrv/requirements.txt

# code du paquet
COPY . /app/licsrv/

# la base SQLite et la clé privée Ed25519 sont persistées hors image (volume)
ENV LICSRV_DB=/data/licenses.db \
    LICSRV_PRIVATE_KEY=/data/keys/license_ed25519.pem \
    LICSRV_PUBLIC_PORT=8790 \
    LICSRV_ADMIN_PORT=8791 \
    PYTHONUNBUFFERED=1

EXPOSE 8790 8791
VOLUME ["/data"]

CMD ["python", "-m", "licsrv.serve"]
