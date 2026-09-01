# TimesFM Studio — Google Research Foundation Model

Interface moderna, inteligente e isolada para previsão de séries temporais utilizando o modelo fundacional **Google TimesFM** (*Time Series Foundation Model*).

---

## 📁 Estrutura do Projeto

`
d:\Projetos\Clientes\timesfm-studio\
├── backend/
│   ├── engine.py          # Motor de inferência (PyTorch CPU + TimesFM + fallback estatístico)
│   ├── main.py            # API FastAPI com endpoints REST e arquivos estáticos
│   └── requirements.txt   # Dependências Python enxutas
├── frontend/
│   ├── index.html         # Dashboard executivo em Dark Mode
│   ├── style.css          # Estilos glassmorphism e responsividade
│   └── app.js             # Controlador com Chart.js, presets e importação CSV
├── Dockerfile             # Container otimizado com PyTorch CPU
├── docker-compose.yml     # Limites rígidos de CPU (2.0) e RAM (3.5GB) para proteção da VPS
├── Caddyfile.snippet      # Configuração para o Caddy da VPS com SSL automático
└── run_local.bat          # Inicializador rápido para Windows
`

---

## 🚀 1. Executando Localmente no seu Notebook (Windows)

1. Abra a pasta d:\Projetos\Clientes\timesfm-studio.
2. Dê dois cliques em un_local.bat **OU** rode via terminal:

`powershell
cd d:\Projetos\Clientes\timesfm-studio\backend
python -m venv ..\.venv
..\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8100 --reload
`

3. Abra no navegador: **http://localhost:8100**

---

## ☁️ 2. Deploy Isolado na VPS Hostinger

### Passo 1: Transferir a pasta para a VPS
Na VPS, clone ou envie a pasta para /var/www/timesfm-studio:

`ash
# Na VPS:
mkdir -p /var/www/timesfm-studio
# Suba os arquivos do timesfm-studio para lá
`

### Passo 2: Subir o Container Docker Isolado

`ash
cd /var/www/timesfm-studio
docker compose up -d --build
`

O container subirá na porta interna 127.0.0.1:8100 com limite de 2 vCPUs e 3.5GB de RAM.

### Passo 3: Configurar o Subdomínio no Caddy

1. Edite o Caddyfile da VPS:
`ash
sudo nano /etc/caddy/Caddyfile
`

2. Cole o bloco abaixo (substituindo pelo seu subdomínio apontado na Hostinger):
`caddy
timesfm.seudominio.com.br {
    encode gzip zstd
    reverse_proxy 127.0.0.1:8100
}
`

3. Recarregue o Caddy sem derrubar as conexões existentes:
`ash
sudo systemctl reload caddy
`

Pronto! Seu **TimesFM Studio** estará no ar em https://timesfm.seudominio.com.br com certificado SSL automático e sem qualquer risco para os outros sites da VPS.
