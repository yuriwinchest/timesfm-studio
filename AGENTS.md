# InstruÃ§Ãµes para Assistentes de IA & Engenheiros â€” TimesFM Studio

> Este documento Ã© a autoridade tÃ©cnica para qualquer assistente de inteligÃªncia artificial (Claude, Gemini, GPT, Copilot ou outro) ou desenvolvedor humano que for realizar modificaÃ§Ãµes, expansÃµes ou correÃ§Ãµes no repositÃ³rio **TimesFM Studio**.

---

## 1. PrincÃ­pios Operacionais InegociÃ¡veis

1. **Isolamento de Recursos:**
   - Este serviÃ§o roda em uma VPS compartilhada da Hostinger junto a outros projetos de produÃ§Ã£o (ZYNEXLOG, Largada Brasil, Caddy, Appwrite).
   - O `docker-compose.yml` **NUNCA** deve ter seus limites de recursos removidos (`cpus: 2.0` e `memory: 3500M`).
   - O PyTorch CPU deve manter a restriÃ§Ã£o de threads (`torch.set_num_threads(MAX_CPU_THREADS)`).

2. **Fluxo de Deploy (CI/CD Exclusivo):**
   - NÃ£o realize deploys manuais via SSH ou ediÃ§Ã£o direta na VPS.
   - Qualquer modificaÃ§Ã£o deve ser commitada e enviada para a branch `main`:
     ```bash
     git add .
     git commit -m "feat/fix: descricao da alteracao"
     git push origin main
     ```
   - O GitHub Actions (`.github/workflows/deploy.yml`) executarÃ¡ o build e atualizarÃ¡ o container na VPS de forma atÃ´mica.

3. **Design System & UX:**
   - A interface utiliza Vanilla CSS com Glassmorphism Dark Mode e componentes reativos com Chart.js.
   - NÃ£o adicione bibliotecas genÃ©ricas de UI (Material UI, Bootstrap, etc.) que destruam a identidade visual executiva do projeto.
   - Toda renderizaÃ§Ã£o numÃ©rica deve respeitar formataÃ§Ã£o monetÃ¡ria e de pontuaÃ§Ã£o em PortuguÃªs do Brasil (`pt-BR`) e fontes numÃ©ricas monoespaÃ§adas (`JetBrains Mono`).

4. **Banco de Dados (Appwrite):**
   - InstÃ¢ncia: `https://db.largadabrasil.com`
   - Database ID: `timesfm_studio`
   - Toda nova coleÃ§Ã£o criada para usuÃ¡rios, histÃ³rico de previsÃµes ou mÃ©tricas deve ser documentada em `HANDOVER.md`.

---

## 2. Mapa RÃ¡pido da Arquitetura

```
timesfm-studio/
  â”œâ”€â”€ backend/
  â”‚     â”œâ”€â”€ main.py        -> Ponto de entrada FastAPI e rotas REST
  â”‚     â”œâ”€â”€ engine.py      -> Motor TimesFM PyTorch CPU e lÃ³gica de fallback
  â”‚     â””â”€â”€ requirements.txt -> DependÃªncias Python
  â”œâ”€â”€ frontend/
  â”‚     â”œâ”€â”€ index.html     -> Layout do Dashboard e seletores
  â”‚     â”œâ”€â”€ style.css      -> Tokens de design e CSS moderno
  â”‚     â””â”€â”€ app.js         -> Controlador do Chart.js e interaÃ§Ãµes
  â”œâ”€â”€ Dockerfile           -> Imagem de produÃ§Ã£o otimizada para CPU
  â”œâ”€â”€ docker-compose.yml   -> OrquestraÃ§Ã£o com restriÃ§Ã£o cgroups
  â”œâ”€â”€ Caddyfile.snippet    -> Bloco de proxy reverso Caddy para o subdomÃ­nio
  â””â”€â”€ HANDOVER.md          -> Registro histÃ³rico e estado atual do projeto
```

---

## 3. Comandos Ãšteis

### Rodar Localmente (Windows):
```powershell
cd backend
python -m venv ..\.venv
..\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8100 --reload
```

### Verificar SaÃºde da API:
```bash
curl http://localhost:8100/api/health
```
