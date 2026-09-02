"""
Camada de visao computacional da leitura de comprovantes.

Responsabilidade unica: transformar pixels em numeros de 2 digitos posicionados.
Nao conhece modalidade, nao valida aposta e nao conversa com a API da Caixa - quem
decide o que aquilo significa e o ticket_scanner.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from lottery_rules import BET_SIZE_RULES, NUMBER_RANGE_RULES

logger = logging.getLogger("ticket-vision")

try:
    import cv2
    import numpy as np
    CV_AVAILABLE = True
except ImportError:  # pragma: no cover
    CV_AVAILABLE = False

try:
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:  # pragma: no cover
    OCR_AVAILABLE = False

try:
    from pyzbar import pyzbar
    ZBAR_AVAILABLE = True
except ImportError:  # pragma: no cover
    ZBAR_AVAILABLE = False

# Termos usados para pontuar a orientacao correta da foto do comprovante.
ORIENTATION_ANCHORS = (
    "loteria", "caixa", "concurso", "aposta", "lotomania", "quina",
    "lotofacil", "mega", "valor", "sena", "federal", "bilhete", "terminal",
)

# psm 4 = coluna unica com tamanhos de fonte variados, que e exatamente um comprovante.
TESS_TEXT = "--oem 3 --psm 4"
TESS_FALLBACKS = ("--oem 3 --psm 6",)


class TicketVision:
    """Decodifica, orienta, realca e extrai dezenas posicionadas do comprovante."""

    def is_available(self):
        """Diz se a stack optica esta de pe neste container."""
        if not CV_AVAILABLE:
            return False, "OpenCV nao instalado no container."
        if not OCR_AVAILABLE:
            return False, "pytesseract nao instalado no container."
        try:
            pytesseract.get_tesseract_version()
        except Exception as e:
            return False, f"Binario do Tesseract indisponivel: {e}"
        return True, "ok"

    def read_qr(self, image) -> Optional[str]:
        """Tenta decodificar o QR do comprovante com zbar e OpenCV."""
        if not CV_AVAILABLE or image is None:
            return None

        # Redimensiona para busca rapida de QR
        h, w = image.shape[:2]
        target_w = 800
        if w > target_w:
            scale = target_w / float(w)
            small = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        else:
            small = image

        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

        if ZBAR_AVAILABLE:
            try:
                for code in pyzbar.decode(gray):
                    payload = code.data.decode("utf-8", errors="replace").strip()
                    if payload:
                        logger.info("QR decodificado (zbar): %s", payload)
                        return payload
            except Exception as e:
                logger.debug("Falha zbar: %s", e)

        try:
            detector = cv2.QRCodeDetector()
            payload, _, _ = detector.detectAndDecode(gray)
            if payload:
                logger.info("QR decodificado (OpenCV): %s", payload)
                return payload.strip()
        except Exception as e:
            logger.debug("Falha OpenCV QR: %s", e)

        return None

    def decode(self, image_bytes: bytes):
        try:
            buf = np.frombuffer(image_bytes, dtype=np.uint8)
            img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
            if img is not None:
                # Normaliza tamanho máximo para evitar exaustão de CPU
                h, w = img.shape[:2]
                max_dim = 1600
                if max(h, w) > max_dim:
                    scale = max_dim / float(max(h, w))
                    img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            return img
        except Exception as e:
            logger.warning("Erro ao decodificar imagem: %s", e)
            return None

    def auto_orient(self, image):
        """
        Orienta a foto do comprovante com teste rapido de curto-circuito.
        Se a imagem já estiver em pe (0 graus), retorna instantaneamente.
        """
        # 1. Teste rapido na orientacao atual (0)
        score_0 = self._orientation_score(image)
        if score_0 >= 1:
            logger.info("Comprovante ja esta na orientacao correta (0 graus, score=%s)", score_0)
            return image, "0"

        # 2. Se nao encontrou palavras na orientacao 0, testa as outras
        variants = {
            "180": cv2.rotate(image, cv2.ROTATE_180),
            "90": cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE),
            "270": cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE),
            "0-espelhado": cv2.flip(image, 1),
        }

        best_key, best_score, best_img = "0", score_0, image
        for key, candidate in variants.items():
            score = self._orientation_score(candidate)
            if score > best_score:
                best_key, best_score, best_img = key, score, candidate
                if best_score >= 2:
                    break

        logger.info("Orientacao escolhida: %s (score=%s)", best_key, best_score)
        return best_img, best_key

    def _orientation_score(self, image) -> int:
        probe = self._prepare(image, max_width=600)
        try:
            text = pytesseract.image_to_string(probe, config=TESS_TEXT).lower()
        except Exception:
            return 0
        return sum(text.count(anchor) for anchor in ORIENTATION_ANCHORS)

    def _grayscale(self, image, max_width: int = 1100):
        """Normaliza escala e contraste antes de qualquer binarizacao."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        width = gray.shape[1]
        if width != max_width and width > 0:
            factor = max_width / float(width)
            interp = cv2.INTER_AREA if factor < 1 else cv2.INTER_CUBIC
            gray = cv2.resize(gray, None, fx=factor, fy=factor, interpolation=interp)

        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        return clahe.apply(gray)

    def _prepare_variants(self, image, max_width: int = 1100) -> List[Any]:
        gray = self._grayscale(image, max_width)
        otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        block = max(31, int(gray.shape[1] * 0.035) | 1)
        adaptive = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block, 10
        )
        return [otsu, adaptive]

    def _prepare(self, image, max_width: int = 1100):
        return self._prepare_variants(image, max_width)[0]

    def ocr(self, image, config: str = TESS_TEXT) -> str:
        try:
            prepared = self._prepare(image, max_width=1100)
            return pytesseract.image_to_string(prepared, config=config)
        except Exception as e:
            logger.warning("Erro no OCR: %s", e)
            return ""

    def extract_numbers_and_games(self, image, game_id: Optional[str]) -> Tuple[List[str], List[List[str]], str]:
        """
        Extrai em uma única passagem rápida tanto os números quanto os jogos do bilhete.
        """
        rules = BET_SIZE_RULES.get(game_id)
        baixo, alto = NUMBER_RANGE_RULES.get(game_id or "megasena", (0, 99))
        variantes = self._prepare_variants(image, max_width=1100)

        best_numbers: List[str] = []
        best_games: List[List[str]] = []
        best_raw_text: str = ""

        for prepared in variantes:
            try:
                texto = pytesseract.image_to_string(prepared, config=TESS_TEXT)
            except Exception as e:
                logger.warning("Erro no OCR de dezenas: %s", e)
                continue

            if len(texto) > len(best_raw_text):
                best_raw_text = texto

            # Extração dos jogos por linhas
            games = []
            for bruta in texto.splitlines():
                tokens = self._bet_line_tokens(bruta, baixo, alto)
                if tokens:
                    deduped = self._dedupe(tokens)
                    if rules and rules[0] <= len(deduped) <= rules[1]:
                        games.append(deduped)

            numbers = self._numbers_from_lines(texto, game_id)
            if rules and rules[0] <= len(numbers) <= rules[1]:
                return numbers, games or [numbers], texto

            if len(numbers) > len(best_numbers):
                best_numbers = numbers
                best_games = games

        if not best_games and best_numbers:
            best_games = [best_numbers]

        return best_numbers, best_games, best_raw_text

    def extract_numbers(self, image, game_id: Optional[str]) -> List[str]:
        numbers, _, _ = self.extract_numbers_and_games(image, game_id)
        return numbers

    def extract_games(self, image, game_id: Optional[str]) -> List[List[str]]:
        _, games, _ = self.extract_numbers_and_games(image, game_id)
        return games

    def _numbers_from_lines(self, texto: str, game_id: Optional[str]) -> List[str]:
        baixo, alto = NUMBER_RANGE_RULES.get(game_id or "megasena", (0, 99))
        linhas_de_aposta = []
        for bruta in texto.splitlines():
            tokens = self._bet_line_tokens(bruta, baixo, alto)
            if tokens:
                linhas_de_aposta.append(tokens)

        if not linhas_de_aposta:
            return []

        rules = BET_SIZE_RULES.get(game_id)
        todas = sum(linhas_de_aposta, [])
        dezenas = self._dedupe(todas)
        if rules and rules[0] <= len(dezenas) <= rules[1]:
            return dezenas

        # Se houver múltiplas linhas, verifica se alguma linha individual fecha a regra
        for linha in linhas_de_aposta:
            d = self._dedupe(linha)
            if rules and rules[0] <= len(d) <= rules[1]:
                return d

        return dezenas

    def _bet_line_tokens(self, linha: str, baixo: int, alto: int) -> List[str]:
        limpa = linha.replace("[", " ").replace("]", " ").replace("|", " ").strip()
        if not limpa:
            return []

        tokens = limpa.split()
        if not tokens:
            return []

        # Remove marcador de aposta (ex: "A", "B", "C")
        if len(tokens[0]) == 1 and tokens[0].isalpha():
            tokens = tokens[1:]

        dezenas = []
        for t in tokens:
            digits = re.sub(r"\D", "", t)
            if len(digits) == 1:
                digits = digits.zfill(2)
            if len(digits) == 2 and digits.isdigit():
                val = int(digits)
                if baixo <= val <= alto:
                    dezenas.append(digits)
            else:
                return []

        return dezenas

    def _dedupe(self, tokens: List[str]) -> List[str]:
        seen = set()
        out = []
        for t in tokens:
            if t not in seen:
                seen.add(t)
                out.append(t)
        return sorted(out, key=int)


ticket_vision = TicketVision()
