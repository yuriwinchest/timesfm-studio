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

STANDARD_BET_SIZES = {
    "megasena": 6,
    "quina": 5,
    "lotofacil": 15,
    "lotomania": 50,
}


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
    if len(numbers) > maximum * 4:
        raise ValueError(
            f"Aposta invalida: {len(numbers)} dezenas informadas ultrapassam o limite maximo."
        )


def _band_hits(descricao: str) -> Optional[int]:
    """Extrai a quantidade de acertos da descricao oficial da faixa (ex.: '15 acertos' ou '3 acertos')."""
    match = re.match(r"\s*(\d+)", descricao or "")
    return int(match.group(1)) if match else None


def check_ticket(
    game_id: str,
    raw_numbers: List[Any],
    contest_number: Optional[int] = None,
    games: Optional[List[List[Any]]] = None
) -> Dict[str, Any]:
    """
    Confere um bilhete contra o resultado oficial e devolve acertos, faixa e premio.
    Suporta bilhetes simples e bilhetes com multiplos jogos (ex: Jogo A, Jogo B).
    """
    game_id = (game_id or "").lower()
    if game_id not in LOTTERY_CONFIGS:
        raise ValueError(f"Modalidade nao suportada: {game_id}")

    # Consulta concurso oficial na Caixa ou espelho
    if contest_number:
        requested = int(contest_number)
        try:
            contest = lottery_service.fetch_contest_by_number(game_id, requested)
        except LotteryUnavailable as e:
            raise ValueError(str(e)) from e

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

    # Identificar jogos individuais se houver múltiplos jogos no comprovante
    standard_size = STANDARD_BET_SIZES.get(game_id, 6)
    games_list: List[List[str]] = []

    if games and len(games) > 1:
        for g in games:
            norm_g = normalize_numbers(g, game_id)
            if norm_g:
                games_list.append(norm_g)
        flat_numbers = sorted(list(set([n for g in games_list for n in g])), key=int)
    else:
        flat_numbers = normalize_numbers(raw_numbers, game_id)
        validate_bet_size(flat_numbers, game_id)
        if len(flat_numbers) > standard_size and (len(flat_numbers) % standard_size == 0):
            for i in range(0, len(flat_numbers), standard_size):
                games_list.append(flat_numbers[i:i + standard_size])
        else:
            games_list.append(flat_numbers)

    hits_global = [n for n in flat_numbers if n in official_set]

    # Avaliar premiação de cada jogo individual
    games_results = []
    total_prize = 0.0
    best_hit_count = 0
    best_band_desc = None
    any_winner = False

    for idx, g_numbers in enumerate(games_list):
        g_hits = [n for n in g_numbers if n in official_set]
        g_hit_count = len(g_hits)
        if g_hit_count > best_hit_count:
            best_hit_count = g_hit_count

        g_band = None
        g_prize = 0.0
        g_winners = 0
        g_is_winner = False

        for band in contest.get("rateio", []):
            if _band_hits(band.get("descricao", "")) == g_hit_count:
                g_band = band.get("descricao")
                g_prize = float(band.get("premio", 0.0))
                g_winners = int(band.get("ganhadores", 0))
                g_is_winner = True
                any_winner = True
                total_prize += g_prize
                if not best_band_desc:
                    best_band_desc = g_band
                break

        game_label = f"Jogo {chr(65 + idx)}" if len(games_list) > 1 else "Seu Jogo"
        games_results.append({
            "game_label": game_label,
            "numbers": g_numbers,
            "hit_numbers": g_hits,
            "hit_count": g_hit_count,
            "is_winner": g_is_winner,
            "band_description": g_band or "Sem premiação",
            "prize": g_prize,
            "band_winners": g_winners,
        })

    return {
        "game_id": game_id,
        "game_name": LOTTERY_CONFIGS[game_id]["name"],
        "contest": contest.get("concurso"),
        "contest_date": contest.get("data_apuracao"),
        "official_numbers": official,
        "user_numbers": flat_numbers,
        "hit_numbers": hits_global,
        "hit_count": best_hit_count if len(games_list) > 1 else len(hits_global),
        "is_winner": any_winner,
        "band_description": best_band_desc or "Nenhuma faixa premiada",
        "prize": total_prize,
        "source": contest.get("origem"),
        "games_results": games_results,
    }
