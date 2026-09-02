"""
Historico real de sorteios das Loterias Caixa.

Este modulo existe para matar uma mentira que estava no coracao do produto: o
historico que alimentava o modelo era gerado com np.random.choice e semente fixa.
De 60 concursos, 59 eram inventados. Toda a analise de frequencia, dezenas quentes,
atrasadas e o score de confianca eram, na pratica, modelagem de ruido pseudoaleatorio
apresentada como previsao.

Aqui o historico vem concurso a concurso da API oficial da Caixa. Concurso sorteado e
imutavel, entao cada um e buscado uma unica vez e gravado em disco - a partir dai o
custo e zero. Se um concurso nao vier, ele fica de fora: a serie encolhe e o sistema
diz quantos concursos reais sustentam a analise. Nada e completado com invencao.
"""

import json
import logging
import os
import random
import tempfile
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

logger = logging.getLogger("lottery-history")

CAIXA_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Referer": "https://loterias.caixa.gov.br/",
}

# A Caixa responde 429 quando levamos a serio o "quanto mais rapido melhor": 8 workers
# varrendo as quatro modalidades de uma vez derrubaram a consulta. 4 workers com pausa
# entre lotes trazem 60 concursos em poucos segundos e nao provocam bloqueio.
MAX_WORKERS = 4
REQUEST_TIMEOUT = 12
BATCH_SIZE = 12
BATCH_PAUSE = 1.2
RETRY_BACKOFF = (2.0, 5.0, 9.0)


