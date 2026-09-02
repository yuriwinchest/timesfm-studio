# 🚀 Guia Definitivo de Execução, Versionamento e Deploy — TimesFM Studio

> **Autoridade Operacional:** Este documento é o manual definitivo e canônico para desenvolvedores humanos e assistentes de IA (Claude, Gemini, GPT, Copilot, etc.) sobre como rodar localmente, validar código, versionar no GitHub e realizar o deploy na VPS da Hostinger.

---

## 📌 Sumário Rápido

1. [Visão Geral e Arquitetura de Ambientes](#1-visão-geral-e-arquitetura-de-ambientes)
2. [Como Rodar Localmente (Windows e Linux)](#2-como-rodar-localmente-windows-e-linux)
3. [Fluxo Oficial de Deploy via GitHub (CI/CD Automático)](#3-fluxo-oficial-de-deploy-via-github-cicd-automático)
4. [O que Acontece Dentro da Pipeline do GitHub Actions](#4-o-que-acontece-dentro-da-pipeline-do-github-actions)
5. [O que Acontece Dentro da VPS (`deploy_vps.sh`)](#5-o-que-acontece-dentro-da-vps-deploy_vpssh)
6. [Deploy Manual / Recuperação de Emergência na VPS via SSH](#6-deploy-manual--recuperação-de-emergência-na-vps-via-ssh)
7. [Configuração do Proxy Reverso Caddy e SSL](#7-configuração-do-proxy-reverso-caddy-e-ssl)
8. [Regras de Ouro e Erros Comuns de LLMs (O que NUNCA fazer)](#8-regras-de-ouro-e-erros-comuns-de-llms-o-que-nunca-fazer)

---

## 1. Visão Geral e Arquitetura de Ambientes

O **TimesFM Studio** foi desenhado para operar com isolamento total de recursos:

```
[ Desenvolvedor / LLM ]
         │
         ▼ (git push origin main)
[ Repositório GitHub: yuriwinchest/timesfm-studio ]
         │
         ▼ (GitHub Actions: .github/workflows/deploy.yml)
   [ Job 1: Validação de Sintaxe + Testes de Fumaça ]
         │
         ▼ (Job 2: SSH Deploy com retentativas automáticas)
[ VPS Hostinger (Ambiente Compartilhado) ]
   ├── Diretório: /var/www/timesfm-studio
   ├── Script: bash scripts/deploy_vps.sh
   ├── Caddy Proxy Reverso (porta 80/443 -> 127.0.0.1:8100)
   └── Docker Container: timesfm-studio
         ├── cgroups: 2.0 vCPUs / 3.5GB RAM
         ├── Usuário: appuser (UID 1001)
         ├── Porta: 127.0.0.1:8100
         └── Volumes de Cache: ./hf_cache e ./lottery_cache
```

### Dados de Infraestrutura:
- **Repositório GitHub:** `https://github.com/yuriwinchest/timesfm-studio.git`
- **Branch Principal:** `main`
- **Diretório na VPS:** `/var/www/timesfm-studio`
- **Porta do Container:** `127.0.0.1:8100` (nunca expor em 0.0.0.0 no host!)
- **Proxy Reverso:** Caddy Server (`/etc/caddy/Caddyfile`)

---

## 2. Como Rodar Localmente (Windows e Linux)

### No Windows (Opção Rápida):
Dê dois cliques no arquivo `run_local.bat` na raiz do repositório.

### No Windows via PowerShell / Terminal:
```powershell
# 1. Navegar até o diretório backend
cd d:\Projetos\Clientes\timesfm-studio\backend

# 2. Criar ambiente virtual se ainda não existir
python -m venv ..\.venv

# 3. Ativar o venv
..\.venv\Scripts\Activate.ps1

# 4. Instalar dependências
pip install -r requirements.txt

# 5. Iniciar o servidor com recarregamento automático
uvicorn main:app --host 0.0.0.0 --port 8100 --reload
```

### No Linux / MacOS:
```bash
cd backend
python3 -m venv ../.venv
source ../.venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8100 --reload
```

Acesse no navegador: **`http://localhost:8100`**  
Teste de saúde: **`http://localhost:8100/api/health`**

---

## 3. Fluxo Oficial de Deploy via GitHub (CI/CD Automático)

> ⚠️ **IMPORTANTE:** O deploy em produção é **100% automatizado** pelo GitHub Actions. Toda vez que você fizer `git push origin main`, o pipeline é disparado, valida o código e atualiza o container na VPS.

### Passo a Passo para Subir Correções (Para LLMs e Desenvolvedores):

#### Passo 3.1: Validar Localmente antes de comitar
Antes de enviar o código, execute uma checagem sintática e o teste de fumaça:
```powershell
# Validação de sintaxe dos arquivos Python
python -m py_compile backend/main.py
python -m py_compile backend/engine.py
python -m py_compile backend/lottery_service.py
python -m py_compile backend/ticket_scanner.py
python -m py_compile backend/ticket_checker.py
python -m py_compile backend/ticket_vision.py
python -m py_compile backend/lottery_rules.py
python -m py_compile backend/lottery_history.py

# Teste de fumaça do módulo óptico/OCR (se as dependências estiverem instaladas)
python backend/tests/smoke_scan.py
```

#### Passo 3.2: Verificar o status do Git
```bash
git status
```

#### Passo 3.3: Adicionar os arquivos modificados
```bash
git add .
```

#### Passo 3.4: Criar o commit semântico
```bash
git commit -m "feat/fix: descricao clara da alteracao realizada"
```

#### Passo 3.5: Enviar para a branch `main`
```bash
git push origin main
```

Assim que o comando acima terminar, o GitHub Actions assumirá o deploy.

---

## 4. O que Acontece Dentro da Pipeline do GitHub Actions

O arquivo `.github/workflows/deploy.yml` orquestra duas fases cruciais:

1. **Job `validate` (Lint & Validation):**
   - Roda em um runner `ubuntu-latest`.
   - Compila via `py_compile` todos os módulos Python do backend.
   - Instala as bibliotecas de OCR (`tesseract-ocr`, `libzbar0`, `pytesseract`, `opencv-python-headless`).
   - Roda o teste de fumaça `backend/tests/smoke_scan.py`.
   - Se qualquer teste falhar, o deploy é **abortado imediatamente**, protegendo a VPS.

2. **Job `deploy` (Deploy to Hostinger VPS):**
   - Conecta via SSH na VPS usando os segredos (`VPS_HOST`, `VPS_USER`, `VPS_PASSWORD` ou `VPS_SSH_KEY`).
   - Possui **3 tentativas automáticas** (com pausas de 45s e 120s) para absorver eventuais timeouts intermitentes da VPS Hostinger.
   - Atualiza o código na VPS:
     ```bash
     cd /var/www/timesfm-studio
     git fetch origin main
     git reset --hard origin/main
     bash scripts/deploy_vps.sh
     ```

---

## 5. O que Acontece Dentro da VPS (`deploy_vps.sh`)

O script `scripts/deploy_vps.sh` executa as seguintes etapas no host Linux:

1. **Garante diretórios de Cache:**
   - Cria `hf_cache` (modelos HuggingFace/TimesFM) e `lottery_cache` (histórico de sorteios da Caixa).
   - Ajusta as permissões para o usuário `1001:1001` (`appuser`).
2. **Reconstrói e sobe o Docker Compose:**
   - Executa `docker compose up -d --build`.
   - **NÃO** usa `--remove-orphans` para proteger outros containers coexistentes na VPS (ZYNEXLOG, Largada Brasil, Appwrite, Caddy).
3. **Healthcheck Loop:**
   - Faz até 30 requisições em `http://127.0.0.1:8100/api/health` até o serviço responder HTTP 200.
   - Imprime o status do diagnóstico da Caixa.
   - Emite mensagem de sucesso ou falha com dump dos logs.

---

## 6. Deploy Manual / Recuperação de Emergência na VPS via SSH

Se por qualquer motivo o GitHub Actions estiver fora do ar ou precisar de manutenção manual direta na VPS:

```bash
# 1. Acessar a VPS via SSH
ssh usuario@ip-da-vps

# 2. Entrar no diretório da aplicação
cd /var/www/timesfm-studio

# 3. Puxar as alterações mais recentes da branch main
git fetch origin main
git reset --hard origin/main

# 4. Executar o script de deploy
bash scripts/deploy_vps.sh

# 5. Visualizar logs em tempo real (se necessário)
docker compose logs -f timesfm-studio

# 6. Testar endpoint de saúde
curl -fsS http://127.0.0.1:8100/api/health
```

---

## 7. Configuração do Proxy Reverso Caddy e SSL

O tráfego HTTPS externo é gerenciado pelo Caddy na VPS.

### Arquivo: `/etc/caddy/Caddyfile`
Bloco de configuração correspondente:

```caddy
timesfm.seudominio.com.br {
    encode gzip zstd

    # Proxy para o container isolado do TimesFM Studio
    reverse_proxy 127.0.0.1:8100 {
        header_up Host {host}
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-For {remote_host}
        header_up X-Forwarded-Proto {scheme}
    }

    # Cabeçalhos de segurança
    header {
        X-Content-Type-Options nosniff
        X-Frame-Options DENY
        Referrer-Policy strict-origin-when-cross-origin
    }
}
```

### Comandos de Recarregamento do Caddy:
```bash
# Validar sintaxe do Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile

# Recarregar sem downtime para outros sites
sudo systemctl reload caddy
```

---

## 8. Regras de Ouro e Erros Comuns de LLMs (O que NUNCA fazer)

Para qualquer IA ou desenvolvedor trabalhando neste repositório:

| ❌ O Que NÃO Fazer | ✅ O Que Fazer Corretamente | Motivo Técnico |
| :--- | :--- | :--- |
| **Remover limites de CPU/RAM** do `docker-compose.yml`. | Manter `cpus: '2.0'` e `memory: 3500M`. | Evita que o PyTorch esgote a RAM da VPS e derrube sistemas vizinhos. |
| **Usar `--remove-orphans`** no docker compose. | Usar apenas `docker compose up -d --build`. | A VPS possui containers de outros projetos que seriam deletados acidentalmente. |
| **Commitar `.env` ou senhas**. | Manter `.env` no `.gitignore`. | Proteção inegociável de segredos e credenciais de produção. |
| **Expor porta `0.0.0.0:8100` no host**. | Manter `127.0.0.1:8100:8100` no compose. | Apenas o Caddy local deve ter acesso ao backend. |
| **Usar `chmod 777` em diretórios de produção**. | Usar `chown -R 1001:1001` ou `chmod 775`. | Container roda sob usuário não-root `1001` (`appuser`). |
| **Criar novos arquivos `.py` sem adicionar no `deploy.yml`**. | Adicionar `python -m py_compile backend/novo_arquivo.py` no `deploy.yml`. | Garante que toda a base de código seja testada e validada no CI. |
| **Tentar fazer deploy em branch que não seja `main`**. | Fazer merge/push diretamente para `origin/main`. | O workflow do GitHub Actions só é disparado em `push` na branch `main`. |
