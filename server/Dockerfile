# Dockerfile du serveur Jarvis (F5.3). Image CPU par défaut.
FROM python:3.12-slim

WORKDIR /app

# Dépendances système minimales (audio/soundfile).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Dépendances Python (couche cache).
COPY server/requirements.txt server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt

# Code serveur + build frontend (doit être généré avant : npm run build).
COPY server/ server/
COPY web/dist/ web/dist/

WORKDIR /app/server
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