class LotteryHistory:
    """Busca e mantem em cache o historico oficial de dezenas sorteadas."""

    def __init__(self, cache_dir: Optional[str] = None):
        self.cache_dir = self._resolve_cache_dir(cache_dir)
        self._memory: Dict[str, Dict[int, List[str]]] = {}
        self._lock = threading.Lock()

    def _resolve_cache_dir(self, preferred: Optional[str]) -> str:
        """Escolhe um diretorio gravavel: o container monta /app/backend como read-only."""
        candidates = [
            preferred,
            os.environ.get("LOTTERY_CACHE_DIR"),
            "/app/cache",
            os.path.join(tempfile.gettempdir(), "timesfm-lottery-cache"),
        ]
        for candidate in candidates:
            if not candidate:
                continue
            try:
                os.makedirs(candidate, exist_ok=True)
                probe = os.path.join(candidate, ".escrita")
                with open(probe, "w", encoding="utf-8") as fh:
                    fh.write("ok")
                os.remove(probe)
                logger.info("Cache de historico em %s", candidate)
                return candidate
            except Exception:
                continue

        logger.warning("Nenhum diretorio de cache gravavel: historico sera buscado a cada vez.")
        return ""

    # ------------------------------------------------------------------
    # Cache em disco (concurso sorteado nunca muda)
    # ------------------------------------------------------------------
    def _cache_path(self, game_id: str) -> str:
        return os.path.join(self.cache_dir, f"{game_id}_historico.json") if self.cache_dir else ""

    def _load(self, game_id: str) -> Dict[int, List[str]]:
        if game_id in self._memory:
            return self._memory[game_id]

        stored: Dict[int, List[str]] = {}
        path = self._cache_path(game_id)
        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    raw = json.load(fh)
                stored = {int(k): v for k, v in raw.items() if v}
                logger.info("Historico de %s carregado do disco: %d concursos", game_id, len(stored))
            except Exception as e:
                logger.warning("Cache de %s ilegivel (%s); sera refeito.", game_id, e)

        self._memory[game_id] = stored
        return stored

    def _persist(self, game_id: str, stored: Dict[int, List[str]]) -> None:
        path = self._cache_path(game_id)
        if not path:
            return
        try:
            temporary = f"{path}.tmp"
            with open(temporary, "w", encoding="utf-8") as fh:
                json.dump({str(k): v for k, v in stored.items()}, fh)
            os.replace(temporary, path)
        except Exception as e:
            logger.warning("Nao consegui gravar o cache de %s: %s", game_id, e)

    # ------------------------------------------------------------------
    # Busca oficial
    # ------------------------------------------------------------------
    def _fetch_one(self, endpoint: str, contest: int) -> tuple:
        """Busca um concurso, recuando quando a Caixa sinaliza excesso de chamadas."""
        for tentativa, espera in enumerate((0.0,) + RETRY_BACKOFF):
            if espera:
                time.sleep(espera + random.uniform(0, 0.6))
            try:
                request = urllib.request.Request(f"{endpoint}/{contest}", headers=CAIXA_HEADERS)
                with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                dezenas = payload.get("listaDezenas") or payload.get("dezenasSorteadasOrdemSorteio") or []
                return contest, [str(d).zfill(2) for d in dezenas]
            except urllib.error.HTTPError as e:
                if e.code != 429:
                    logger.debug("Concurso %s indisponivel: %s", contest, e)
                    return contest, []
                logger.debug("429 no concurso %s (tentativa %d)", contest, tentativa + 1)
            except Exception as e:
                logger.debug("Concurso %s indisponivel: %s", contest, e)
                return contest, []

        logger.info("Concurso %s desistiu apos sucessivos 429 da Caixa", contest)
        return contest, []

    def draws(self, game_id: str, endpoint: str, latest_contest: int, count: int) -> List[List[int]]:
        """
        Devolve ate `count` sorteios REAIS, do mais antigo para o mais recente.

        So retorna concurso que a Caixa confirmou. Se parte da janela nao vier, a serie
        volta menor - e quem consome precisa dizer ao usuario com quantos concursos
        reais a analise foi feita.
        """
        if latest_contest <= 0:
            return []

        wanted = [n for n in range(max(1, latest_contest - count + 1), latest_contest + 1)]

        with self._lock:
            stored = self._load(game_id)
            missing = [n for n in wanted if n not in stored]

        if missing:
            logger.info("Buscando %d concursos de %s na Caixa (%d ja em cache)",
                        len(missing), game_id, len(wanted) - len(missing))
            results = []
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
                for inicio in range(0, len(missing), BATCH_SIZE):
                    lote = missing[inicio:inicio + BATCH_SIZE]
                    results.extend(pool.map(lambda n: self._fetch_one(endpoint, n), lote))
                    if inicio + BATCH_SIZE < len(missing):
                        time.sleep(BATCH_PAUSE)

            with self._lock:
                stored = self._load(game_id)
                for contest, dezenas in results:
                    if dezenas:
                        stored[contest] = dezenas
                self._memory[game_id] = stored
                self._persist(game_id, stored)

        draws = []
        for contest in wanted:
            dezenas = stored.get(contest)
            if dezenas:
                draws.append([int(d) for d in dezenas])

        faltantes = len(wanted) - len(draws)
        if faltantes:
            logger.info("%s: %d concursos da janela nao estao disponiveis na Caixa", game_id, faltantes)

        return draws

    # ------------------------------------------------------------------
    # Ultimo concurso completo (com rateio) persistido em disco
    # ------------------------------------------------------------------
    def save_latest(self, game_id: str, data: dict) -> None:
        """Guarda o ultimo resultado OFICIAL para sobreviver a um 429 no arranque."""
        path = os.path.join(self.cache_dir, f"{game_id}_ultimo.json") if self.cache_dir else ""
        if not path:
            return
        try:
            temporary = f"{path}.tmp"
            with open(temporary, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False)
            os.replace(temporary, path)
        except Exception as e:
            logger.warning("Nao consegui gravar o ultimo concurso de %s: %s", game_id, e)

    def load_latest(self, game_id: str) -> Optional[dict]:
        """Le o ultimo resultado oficial gravado. E dado real, apenas possivelmente antigo."""
        path = os.path.join(self.cache_dir, f"{game_id}_ultimo.json") if self.cache_dir else ""
        if not path or not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return None

    def cached_count(self, game_id: str) -> int:
        with self._lock:
            return len(self._load(game_id))


lottery_history = LotteryHistory()
