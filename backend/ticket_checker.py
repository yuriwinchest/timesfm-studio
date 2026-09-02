"""
Conferencia oficial de bilhetes contra o resultado real da Caixa.

Esta e a unica fonte de verdade da conferencia. O frontend nao calcula acerto,
nao decide faixa e nao inventa premio: ele apenas exibe o que sai daqui.
"""

import logging
import re
from typing import Any, Dict, List, Optional

from lottery_service import LOTTERY_CONFIGS, LotteryUnavailable, lottery_service
from lottery_rules import BET_SIZE_RULES, NUMBER_RANGE_RULES

logger = logging.getLogger("ticket-checker")


def normalize_numbers(raw_numbers: List[Any], game_id: str) -> List[str]:
    """Normaliza dezenas para o formato oficial de 2 digitos, sem duplicatas."""
    low, high = NUMBER_RANGE_RULES.get(game_id, (0, 99))
    normalized: List[str] = []
    seen = set()

    for item in raw_numbers:
        digits = re.sub(r"\D", "", str(item))
        if not digits:
            continue
        value = int(digits)
        if value < low or value > high:
            raise ValueError(
                f"A dezena {digits} esta fora do intervalo valido "
                f"({low:02d} a {high:02d}) para {LOTTERY_CONFIGS[game_id]['name']}."
            )
        key = str(value).zfill(2)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(key)

    return sorted(normalized, key=int)


def validate_bet_size(numbers: List[str], game_id: str) -> None:
    minimum, maximum = BET_SIZE_RULES[game_id]
    if len(numbers) < minimum:
        raise ValueError(
            f"Aposta incompleta: {len(numbers)} dezenas informadas e a "
            f"{LOTTERY_CONFIGS[game_id]['name']} exige no minimo {minimum}."
        )
    if len(numbers) > maximum:
        raise ValueError(
            f"Aposta invalida: {len(numbers)} dezenas informadas e o maximo da "
            f"{LOTTERY_CONFIGS[game_id]['name']} e {maximum}."
        )


def _band_hits(descricao: str) -> Optional[int]:
    """Extrai a quantidade de acertos da descricao oficial da faixa (ex.: '15 acertos')."""
    match = re.match(r"\s*(\d+)", descricao or "")
    return int(match.group(1)) if match else None


def check_ticket(game_id: str, raw_numbers: List[Any], contest_number: Optional[int] = None) -> Dict[str, Any]:
    """
    Confere um bilhete contra o resultado oficial e devolve acertos, faixa e premio.

    Regra dura: nada e completado nem estimado. Se a aposta nao respeitar as regras
    da modalidade, levanta ValueError e a conferencia nao acontece.
    """
    game_id = (game_id or "").lower()
    if game_id not in LOTTERY_CONFIGS:
        raise ValueError(f"Modalidade nao suportada: {game_id}")

    numbers = normalize_numbers(raw_numbers, game_id)
    validate_bet_size(numbers, game_id)

    if contest_number:
        requested = int(contest_number)
        try:
            contest = lottery_service.fetch_contest_by_number(game_id, requested)
        except LotteryUnavailable as e:
            raise ValueError(str(e)) from e

        # O fetch cai para o ultimo concurso quando a Caixa nao devolve o pedido, o que
        # acontece com bilhete de sorteio que ainda nao ocorreu. Conferir contra outro
        # concurso seria dar um resultado falso ao apostador.
        if int(contest.get("concurso") or 0) != requested:
            raise ValueError(
                f"O concurso {requested} da {LOTTERY_CONFIGS[game_id]['name']} ainda nao "
                f"foi divulgado pela Caixa. O ultimo disponivel e o "
                f"{contest.get('concurso')} - guarde o bilhete e confira apos o sorteio."
            )
    else:
        contest = lottery_service.fetch_latest_contest(game_id)

    official = contest.get("dezenas", [])
    official_set = set(official)
    hits = [n for n in numbers if n in official_set]
    hit_count = len(hits)

    band_description = None
    prize = 0.0
    winners = 0
    is_winner = False

    for band in contest.get("rateio", []):
        if _band_hits(band.get("descricao", "")) == hit_count:
            band_description = band.get("descricao")
            prize = float(band.get("premio", 0.0))
            winners = int(band.get("ganhadores", 0))
            is_winner = True
            break

    return {
        "game_id": game_id,
        "game_name": LOTTERY_CONFIGS[game_id]["name"],
        "contest": contest.get("concurso"),
        "contest_date": contest.get("data_apuracao"),
        "official_numbers": official,
        "user_numbers": numbers,
        "hit_numbers": hits,
        "hit_count": hit_count,
        "is_winner": is_winner,
        "band_description": band_description or "Nenhuma faixa premiada",
        "prize": prize,
        "band_winners": winners,
        "source": contest.get("origem"),
    }
