"""
Leitura de comprovantes fisicos das Loterias Caixa.

Estrategia real (nao existe atalho magico aqui):

1. O QR Code impresso no comprovante da Caixa NAO carrega as dezenas apostadas em
   texto legivel. Ele carrega um payload opaco que so o app oficial resolve contra
   os servidores da Caixa. Portanto o QR serve para: (a) identificar o comprovante,
   (b) eventualmente extrair o numero do concurso, (c) ser registrado bruto para
   evolucao futura. Nunca para inventar dezenas.

2. As dezenas ESTAO impressas em texto no comprovante. E dai que elas saem, via OCR
   com pre-processamento de visao computacional (ver ticket_vision.py).

3. Se o OCR nao produzir um conjunto de dezenas que respeite as regras da modalidade,
   este modulo devolve falha explicita. Ele jamais completa, adivinha ou fabrica
   numeros para "fazer o resultado aparecer".

Este arquivo cuida da leitura de significado: qual modalidade, qual concurso e se a
aposta lida e valida. Quem mexe em pixel e o ticket_vision.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from lottery_rules import BET_SIZE_RULES, NUMBER_RANGE_RULES  # noqa: F401 (reexport)
from ticket_vision import TESS_TEXT, ticket_vision

logger = logging.getLogger("ticket-scanner")

GAME_KEYWORDS = {
    "lotomania": ("lotomania",),
    "lotofacil": ("lotofacil", "loto facil"),
    "megasena": ("megasena", "mega-sena", "mega sena"),
    "quina": ("quina",),
}


class TicketScanner:
    """Extrai concurso, modalidade e dezenas de uma foto de comprovante da Caixa."""

    def __init__(self, vision=ticket_vision):
        self.vision = vision

    def is_available(self) -> Tuple[bool, str]:
        return self.vision.is_available()

    def scan(self, image_bytes: bytes, hint_game: Optional[str] = None) -> Dict[str, Any]:
        available, reason = self.is_available()
        if not available:
            return self._failure(reason, stage="dependencias")

        image = self.vision.decode(image_bytes)
        if image is None:
            return self._failure("Nao foi possivel ler o arquivo de imagem enviado.", stage="decode")

        qr_payload = self.vision.read_qr(image)
        oriented, orientation = self.vision.auto_orient(image)
        text = self.vision.ocr(oriented, TESS_TEXT)

        detected = self._detect_game(text)
        game_id = detected or hint_game
        contest = self._detect_contest(text) or self._contest_from_qr(qr_payload)
        numbers = self.vision.extract_numbers(oriented, game_id)

        valid, validation_msg = self._validate(numbers, game_id)

        # A deducao so entra quando o logo NAO foi lido. Deixa-la sobrepor o logo
        # impresso produziu um erro grave em teste: as 50 dezenas de uma Lotomania,
        # filtradas pela faixa da Lotofacil (01-25), sobraram exatamente 15 e passaram
        # como aposta valida de outra modalidade. O que esta impresso manda.
        if not valid and not detected:
            deduced = self._deduce_game(oriented, skip=game_id)
            if deduced:
                game_id, numbers = deduced
                valid = True
                validation_msg = ("Dezenas lidas do comprovante. A modalidade foi deduzida "
                                  "pelo formato da aposta - confirme antes de conferir.")

        return {
            "success": valid,
            "message": validation_msg,
            "stage": "ocr",
            "game_id": game_id,
            "contest": contest,
            "numbers": numbers,
            "qr_payload": qr_payload,
            "needs_confirmation": True,
            "orientation": orientation,
            "raw_text": text[:1200],
        }

    # ------------------------------------------------------------------
    # Leitura de significado
    # ------------------------------------------------------------------
    def _detect_game(self, text: str) -> Optional[str]:
        """
        Identifica a modalidade pela PRIMEIRA que aparece no comprovante.

        Os tres comprovantes reais analisados (Lotomania 2971, Lotofacil 3777 e
        Quina 7107) trazem "MEGA-SENA ESTA EM 36 MILHOES" no cabecalho promocional,
        logo abaixo do logo da modalidade verdadeira. Contar ocorrencias daria empate
        de 1 a 1 nos tres; pegar a primeira acerta os tres, porque o logo e sempre a
        primeira linha impressa.
        """
        normalized = text.lower().replace(" ", "")

        positions = {}
        for game_id, keywords in GAME_KEYWORDS.items():
            hits = [normalized.find(kw.replace(" ", "")) for kw in keywords]
            hits = [h for h in hits if h >= 0]
            if hits:
                positions[game_id] = min(hits)

        if not positions:
            return None

        winner = min(positions, key=positions.get)
        logger.info("Modalidade detectada: %s (posicoes: %s)", winner, positions)
        return winner

    def _detect_contest(self, text: str) -> Optional[int]:
        """
        Aceita a forma abreviada impressa no comprovante ("CONC 7107") alem de
        "CONCURSO 7107". O \\b depois de conc(urso) evita casar com "CONCORRA".
        """
        match = re.search(r"\bconc(?:urso)?\b[^0-9]{0,8}(\d{3,5})\b", text, flags=re.IGNORECASE)
        return int(match.group(1)) if match else None

    def _contest_from_qr(self, payload: Optional[str]) -> Optional[int]:
        if not payload:
            return None
        match = re.search(r"concurso[=:/-]?(\d{3,5})", payload, flags=re.IGNORECASE)
        return int(match.group(1)) if match else None

    def _deduce_game(self, image, skip: Optional[str]) -> Optional[Tuple[str, List[str]]]:
        """
        Ultima rede: identifica a modalidade pelo proprio formato da aposta.

        Se o logo nao for lido (papel amassado, foto torta), as regras ainda denunciam
        o jogo: 50 dezenas de 00 a 99 so existe na Lotomania; 15 a 20 dezenas de 01 a 25
        so na Lotofacil. So aceita quando UMA unica modalidade fecha - ambiguidade volta
        para o usuario decidir, nunca para o chute.
        """
        matches = []
        for candidate in BET_SIZE_RULES:
            if candidate == skip:
                continue
            numbers = self.vision.extract_numbers(image, candidate)
            if self._validate(numbers, candidate)[0]:
                matches.append((candidate, numbers))

        if len(matches) != 1:
            if matches:
                logger.info("Deducao ambigua entre %s", [m[0] for m in matches])
            return None

        logger.info("Modalidade deduzida pelo formato da aposta: %s", matches[0][0])
        return matches[0]

    # ------------------------------------------------------------------
    # Validacao
    # ------------------------------------------------------------------
    def _validate(self, numbers: List[str], game_id: Optional[str]) -> Tuple[bool, str]:
        if not game_id:
            return False, ("Nao consegui identificar a modalidade no comprovante. "
                           "Selecione o jogo e confirme as dezenas manualmente.")

        if game_id not in BET_SIZE_RULES:
            return False, f"Modalidade nao suportada: {game_id}."

        minimum, maximum = BET_SIZE_RULES[game_id]
        if len(numbers) < minimum:
            return False, (f"Li apenas {len(numbers)} dezenas legiveis e a aposta da "
                           f"{game_id} tem no minimo {minimum}. Melhore a foto ou "
                           f"corrija as dezenas na tela - nao vou conferir bilhete incompleto.")

        if len(numbers) > maximum:
            return False, (f"Li {len(numbers)} dezenas, acima do maximo de {maximum} para "
                           f"{game_id}. O OCR capturou ruido do papel. Confirme manualmente.")

        return True, "Dezenas lidas do comprovante. Confirme antes de conferir."

    def _failure(self, message: str, stage: str) -> Dict[str, Any]:
        return {
            "success": False,
            "message": message,
            "stage": stage,
            "game_id": None,
            "contest": None,
            "numbers": [],
            "qr_payload": None,
            "needs_confirmation": True,
            "orientation": None,
            "raw_text": "",
        }


ticket_scanner = TicketScanner()
