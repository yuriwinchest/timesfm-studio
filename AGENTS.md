# Instruções para Assistentes de IA & Engenheiros — TimesFM Studio

> Este documento é a autoridade técnica para qualquer assistente de inteligência artificial (Claude, Gemini, GPT, Copilot ou outro) ou desenvolvedor humano que for realizar modificações, expansões ou correções no repositório **TimesFM Studio**.
>
> 📖 **Para o guia completo de deploy, execução e CI/CD, consulte:** [DEPLOY.md](file:///d:/Projetos/Clientes/timesfm-studio/DEPLOY.md)

---

## 1. Princípios Operacionais Inegociáveis

1. **Isolamento de Recursos:**
   - Este serviço roda em uma VPS compartilhada da Hostinger junto a outros projetos de produção (ZYNEXLOG, Largada Brasil, Caddy, Appwrite).
   - O `docker-compose.yml` **NUNCA** deve ter seus limites de recursos removidos (`cpus: '2.0'` e `memory: 3500M`).
   - O PyTorch CPU deve manter a restrição de threads (`torch.set_num_threads(MAX_CPU_THREADS)`).
   - **NUNCA** use `--remove-orphans` no `docker compose`.

2. **Fluxo de Deploy (CI/CD Exclusivo via GitHub):**
   - Não realize deploys manuais via SSH ou edição direta na VPS sem necessidade.
   - Qualquer modificação deve ser validada e enviada para a branch `main`:
     ```bash
     git add .
     git commit -m "feat/fix: descricao da alteracao"
     git push origin main
     ```
   - O GitHub Actions (`.github/workflows/deploy.yml`) executará a compilação, testes de fumaça e atualizará o container na VPS de forma atômica via `scripts/deploy_vps.sh`.

3. **Design System & UX:**
   - A interface utiliza Vanilla CSS com Glassmorphism Dark Mode e componentes reativos com Chart.js.
   - Não adicione bibliotecas genéricas de UI (Material UI, Bootstrap, etc.) que destruam a identidade visual executiva do projeto.
   - Toda renderização numérica deve respeitar formatação monetária e de pontuação em Português do Brasil (`pt-BR`) e fontes numéricas monoespaçadas (`JetBrains Mono`).

4. **Banco de Dados (Appwrite):**
   - Instância: `https://db.largadabrasil.com`
   - Database ID: `timesfm_studio`
   - Toda nova coleção criada para usuários, histórico de previsões ou métricas deve ser documentada em `HANDOVER.md`.

---

## 2. Mapa Rápido da Arquitetura

```
timesfm-studio/
  ├── backend/
  │     ├── main.py            -> Ponto de entrada FastAPI e rotas REST
  │     ├── engine.py          -> Motor TimesFM PyTorch CPU e lógica de fallback
  │     ├── lottery_service.py -> Integração oficial Caixa com cache
  │     ├── ticket_scanner.py  -> Scanner e OCR de bilhetes de loteria
  │     └── requirements.txt   -> Dependências Python
  ├── frontend/
  │     ├── index.html         -> Layout do Dashboard e seletores
  │     ├── style.css          -> Tokens de design e CSS moderno
  │     └── app.js             -> Controlador do Chart.js e interações
  ├── scripts/
  │     └── deploy_vps.sh      -> Script de deploy executado na VPS pelo CI/CD
  ├── .github/workflows/
  │     └── deploy.yml         -> Pipeline GitHub Actions (validação + SSH deploy)
  ├── Dockerfile               -> Imagem de produção otimizada para CPU
  ├── docker-compose.yml       -> Orquestração com restrição cgroups
  ├── Caddyfile.snippet        -> Bloco de proxy reverso Caddy para o subdomínio
  ├── DEPLOY.md                -> Manual detalhado de execução, git e deploy
  └── HANDOVER.md              -> Registro histórico e estado atual do projeto
```

---

## 3. Comandos Úteis

### Rodar Localmente (Windows):
```powershell
cd backend
python -m venv ..\.venv
..\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8100 --reload
```

### Verificar Saúde da API:
```bash
curl http://localhost:8100/api/health
```

### Validação Pré-Push:
```powershell
python -m py_compile backend/main.py backend/engine.py backend/lottery_service.py backend/ticket_scanner.py
python backend/tests/smoke_scan.py
```
