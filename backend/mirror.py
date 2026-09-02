"""
Módulo de Espelhos e Alta Disponibilidade para Loterias Caixa.

Motivo de Existência:
A API oficial da Caixa (servicebus2.caixa.gov.br) fica atrás do WAF/CDN Azion, que
bloqueia requisições originadas de certos ranges de IP de Datacenters/Cloud (como VPS
da Hostinger), devolvendo HTTP 403 Forbidden em ~20ms.

Este módulo implementa uma arquitetura de alta disponibilidade:
1. Sempre tenta a fonte oficial da Caixa primeiro (servicebus2.caixa.gov.br).
2. Se a Caixa falhar (403, 429, 502, Timeout), recorre automaticamente a espelhos
   transparentes de alta fidelidade (como api.guidi.dev.br e loteriascaixa-api.herokuapp.com)
   que preservam o schema JSON original com dezenas, acumulados e rateio completos.
3. Declara explicitamente a procedência do dado (Origem Oficial vs Espelho Declarado).
"""

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("lottery-mirror")

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://loterias.caixa.gov.br/",
}

# Lista de fontes ordenadas por prioridade: Oficial sempre em 1º lugar
MIRROR_SOURCES = [
    {
        "id": "caixa_oficial",
        "nome": "API Oficial Loterias Caixa (Tempo Real)",
        "url_latest": "https://servicebus2.caixa.gov.br/portaldeloterias/api/{game}",
        "url_contest": "https://servicebus2.caixa.gov.br/portaldeloterias/api/{game}/{contest}",
        "is_official": True,
    },
    {
        "id": "guidi_mirror",
        "nome": "Espelho Transparente Caixa (api.guidi.dev.br)",
        "url_latest": "https://api.guidi.dev.br/loteria/{game}/ultimo",
        "url_contest": "https://api.guidi.dev.br/loteria/{game}/{contest}",
        "is_official": False,
    },
    {
        "id": "loteriascaixa_api",
        "nome": "Espelho de Contingência (loteriascaixa-api.herokuapp.com)",
        "url_latest": "https://loteriascaixa-api.herokuapp.com/api/{game}/latest",
        "url_contest": "https://loteriascaixa-api.herokuapp.com/api/{game}/{contest}",
        "is_official": False,
    },
]


def _request_json(url: str, timeout: int = 10) -> Dict[str, Any]:
    """Executa requisição HTTP GET retornando o JSON decodificado."""
    req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        content = response.read().decode("utf-8", errors="replace")
        return json.loads(content)


def fetch_latest_with_fallback(game_id: str) -> Tuple[Dict[str, Any], str]:
    """
    Busca o último concurso de uma modalidade tentando a Caixa oficial e depois os espelhos.
    Retorna uma tupla: (payload_json, nome_da_fonte).
    """
    erros = []
    for source in MIRROR_SOURCES:
        url = source["url_latest"].format(game=game_id)
        try:
            inicio = time.time()
            data = _request_json(url, timeout=8)
            duracao_ms = round((time.time() - inicio) * 1000)

            # Validar se o payload retornado tem os campos essenciais do sorteio
            numero = data.get("numero") or data.get("concurso")
            dezenas = data.get("listaDezenas") or data.get("dezenas") or data.get("dezenasSorteadasOrdemSorteio")
            if numero and dezenas:
                logger.info(
                    "Concurso %s obtido com sucesso via %s em %dms",
                    game_id,
                    source["nome"],
                    duracao_ms,
                )
                return data, source["nome"]
        except urllib.error.HTTPError as e:
            erros.append(f"{source['id']}: HTTP {e.code} {e.reason}")
            logger.debug("Fonte %s indisponível para %s: HTTP %s", source["id"], game_id, e.code)
        except Exception as e:
            erros.append(f"{source['id']}: {type(e).__name__} ({e})")
            logger.debug("Fonte %s falhou para %s: %s", source["id"], game_id, e)

    raise RuntimeError(f"Todas as fontes falharam para {game_id}: {'; '.join(erros)}")


def fetch_contest_with_fallback(game_id: str, contest: int) -> Tuple[Dict[str, Any], str]:
    """
    Busca um concurso específico pelo número tentando a Caixa oficial e depois os espelhos.
    Retorna uma tupla: (payload_json, nome_da_fonte).
    """
    erros = []
    for source in MIRROR_SOURCES:
        url = source["url_contest"].format(game=game_id, contest=contest)
        try:
            data = _request_json(url, timeout=8)
            numero = data.get("numero") or data.get("concurso")
            dezenas = data.get("listaDezenas") or data.get("dezenas") or data.get("dezenasSorteadasOrdemSorteio")
            if numero and dezenas:
                return data, source["nome"]
        except Exception as e:
            erros.append(f"{source['id']}: {e}")

    raise RuntimeError(f"Concurso {contest} da {game_id} indisponível em todas as fontes: {'; '.join(erros)}")


def fetch_history_draw_with_fallback(game_id: str, contest: int) -> Tuple[int, List[str]]:
    """
    Busca as dezenas de um concurso histórico usando a cadeia de fontes resiliente.
    Retorna (contest_number, lista_de_dezenas).
    """
    for source in MIRROR_SOURCES:
        url = source["url_contest"].format(game=game_id, contest=contest)
        try:
            data = _request_json(url, timeout=6)
            dezenas = data.get("listaDezenas") or data.get("dezenas") or data.get("dezenasSorteadasOrdemSorteio")
            if dezenas:
                return contest, [str(d).zfill(2) for d in dezenas]
        except Exception:
            continue
    return contest, []


def diagnose_sources() -> Dict[str, Any]:
    """
    Verifica a latência e o status de cada fonte (Oficial e Espelhos) para diagnóstico.
    """
    diagnostico = {}
    for source in MIRROR_SOURCES:
        url = source["url_latest"].format(game="megasena")
        inicio = time.time()
        try:
            data = _request_json(url, timeout=8)
            duracao_ms = round((time.time() - inicio) * 1000)
            diagnostico[source["id"]] = {
                "nome": source["nome"],
                "ok": True,
                "concurso": data.get("numero") or data.get("concurso"),
                "latencia_ms": duracao_ms,
            }
        except urllib.error.HTTPError as e:
            duracao_ms = round((time.time() - inicio) * 1000)
            diagnostico[source["id"]] = {
                "nome": source["nome"],
                "ok": False,
                "erro": f"HTTP {e.code} {e.reason}",
                "latencia_ms": duracao_ms,
            }
        except Exception as e:
            duracao_ms = round((time.time() - inicio) * 1000)
            diagnostico[source["id"]] = {
                "nome": source["nome"],
                "ok": False,
                "erro": f"{type(e).__name__}: {e}",
                "latencia_ms": duracao_ms,
            }
    return diagnostico
