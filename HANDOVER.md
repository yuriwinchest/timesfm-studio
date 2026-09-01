# 📋 Documento de Passagem de Bastão & Handover Técnico — TimesFM Studio

> **Data de Atualização:** 01 de Setembro de 2026  
> **Autor da Entrega:** TONE (Tech Lead & Arquiteto) / Gemini 3.7  
> **Repositório Oficial:** [https://github.com/yuriwinchest/timesfm-studio](https://github.com/yuriwinchest/timesfm-studio)  
> **Status Geral:** ✅ **Módulo de Loterias Caixa (Mega-Sena, Quina, Lotofácil, Lotomania) & TimesFM 100% Integrados e Operacionais**

---

## 🎯 1. Visão Geral do Projeto

O **TimesFM Studio** é uma plataforma visual executiva e API REST de alta performance voltada para previsão (*forecasting*) de séries temporais com o modelo fundacional **Google TimesFM** (*Time Series Foundation Model*) e modelagem estocástica e temporal dos sorteios das **Loterias Federais da Caixa Econômica Federal** (Mega-Sena, Quina, Lotofácil e Lotomania).

O sistema opera de forma **100% isolada e resiliente** em ambiente local (Windows) e em nuvem na VPS da Hostinger, sob limites rígidos de cgroups (`2.0 CPUs` e `3.5GB RAM`), convivendo harmoniosamente com os demais serviços em produção.

---

## 🏛️ 2. Arquitetura do Sistema

```
[ Navegador / Usuário ]
          │
          ▼ (HTTPS - SSL Let's Encrypt / Caddy)
[ Caddy Proxy Reverso (VPS Hostinger) ]
          │
          ▼ (Proxy interno na porta 127.0.0.1:8100)
[ Docker Container: timesfm-studio ]
 ├── [ Limites cgroups: max 2.0 vCPUs, max 3.5GB RAM ]
 ├── [ Frontend SPA Glassmorphism ]
 │     ├── Seletor de Modalidades Caixa (Mega-Sena, Quina, Lotofácil, Lotomania)
 │     ├── Esferas 3D de Loteria com iluminação esférica e cores oficiais
 │     ├── Card de Projeção IA TimesFM (Jogo Principal, Quentes, Atrasadas, Score)
 │     ├── Card do Último Concurso Oficial Caixa (Dezenas sorteadas, Rateio, Comparativo de Acertos)
 │     ├── Análise Espectral das Dezenas (Filtros: Todas, Mais Quentes, Mais Atrasadas, IA)
 │     ├── Gráfico Chart.js interativo de probabilidades
 │     └── Módulo de Séries Temporais Gerais (ZynexLog, E-commerce, Upload CSV)
 └── [ Backend FastAPI (Python 3.11) ]
       ├── /api/health            -> Diagnóstico do motor, status de CPU e loterias suportadas
       ├── /api/lottery/games     -> Retorna as configurações das modalidades suportadas
       ├── /api/lottery/info/{id} -> Consulta em tempo real o último concurso oficial na Caixa
       ├── /api/lottery/predict   -> Modelagem de séries temporais TimesFM e geração de apostas
       ├── /api/presets           -> Séries temporais de demonstração
       ├── /api/forecast          -> Previsão de séries temporais genéricas
       └── /api/upload-csv        -> Leitor e analisador de planilhas
```

---

## 📂 3. Estrutura de Arquivos e Funções

```
d:\Projetos\Clientes\timesfm-studio\
├── backend/
│   ├── lottery_service.py      # Integração direta com a API da Caixa (servicebus2.caixa.gov.br) + Cache com TTL
│   ├── engine.py              # Motor TimesFM com modelagem de dezenas, cálculo de atraso e reversão de ciclo
│   ├── main.py                # API FastAPI com rotas REST de loterias e séries temporais
│   └── requirements.txt       # Dependências Python (FastAPI, Uvicorn, Pandas, NumPy, etc.)
├── frontend/
│   ├── index.html             # Dashboard Dark Mode com esferas 3D e seletor de loterias
│   ├── style.css              # Design System Glassmorphism com identidades oficiais (Verde, Azul, Magenta, Laranja)
│   └── app.js                 # Controlador reativo, Chart.js, cálculo de acertos e cópia de bilhetes
├── .github/
│   └── workflows/
│       └── deploy.yml         # Pipeline CI/CD que constrói e atualiza a VPS a cada 'git push'
├── Dockerfile                 # Container Debian slim com PyTorch CPU e usuário não-root (appuser)
├── docker-compose.yml         # Orquestrador Docker com restrições de CPU e RAM
├── Caddyfile.snippet          # Bloco de configuração para o Caddy da VPS
├── run_local.bat              # Script de execução rápida para Windows
├── AGENTS.md                  # Regras operacionais para assistentes de IA subsequentes
├── HANDOVER.md                # Este documento de passagem de bastão
└── README.md                  # Guia de introdução rápida
```

---

## ☁️ 4. Mapeamento de Infraestrutura e Credenciais

| Recurso | Identificação / Valor | Observações |
| :--- | :--- | :--- |
| **Repositório GitHub** | `yuriwinchest/timesfm-studio` | Repositório com branch `main`. |
| **Pipeline CI/CD** | GitHub Actions (`deploy.yml`) | Segredos `VPS_HOST`, `VPS_USER` e `VPS_PASSWORD` no GitHub Secrets. |
| **VPS Hostinger** | Configurada via GitHub Secrets | Protegida por firewall e chaves SSH. |
| **Porta Interna do Container** | `127.0.0.1:8100` | Mapeada estritamente para localhost. |
| **Domínio / Subdomínio** | `timesfm.yuriwinchester.com.br` | Apontamento DNS protegido por SSL/TLS. |
| **Proxy Reverso & SSL** | Caddy (`/etc/caddy/Caddyfile`) | Emissão e renovação automática de certificado SSL. |
| **API Externa de Loterias** | `servicebus2.caixa.gov.br` | Endpoints REST públicos da Caixa Econômica Federal. |
| **Segurança do `.env`** | Arquivo local `.env` | **Protegido no `.gitignore`**. NUNCA versionado no Git. |

---

## 🚦 5. Funcionalidades do Módulo de Loterias

1. **Ingestão Oficial Caixa:**
   - Consulta direta dos sorteios em tempo real via REST oficial da Caixa para `megasena`, `quina`, `lotofacil` e `lotomania`.
   - Exibição de número do concurso, data de apuração, local (`Espaço da Sorte, SP`), dezenas sorteadas, indicador de acúmulo e tabela detalhada de rateio de prêmios por faixa.
2. **Modelagem Temporal com Google TimesFM:**
   - Vetorização dos sorteios em matrizes de sinais temporais por número.
   - Análise de frequência ponderada, recência e fator de atraso (*delay / mean reversion*).
   - Inferência com TimesFM para gerar ranking probabilístico de todas as dezenas.
3. **Estratégias de Jogos Gerados:**
   - **Jogo Otimizado IA:** Equilíbrio estatístico de paridade, soma média e cobertura.
   - **Jogo Momentum (Quentes):** Foco nas dezenas de maior tração recente.
   - **Jogo Reversão de Ciclo (Atrasadas):** Prioriza dezenas com atraso histórico acentuado.
4. **Comparativo de Acertos:**
   - Confronta as dezenas da projeção IA com as dezenas reais do último concurso oficial, destacando visualmente as dezenas sorteadas acertadas.

---

## 🔒 6. Regras Críticas que NUNCA Devem ser Quebradas

1. **Nunca remova as travas de recursos no `docker-compose.yml` (`cpus: '2.0'` e `memory: 3500M`).**
2. **Nunca publique senhas, chaves ou o arquivo `.env` no GitHub.**
3. **Todo deploy deve passar pelo GitHub Actions (`git push origin main`).**
