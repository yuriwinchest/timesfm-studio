# TimesFM Studio — Google Research Foundation Model

Interface moderna, inteligente e isolada para previsão de séries temporais utilizando o modelo fundacional **Google TimesFM** (*Time Series Foundation Model*) e modelagem estocástica de loterias federais da Caixa Econômica Federal.

---

## 📖 Documentação & Guias

- **[DEPLOY.md](file:///d:/Projetos/Clientes/timesfm-studio/DEPLOY.md):** Manual completo de deploy, execução local, CI/CD no GitHub Actions e VPS.
- **[AGENTS.md](file:///d:/Projetos/Clientes/timesfm-studio/AGENTS.md):** Diretrizes e regras inegociáveis para assistentes de IA e engenheiros.
- **[HANDOVER.md](file:///d:/Projetos/Clientes/timesfm-studio/HANDOVER.md):** Registro histórico da arquitetura e das funcionalidades entregues.

---

## 📁 Estrutura do Projeto

```
timesfm-studio/
├── backend/
│   ├── engine.py          # Motor de inferência (PyTorch CPU + TimesFM + fallback estocástico)
│   ├── lottery_service.py # Integração Caixa Econômica Federal + Cache
│   ├── ticket_scanner.py  # Scanner OCR / Leitor de bilhetes
│   ├── main.py            # API FastAPI com endpoints REST
│   └── requirements.txt   # Dependências Python enxutas
├── frontend/
│   ├── index.html         # Dashboard executivo em Dark Mode (Glassmorphism)
│   ├── style.css          # Estilos glassmorphism e responsividade
│   └── app.js             # Controlador com Chart.js, presets e conferência de jogos
├── scripts/
│   └── deploy_vps.sh      # Script de deploy executado na VPS
├── .github/workflows/
│   └── deploy.yml         # Pipeline CI/CD GitHub Actions
├── Dockerfile             # Container otimizado com PyTorch CPU
├── docker-compose.yml     # Limites rígidos de CPU (2.0) e RAM (3.5GB) para proteção da VPS
├── Caddyfile.snippet      # Configuração para o Caddy da VPS com SSL automático
└── run_local.bat          # Inicializador rápido para Windows
```

---

## 🚀 1. Executando Localmente no Windows

1. Abra a pasta `d:\Projetos\Clientes\timesfm-studio`.
2. Dê dois cliques em `run_local.bat` **OU** rode via terminal:

```powershell
cd d:\Projetos\Clientes\timesfm-studio\backend
python -m venv ..\.venv
..\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8100 --reload
```

3. Abra no navegador: **`http://localhost:8100`**

---

## ☁️ 2. Deploy na VPS Hostinger (CI/CD Automático)

Todo o deploy é automatizado via GitHub Actions ao realizar push na branch `main`:

```bash
git add .
git commit -m "feat/fix: descricao da alteracao"
git push origin main
```

Para detalhes completos e deploy manual de emergência, leia [DEPLOY.md](file:///d:/Projetos/Clientes/timesfm-studio/DEPLOY.md).
