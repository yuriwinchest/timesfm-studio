import json
import logging
import time
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional
import numpy as np

from lottery_history import lottery_history
import mirror

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lottery-service")


class LotteryUnavailable(RuntimeError):
    """A Caixa nao respondeu e nao existe dado real em cache para servir.

    Levantada no lugar de devolver resultado fabricado: e melhor a tela dizer que a
    fonte oficial esta fora do ar do que o apostador ver um sorteio que nunca houve.
    """

# Configurações das modalidades de loteria
LOTTERY_CONFIGS = {
    "megasena": {
        "id": "megasena",
        "name": "Mega-Sena",
        "total_numbers": 60,
        "draw_count": 6,
        "start_number": 1,
        "format_digits": 2,
        "color": "#209869",
        "accent": "#00d084",
        "api_endpoint": "https://servicebus2.caixa.gov.br/portaldeloterias/api/megasena",
        "description": "Acerte os 6 números sorteados de 01 a 60."
    },
    "quina": {
        "id": "quina",
        "name": "Quina",
        "total_numbers": 80,
        "draw_count": 5,
        "start_number": 1,
        "format_digits": 2,
        "color": "#260085",
        "accent": "#6a38eb",
        "api_endpoint": "https://servicebus2.caixa.gov.br/portaldeloterias/api/quina",
        "description": "Acerte os 5 números sorteados de 01 a 80."
    },
    "lotofacil": {
        "id": "lotofacil",
        "name": "Lotofácil",
        "total_numbers": 25,
        "draw_count": 15,
        "start_number": 1,
        "format_digits": 2,
        "color": "#930089",
        "accent": "#e056fd",
        "api_endpoint": "https://servicebus2.caixa.gov.br/portaldeloterias/api/lotofacil",
        "description": "Acerte de 11 a 15 números sorteados de 01 a 25."
    },
    "lotomania": {
        "id": "lotomania",
        "name": "Lotomania",
        "total_numbers": 100,
        "draw_count": 20,
        "start_number": 0,
        "format_digits": 2,
        "color": "#f78100",
        "accent": "#ffab40",
        "api_endpoint": "https://servicebus2.caixa.gov.br/portaldeloterias/api/lotomania",
        "description": "Acerte 20 números sorteados de 00 a 99."
    }
}

