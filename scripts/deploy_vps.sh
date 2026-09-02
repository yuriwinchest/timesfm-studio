#!/usr/bin/env bash
#
# Passos do deploy executados DENTRO da VPS.
#
# Fica em arquivo, e nao embutido no workflow, porque o passo de SSH e repetido em
# tentativas: a conexao do runner do GitHub com esta maquina falha de forma
# intermitente ("dial tcp :22: i/o timeout"), e triplicar o script inteiro no YAML
# seria triplicar o lugar onde um ajuste pode ser esquecido.
#
# Precisa ser idempotente: pode rodar duas vezes se a primeira tentativa cair depois
# de ja ter feito parte do trabalho.
set -euo pipefail

echo "==> Preparando diretorios de cache"

# Modelos do HuggingFace (TimesFM)
mkdir -p hf_cache
chmod -R 777 hf_cache

# Historico oficial da Caixa. O container roda como uid 1001, entao o diretorio
# precisa ser gravavel por ele; sem isso o historico e rebuscado a cada subida.
mkdir -p lottery_cache
chmod -R 777 lottery_cache

echo "==> Subindo container isolado (limites de CPU e RAM no compose)"
docker compose up -d --build --remove-orphans

echo "==> Aguardando a aplicacao responder"
for tentativa in $(seq 1 30); do
    if curl -fsS --max-time 5 http://127.0.0.1:8100/api/health > /dev/null 2>&1; then
        echo "Aplicacao respondendo apos ${tentativa} verificacao(oes)."

        echo "==> Estado da fonte oficial da Caixa vista de dentro da VPS"
        curl -fsS --max-time 60 http://127.0.0.1:8100/api/lottery/source-status || \
            echo "(endpoint de diagnostico ainda nao disponivel nesta versao)"
        echo

        echo "Deploy concluido com sucesso!"
        exit 0
    fi
    sleep 4
done

echo "ERRO: a aplicacao nao respondeu em /api/health apos o deploy." >&2
docker compose logs --tail 60 timesfm-studio >&2
exit 1
