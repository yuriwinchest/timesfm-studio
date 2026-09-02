"""
Sonda de acesso a fonte oficial da Caixa.

Motivo de existir: a VPS recebe "HTTP 403 Forbidden" em ~20ms da API da Caixa,
enquanto a mesma chamada, com os mesmos cabecalhos, responde em 300-600ms da maquina
de desenvolvimento. 20ms nao e viagem de rede - e recusa na borda, de um WAF.

Sem acesso a um terminal na VPS, descobrir o que passa exige que o proprio servidor
teste as alternativas e reporte. Esta sonda tenta variacoes de cabecalho, sessao com
cookie e formatos de URL, e devolve qual delas atravessa. Nao adivinha: mede.
"""

import http.cookiejar
import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List

logger = logging.getLogger("lottery-probe")

ENDPOINT = "https://servicebus2.caixa.gov.br/portaldeloterias/api/megasena"
PORTAL = "https://loterias.caixa.gov.br/Paginas/Mega-Sena.aspx"

UA_CHROME = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
             "Chrome/122.0.0.0 Safari/537.36")

ESTRATEGIAS: List[Dict[str, Any]] = [
    {
        "nome": "atual (o que esta em producao)",
        "headers": {
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://loterias.caixa.gov.br/",
        },
    },
    {
        "nome": "sem nenhum cabecalho extra",
        "headers": {},
    },
    {
        "nome": "navegador completo (sec-ch-ua, sec-fetch, encoding)",
        "headers": {
            "User-Agent": UA_CHROME,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "pt-BR,pt;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "sec-ch-ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Linux"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "Origin": "https://loterias.caixa.gov.br",
            "Referer": "https://loterias.caixa.gov.br/",
        },
    },
    {
        "nome": "navegador completo + cookie obtido no portal",
        "headers": {
            "User-Agent": UA_CHROME,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "pt-BR,pt;q=0.9",
            "Connection": "keep-alive",
            "Origin": "https://loterias.caixa.gov.br",
            "Referer": "https://loterias.caixa.gov.br/",
        },
        "cookie": True,
    },
    {
        "nome": "url com barra final",
        "url": ENDPOINT + "/",
        "headers": {"User-Agent": UA_CHROME, "Accept": "application/json"},
    },
    {
        "nome": "concurso explicito na url",
        "url": ENDPOINT + "/3051",
        "headers": {"User-Agent": UA_CHROME, "Accept": "application/json"},
    },
]


def _com_cookie(url: str, headers: Dict[str, str], timeout: int = 15) -> Dict[str, Any]:
    """Visita o portal primeiro para receber cookie do WAF, depois chama a API."""
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    try:
        opener.open(urllib.request.Request(PORTAL, headers={"User-Agent": headers.get("User-Agent", UA_CHROME)}),
                    timeout=timeout).read(2048)
    except Exception as e:
        logger.info("Portal nao respondeu na etapa de cookie: %s", e)

    resposta = opener.open(urllib.request.Request(url, headers=headers), timeout=timeout)
    return {"corpo": resposta.read(1500).decode("utf-8", errors="replace"),
            "cookies": len(jar)}


def executar() -> Dict[str, Any]:
    """Roda todas as estrategias e devolve qual atravessa o bloqueio."""
    resultados = []

    for estrategia in ESTRATEGIAS:
        url = estrategia.get("url", ENDPOINT)
        inicio = time.time()
        registro: Dict[str, Any] = {"estrategia": estrategia["nome"]}

        try:
            if estrategia.get("cookie"):
                saida = _com_cookie(url, estrategia["headers"])
                corpo = saida["corpo"]
                registro["cookies_recebidos"] = saida["cookies"]
            else:
                requisicao = urllib.request.Request(url, headers=estrategia["headers"])
                with urllib.request.urlopen(requisicao, timeout=15) as resposta:
                    corpo = resposta.read(1500).decode("utf-8", errors="replace")

            registro["ok"] = True
            try:
                registro["concurso"] = json.loads(corpo).get("numero")
            except Exception:
                registro["amostra"] = corpo[:120]

        except urllib.error.HTTPError as e:
            registro["ok"] = False
            registro["erro"] = f"HTTP {e.code} {e.reason}"
            registro["servidor"] = e.headers.get("Server") if e.headers else None
            try:
                registro["corpo_erro"] = e.read(200).decode("utf-8", errors="replace")
            except Exception:
                pass
        except Exception as e:
            registro["ok"] = False
            registro["erro"] = f"{type(e).__name__}: {e}"

        registro["ms"] = round((time.time() - inicio) * 1000)
        resultados.append(registro)

    vencedoras = [r["estrategia"] for r in resultados if r.get("ok")]
    return {
        "endpoint": ENDPOINT,
        "estrategias_que_passaram": vencedoras,
        "detalhe": resultados,
    }