class LotteryService:
    def __init__(self):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.cache_ttl = 300  # 5 minutos de cache em memória
        self.history_cache: Dict[str, List[Dict[str, Any]]] = {}
        self.last_error: Optional[str] = None

    def get_supported_games(self) -> List[Dict[str, Any]]:
        return list(LOTTERY_CONFIGS.values())

    def fetch_latest_contest(self, game_id: str) -> Dict[str, Any]:
        """Consulta o último concurso diretamente da API oficial da Caixa ou espelhos transparentes com cache resiliente."""
        game_id = game_id.lower()
        if game_id not in LOTTERY_CONFIGS:
            raise ValueError(f"Modalidade de loteria não suportada: {game_id}")

        now = time.time()
        cached = self.cache.get(game_id)
        if cached and (now - cached["timestamp"] < self.cache_ttl):
            return cached["data"]

        try:
            raw_data, source_name = mirror.fetch_latest_with_fallback(game_id)
            parsed = self._parse_caixa_response(game_id, raw_data, source_name=source_name)
            self.cache[game_id] = {"data": parsed, "timestamp": now}
            lottery_history.save_latest(game_id, parsed)
            return parsed

        except Exception as e:
            logger.warning(f"Erro ao consultar API da Caixa/Espelhos para {game_id}: {e}")

            # Cache vencido ainda e dado REAL: melhor servir resultado oficial antigo,
            # devidamente marcado, do que inventar um sorteio.
            if cached:
                stale = dict(cached["data"])
                stale["origem"] = "Ultimo resultado oficial em cache (Caixa/Espelhos indisponiveis)"
                return stale

            # Ultimo recurso ainda REAL: o resultado oficial gravado em disco na
            # ultima consulta bem-sucedida, exibido com a origem declarada.
            from_disk = lottery_history.load_latest(game_id)
            if from_disk:
                from_disk = dict(from_disk)
                from_disk["origem"] = "Ultimo resultado gravado em disco (Caixa/Espelhos indisponiveis)"
                self.cache[game_id] = {"data": from_disk, "timestamp": now}
                return from_disk

            raise LotteryUnavailable(
                f"A API oficial da Caixa e espelhos nao responderam para {LOTTERY_CONFIGS[game_id]['name']} "
                f"({self.last_error or e}) e nao ha resultado real em cache."
            ) from e

    def diagnose(self) -> Dict[str, Any]:
        """
        Testa a fonte oficial e os espelhos transparentes modalidade a modalidade.
        """
        return mirror.diagnose_sources()

    def fetch_contest_by_number(self, game_id: str, contest_number: int) -> Dict[str, Any]:
        """Consulta um concurso específico pelo seu número diretamente na API oficial ou espelhos."""
        game_id = game_id.lower()
        if game_id not in LOTTERY_CONFIGS:
            raise ValueError(f"Modalidade de loteria não suportada: {game_id}")

        cache_key = f"{game_id}_{contest_number}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached["data"]

        config = LOTTERY_CONFIGS[game_id]

        try:
            raw_data, source_name = mirror.fetch_contest_with_fallback(game_id, contest_number)
            parsed = self._parse_caixa_response(game_id, raw_data, source_name=source_name)

            if not parsed.get("dezenas") or int(parsed.get("concurso") or 0) != int(contest_number):
                raise LotteryUnavailable(
                    f"O concurso {contest_number} da {config['name']} ainda nao foi divulgado. "
                    f"Guarde o bilhete e confira apos o sorteio."
                )

            self.cache[cache_key] = {"data": parsed, "timestamp": time.time()}
            return parsed
        except LotteryUnavailable:
            raise
        except Exception as e:
            logger.warning(f"Erro ao consultar concurso {contest_number} da {game_id}: {e}")
            raise LotteryUnavailable(
                f"O concurso {contest_number} da {LOTTERY_CONFIGS[game_id]['name']} nao foi "
                f"devolvido pela Caixa ou espelhos."
            ) from e

    def _parse_caixa_response(self, game_id: str, raw: Dict[str, Any], source_name: Optional[str] = None) -> Dict[str, Any]:
        config = LOTTERY_CONFIGS[game_id]
        
        # Dezenas sorteadas
        dezenas = raw.get("listaDezenas") or raw.get("dezenas") or raw.get("dezenasSorteadasOrdemSorteio") or []
        dezenas_formatadas = [str(d).zfill(config["format_digits"]) for d in dezenas]
        dezenas_formatadas.sort(key=lambda x: int(x))

        # Premiação e rateio
        rateio = []
        for r in raw.get("listaRateioPremio", []):
            rateio.append({
                "faixa": r.get("faixa", 0),
                "descricao": r.get("descricaoFaixa", ""),
                "ganhadores": r.get("numeroDeGanhadores", 0),
                "premio": float(r.get("valorPremio", 0.0))
            })

        return {
            "game_id": game_id,
            "game_name": config["name"],
            "concurso": raw.get("numero") or raw.get("concurso", 0),
            "data_apuracao": raw.get("dataApuracao") or raw.get("data", ""),
            "dezenas": dezenas_formatadas,
            "acumulou": bool(raw.get("acumulado", False)),
            "proximo_concurso": raw.get("numeroConcursoProximo", 0),
            "data_proximo_concurso": raw.get("dataProximoConcurso", ""),
            "valor_estimado_proximo": float(raw.get("valorEstimadoProximoConcurso", 0.0)),
            "valor_arrecadado": float(raw.get("valorArrecadado", 0.0)),
            "local_sorteio": raw.get("localSorteio", "ESPAÇO DA SORTE"),
            "municipio_sorteio": raw.get("nomeMunicipioUFSorteio", "SÃO PAULO, SP"),
            "rateio": rateio,
            "origem": source_name or "API Oficial Loterias Caixa (Tempo Real)"
        }

    MIN_HISTORY = 10

    def fetch_historical_draws(self, game_id: str, count: int = 50) -> List[List[int]]:
        """
        Retorna os sorteios REAIS dos ultimos concursos, do mais antigo ao mais recente.
        """
        config = LOTTERY_CONFIGS[game_id]
        latest = self.fetch_latest_contest(game_id)

        draws = lottery_history.draws(
            game_id=game_id,
            endpoint=config["api_endpoint"],
            latest_contest=int(latest.get("concurso") or 0),
            count=count,
        )

        if len(draws) < self.MIN_HISTORY:
            raise LotteryUnavailable(
                f"So consegui {len(draws)} concursos reais de {config['name']} e a "
                f"analise exige ao menos {self.MIN_HISTORY}. Nao vou preencher a serie com "
                f"dados inventados - tente novamente em instantes."
            )

        return draws

    def calculate_lottery_signals(self, game_id: str, draws: List[List[int]]) -> Dict[str, Any]:
        """
        Calcula as métricas de frequência, atraso (delay), recência e tendência temporal
        de cada uma das dezenas da modalidade para alimentar o modelo TimesFM.
        """
        config = LOTTERY_CONFIGS[game_id]
        total_num = config["total_numbers"]
        start_num = config["start_number"]
        num_draws = len(draws)

        # Matriz binária: [concursos, dezenas]
        matrix = np.zeros((num_draws, total_num), dtype=np.float32)
        for t, draw in enumerate(draws):
            for num in draw:
                idx = num - start_num
                if 0 <= idx < total_num:
                    matrix[t, idx] = 1.0

        number_stats = []
        for i in range(total_num):
            num = i + start_num
            num_str = str(num).zfill(config["format_digits"])
            
            appearances = matrix[:, i]
            freq_total = int(np.sum(appearances))
            freq_recent_10 = int(np.sum(appearances[-10:]))
            
            # Cálculo de atraso (quantos concursos sem ser sorteado)
            indices = np.where(appearances == 1)[0]
            if len(indices) > 0:
                delay = (num_draws - 1) - int(indices[-1])
            else:
                delay = num_draws

            # Frequência móvel (série temporal para o TimesFM)
            moving_freq = []
            window = 5
            for w in range(window, num_draws + 1):
                moving_freq.append(float(np.mean(appearances[w-window:w])))

            number_stats.append({
                "number": num,
                "number_str": num_str,
                "total_frequency": freq_total,
                "recent_frequency": freq_recent_10,
                "delay": delay,
                "series": moving_freq if len(moving_freq) >= 4 else appearances.tolist()
            })

        return {
            "game_id": game_id,
            "total_draws_analyzed": num_draws,
            "stats": number_stats,
            "matrix": matrix
        }

lottery_service = LotteryService()
