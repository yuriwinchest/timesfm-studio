# ðŸ“‹ Documento de Passagem de BastÃ£o & Handover TÃ©cnico â€” TimesFM Studio

> **Data de AtualizaÃ§Ã£o:** 31 de Agosto de 2026  
> **Autor da Entrega Inicial:** TONE (Tech Lead & Arquiteto) / Gemini 3.7  
> **RepositÃ³rio Oficial:** [https://github.com/yuriwinchest/timesfm-studio](https://github.com/yuriwinchest/timesfm-studio)  
> **Status Geral:** âœ… **Fase 1 ConcluÃ­da & Publicada em ProduÃ§Ã£o (VPS via CI/CD)**

---

## ðŸŽ¯ 1. VisÃ£o Geral do Projeto

O **TimesFM Studio** Ã© uma plataforma visual e API assÃ­ncrona voltada para previsÃ£o (*forecasting*) de sÃ©ries temporais utilizando o modelo fundacional **Google TimesFM** (*Time Series Foundation Model*).

O sistema foi arquitetado para rodar de forma **100% isolada** tanto localmente (notebook Windows) quanto na nuvem (VPS Hostinger), garantindo consumo controlado de recursos e convivÃªncia segura com outros sistemas existentes na mesma VPS (Caddy, Appwrite, ZYNEXLOG, Largada Brasil, etc.).

---

## ðŸ—ï¸ 2. Arquitetura do Sistema

```
[ Navegador / UsuÃ¡rio ]
          â”‚
          â–¼ (HTTPS - SSL Let's Encrypt)
[ Caddy Proxy Reverso (VPS Hostinger) ]
          â”‚
          â–¼ (Proxy interno na porta 127.0.0.1:8100)
[ Docker Container: timesfm-studio ]
 â”œâ”€â”€ [ Limites cgroups: max 2.0 vCPUs, max 3.5GB RAM ]
 â”œâ”€â”€ [ Frontend SPA Glassmorphism ]
 â”‚     â”œâ”€â”€ Chart.js interativo (HistÃ³rico + ProjeÃ§Ã£o + Bandas de ConfianÃ§a de 90%)
 â”‚     â”œâ”€â”€ Presets com 1 clique (LogÃ­stica ZynexLog, E-commerce, Infraestrutura)
 â”‚     â”œâ”€â”€ Upload de arquivos CSV / Excel com auto-detecÃ§Ã£o de colunas
 â”‚     â”œâ”€â”€ Painel de mÃ©tricas (TendÃªncia %, MÃ©dia, MÃ­n/MÃ¡x, LatÃªncia em ms)
 â”‚     â””â”€â”€ ExportaÃ§Ã£o de resultados para CSV
 â””â”€â”€ [ Backend FastAPI (Python 3.11) ]
       â”œâ”€â”€ /api/health    -> DiagnÃ³stico do motor e status de hardware
       â”œâ”€â”€ /api/presets   -> Retorna datasets ricos de demonstraÃ§Ã£o
       â”œâ”€â”€ /api/forecast  -> Motor PyTorch CPU TimesFM 200M + Fallback estatÃ­stico
       â””â”€â”€ /api/upload-csv -> Leitor e sanitizador de planilhas
```

---

## ðŸ“‚ 3. Estrutura de Arquivos e FunÃ§Ãµes

```
d:\Projetos\Clientes\timesfm-studio\
â”œâ”€â”€ backend/
â”‚   â”œâ”€â”€ engine.py              # Motor do TimesFM com PyTorch CPU + Fallback analÃ­tico resiliente
â”‚   â”œâ”€â”€ main.py                # API FastAPI com rotas REST e montagem do frontend estÃ¡tico
â”‚   â””â”€â”€ requirements.txt       # DependÃªncias enxutas (FastAPI, Uvicorn, Pandas, NumPy, etc.)
â”œâ”€â”€ frontend/
â”‚   â”œâ”€â”€ index.html             # Dashboard Dark Mode em layout executivo
â”‚   â”œâ”€â”€ style.css              # Design System sob medida (Deep Navy, Neon Cyan, Glassmorphism)
â”‚   â””â”€â”€ app.js                 # Controlador com Chart.js, chamadas de API e parse de CSV
â”œâ”€â”€ .github/
â”‚   â””â”€â”€ workflows/
â”‚       â””â”€â”€ deploy.yml         # Pipeline CI/CD que constrÃ³i e atualiza a VPS a cada 'git push'
â”œâ”€â”€ Dockerfile                 # Container Debian slim com PyTorch CPU e usuÃ¡rio nÃ£o-root (appuser)
â”œâ”€â”€ docker-compose.yml         # Orquestrador Docker com restriÃ§Ãµes rÃ­gidas de CPU e RAM
â”œâ”€â”€ Caddyfile.snippet          # Bloco de configuraÃ§Ã£o pronto para o Caddy da VPS
â”œâ”€â”€ run_local.bat              # Script de execuÃ§Ã£o rÃ¡pida para Windows
â”œâ”€â”€ AGENTS.md                  # Regras operacionais para assistentes de IA subsequentes
â”œâ”€â”€ HANDOVER.md                # Este documento de passagem de bastÃ£o
â””â”€â”€ README.md                  # Guia de introduÃ§Ã£o rÃ¡pida
```

---

## â˜ï¸ 4. Mapeamento de Infraestrutura e Credenciais

| Recurso | IdentificaÃ§Ã£o / Valor | ObservaÃ§Ãµes |
| :--- | :--- | :--- |
| **RepositÃ³rio GitHub** | `yuriwinchest/timesfm-studio` | RepositÃ³rio pÃºblico/ativo com branch `main`. |
| **Pipeline CI/CD** | GitHub Actions (`deploy.yml`) | Segredos `VPS_HOST`, `VPS_USER` e `VPS_PASSWORD` jÃ¡ configurados no repo. |
| **VPS Hostinger** | `179.198.97.28` (Porta SSH padrÃ£o 22) | UsuÃ¡rio: `root`. Pasta da aplicaÃ§Ã£o: `/var/www/timesfm-studio`. |
| **Porta Interna do Container** | `127.0.0.1:8100` | Mapeada estritamente para localhost (inacessÃ­vel diretamente da web). |
| **DomÃ­nio / SubdomÃ­nio** | `timesfm.yuriwinchester.com.br` | Apontamento DNS tipo `A` apontando para `179.198.97.28`. |
| **Proxy Reverso & SSL** | Caddy (`/etc/caddy/Caddyfile`) | Emite e renova certificado SSL automaticamente. |
| **Banco de Dados (Appwrite)** | `https://db.largadabrasil.com` | Base de dados criada: **`timesfm_studio`**. |

---

## ðŸš¦ 5. O que estÃ¡ ConcluÃ­do vs. O que a PrÃ³xima IA Deve Fazer

### âœ… O que estÃ¡ 100% Pronto e Funcional:
1. **Frontend Completo:** Visual moderno, grÃ¡ficos interativos com Chart.js, 3 presets de sÃ©ries temporais, drag-and-drop de planilhas CSV/Excel e exportaÃ§Ã£o.
2. **Backend FastAPI:** Endpoints de inferÃªncia, verificaÃ§Ã£o de saÃºde e serviÃ§o de arquivos estÃ¡ticos integrados.
3. **Motor de InferÃªncia HÃ­brido:** `engine.py` pronto para carregar pesos do TimesFM da Google via PyTorch CPU, com fallback analÃ­tico imediato para evitar travamentos.
4. **Deploy Automatizado:** `git push origin main` roda validaÃ§Ã£o e atualiza o container na VPS automaticamente.
5. **Base de Dados Appwrite:** Database `timesfm_studio` instanciada no servidor Appwrite.

---

### ðŸ“Œ Backlog para a PrÃ³xima IA (PrÃ³ximos Passos):

1. **AutenticaÃ§Ã£o de UsuÃ¡rios via Appwrite (Fase 2):**
   - Criar coleÃ§Ãµes no banco `timesfm_studio` para gerenciar usuÃ¡rios e permissÃµes.
   - Adicionar tela de Login / Registro na interface com SDK web do Appwrite.
2. **HistÃ³rico de PrevisÃµes Salvas:**
   - Criar uma coleÃ§Ã£o `forecast_history` no Appwrite para armazenar previsÃµes passadas e permitir reabrir grÃ¡ficos anteriores.
3. **Suporte a MÃºltiplas Colunas / CovariÃ¡veis (XReg):**
   - Expandir a ingestÃ£o de CSV para aceitar sÃ©ries multivariadas (ex: preÃ§o, feriados, promoÃ§Ãµes correlacionadas com a demanda).
4. **Webhooks / Alertas de Anomalias:**
   - Criar gatilhos para alertar quando uma sÃ©rie temporal ultrapassar os limites projetados pelo modelo.

---

## ðŸ”’ 6. Regras CrÃ­ticas que NUNCA Devem ser Quebradas

1. **Nunca remova as travas de recursos no `docker-compose.yml` (`cpus: '2.0'` e `memory: 3500M`).** A VPS hospeda outros clientes e serviÃ§os essenciais (Caddy, Appwrite, ZYNEXLOG, Largada Brasil). Exceder esses limites pode derrubar os outros sites.
2. **Nunca publique senhas ou tokens em commits ou arquivos versionados.** Todos os segredos de CI/CD devem ser mantidos exclusivamente no GitHub Secrets.
3. **Todo deploy deve passar pelo GitHub Actions (`git push origin main`).** Nunca faÃ§a alteraÃ§Ãµes manuais de arquivos diretamente no disco da VPS sem commitar.
