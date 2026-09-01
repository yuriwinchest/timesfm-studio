# Dockerfile para o TimesFM Studio (Otimizado para CPU e VPS)
FROM python:3.11-slim

# Metadados
LABEL maintainer=ZYNEXLOG Tech Team
LABEL description=TimesFM Studio - Time Series Foundation Model by Google Research

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MAX_CPU_THREADS=2 \
    PORT=8100

WORKDIR /app

# Instala dependências de compilação essenciais
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Instala PyTorch específico para CPU primeiro (camada de cache)
RUN pip install --no-cache-dir torch>=2.0.0 --index-url https://download.pytorch.org/whl/cpu

# Copia e instala dependências Python do backend
COPY backend/requirements.txt /app/backend/
RUN pip install --no-cache-dir -r /app/backend/requirements.txt
RUN pip install --no-cache-dir timesfm

# Copia o código da aplicação
COPY backend/ /app/backend/
COPY frontend/ /app/frontend/

# Cria usuário não-root para segurança
RUN useradd -u 1001 -m appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8100

WORKDIR /app/backend

# Inicia o servidor ASGI Uvicorn
CMD [uvicorn, main:app, --host, 0.0.0.0, --port, 8100, --workers, 1]
