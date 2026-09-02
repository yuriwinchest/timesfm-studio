"""
Leitura optica de bilhetes fisicos das Loterias Caixa.

Estrategia real (nao existe atalho magico aqui):

1. O QR Code impresso no comprovante da Caixa NAO carrega as dezenas apostadas em
   texto legivel. Ele carrega um payload opaco que so o app oficial resolve contra
   os servidores da Caixa. Portanto o QR serve para: (a) identificar o comprovante,
   (b) eventualmente extrair o numero do concurso, (c) ser registrado bruto para
   evolucao futura. Nunca para inventar dezenas.

2. As dezenas ESTAO impressas em texto no comprovante. E dai que elas saem, via OCR
   com pre-processamento de visao computacional.

3. Se o OCR nao produzir um conjunto de dezenas que respeite as regras da modalidade,
   este modulo devolve falha explicita. Ele jamais completa, adivinha ou fabrica
   numeros para "fazer o resultado aparecer".
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("ticket-scanner")

# Dependencias de visao sao opcionais: a API continua de pe mesmo sem elas,
# apenas reportando indisponibilidade honesta do modulo optico.
try:
    import cv2
    import numpy as np
    CV_AVAILABLE = True
except ImportError:  # pragma: no cover - depende do ambiente de deploy
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


# Regras de aposta por modalidade: (minimo de dezenas, maximo de dezenas)
BET_SIZE_RULES = {
    "megasena": (6, 20),
    "quina": (5, 15),
    "lotofacil": (15, 20),
    "lotomania": (50, 50),
}

NUMBER_RANGE_RULES = {
    "megasena": (1, 60),
    "quina": (1, 80),
    "lotofacil": (1, 25),
    "lotomania": (0, 99),
}

GAME_KEYWORDS = {
    "lotomania": ("lotomania",),
    "lotofacil": ("lotofacil", "lotofacil", "loto facil"),
    "megasena": ("megasena", "mega-sena", "mega sena"),
    "quina": ("quina",),
}

# Termos usados para pontuar a orientacao correta da foto do comprovante.
ORIENTATION_ANCHORS = (
    "loteria", "caixa", "concurso", "aposta", "lotomania", "quina",
    "lotofacil", "mega", "valor", "sena", "federal",
)

TESS_DIGITS = "--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789"
TESS_TEXT = "--oem 3 --psm 6"


class TicketScanner:
    """Extrai concurso, modalidade e dezenas de uma foto de comprovante da Caixa."""

    def is_available(self) -> Tuple[bool, str]:
        if not CV_AVAILABLE:
            return False, "OpenCV nao instalado no container (opencv-python-headless)."
        if not OCR_AVAILABLE:
            return False, "pytesseract nao instalado no container."
        try:
            pytesseract.get_tesseract_version()
        except Exception as e:
            return False, f"Binario do Tesseract indisponivel no sistema: {e}"
        return True, "ok"

    # ------------------------------------------------------------------
    # Pipeline publico
    # ------------------------------------------------------------------
    def scan(self, image_bytes: bytes, hint_game: Optional[str] = None) -> Dict[str, Any]:
        available, reason = self.is_available()
        if not available:
            return self._failure(reason, stage="dependencias")

        image = self._decode(image_bytes)
        if image is None:
            return self._failure("Nao foi possivel ler o arquivo de imagem enviado.", stage="decode")

        qr_payload = self.read_qr(image)
        oriented, orientation = self._auto_orient(image)
        text = self._ocr(oriented, TESS_TEXT)

        game_id = self._detect_game(text) or hint_game
        contest = self._detect_contest(text) or self._contest_from_qr(qr_payload)
        numbers = self._extract_numbers(oriented, game_id)

        valid, validation_msg = self._validate(numbers, game_id)

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

    def read_qr(self, image) -> Optional[str]:
        """Tenta decodificar o QR do comprovante com zbar e, em seguida, com OpenCV."""
        if not CV_AVAILABLE:
            return None

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        candidates = [
            gray,
            cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC),
            cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1],
        ]

        if ZBAR_AVAILABLE:
            for cand in candidates:
                try:
                    for code in pyzbar.decode(cand):
                        payload = code.data.decode("utf-8", errors="replace").strip()
                        if payload:
                            logger.info("QR do comprovante decodificado (zbar): %s", payload)
                            return payload
                except Exception as e:
                    logger.debug("Falha zbar: %s", e)

        try:
            detector = cv2.QRCodeDetector()
            for cand in candidates:
                payload, _, _ = detector.detectAndDecode(cand)
                if payload:
                    logger.info("QR do comprovante decodificado (OpenCV): %s", payload)
                    return payload.strip()
        except Exception as e:
            logger.debug("Falha OpenCV QR: %s", e)

        return None

    # ------------------------------------------------------------------
    # Etapas internas
    # ------------------------------------------------------------------
    def _decode(self, image_bytes: bytes):
        try:
            buf = np.frombuffer(image_bytes, dtype=np.uint8)
            return cv2.imdecode(buf, cv2.IMREAD_COLOR)
        except Exception as e:
            logger.warning("Erro ao decodificar imagem: %s", e)
            return None

    def _auto_orient(self, image):
        """
        Fotos de comprovante chegam de cabeca para baixo, giradas ou espelhadas
        (preview de webcam). Testamos as 8 orientacoes em baixa resolucao e
        escolhemos a que produz texto reconhecivel.
        """
        variants = {
            "0": image,
            "180": cv2.rotate(image, cv2.ROTATE_180),
            "90": cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE),
            "270": cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE),
        }
        variants.update({f"{k}-espelhado": cv2.flip(v, 1) for k, v in list(variants.items())})

        best_key, best_score, best_img = "0", -1, image
        for key, candidate in variants.items():
            score = self._orientation_score(candidate)
            if score > best_score:
                best_key, best_score, best_img = key, score, candidate

        logger.info("Orientacao escolhida para o comprovante: %s (score=%s)", best_key, best_score)
        return best_img, best_key

    def _orientation_score(self, image) -> int:
        probe = self._prepare(image, max_width=900)
        try:
            text = pytesseract.image_to_string(probe, config=TESS_TEXT).lower()
        except Exception:
            return 0
        return sum(text.count(anchor) for anchor in ORIENTATION_ANCHORS)

    def _prepare(self, image, max_width: int = 2000):
        """Realce de papel termico: cinza, upscale, CLAHE e binarizacao adaptativa."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        width = gray.shape[1]
        if width != max_width and width > 0:
            factor = max_width / float(width)
            interp = cv2.INTER_CUBIC if factor > 1 else cv2.INTER_AREA
            gray = cv2.resize(gray, None, fx=factor, fy=factor, interpolation=interp)

        gray = cv2.bilateralFilter(gray, 7, 60, 60)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        gray = clahe.apply(gray)

        return cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 12
        )

    def _ocr(self, image, config: str) -> str:
        try:
            prepared = self._prepare(image)
            return pytesseract.image_to_string(prepared, config=config)
        except Exception as e:
            logger.warning("Erro no OCR: %s", e)
            return ""

    def _detect_game(self, text: str) -> Optional[str]:
        """
        Escolhe a modalidade por contagem de ocorrencias, nao pela primeira que aparece.

        O comprovante traz texto promocional de outras loterias ("concorra tambem na
        Mega-Sena", "Mega da Virada"). Devolver a primeira palavra encontrada faria um
        bilhete de Quina ser conferido como Mega-Sena. A modalidade real e a que se
        repete (logo, cabecalho e rodape), nao a citada de passagem.
        """
        normalized = text.lower().replace(" ", "")

        scores = {}
        for game_id, keywords in GAME_KEYWORDS.items():
            total = sum(normalized.count(kw.replace(" ", "")) for kw in keywords)
            if total:
                scores[game_id] = total

        if not scores:
            return None

        best = max(scores.values())
        winners = [g for g, c in scores.items() if c == best]

        # Empate real: nao ha como decidir com honestidade, deixa o usuario escolher.
        if len(winners) > 1:
            logger.info("Modalidade ambigua no comprovante: %s", scores)
            return None

        return winners[0]

    def _detect_contest(self, text: str) -> Optional[int]:
        match = re.search(r"concurso\D{0,12}(\d{3,5})", text, flags=re.IGNORECASE)
        return int(match.group(1)) if match else None

    def _contest_from_qr(self, payload: Optional[str]) -> Optional[int]:
        if not payload:
            return None
        match = re.search(r"concurso[=:/-]?(\d{3,5})", payload, flags=re.IGNORECASE)
        return int(match.group(1)) if match else None

    def _extract_numbers(self, image, game_id: Optional[str]) -> List[str]:
        """
        Extrai as dezenas apostadas.

        O comprovante tem muito numero que NAO e dezena: data, hora, valor, CPF,
        codigo da aposta, numero do concurso. Ler o texto corrido inteiro traz esse
        lixo junto. Por isso a leitura primaria usa as coordenadas de cada token e
        reconstroi a GRADE impressa: so linhas com varios numeros de 2 digitos
        alinhados sao aceitas como dezenas.
        """
        prepared = self._prepare(image)
        grid = self._numbers_from_grid(prepared, game_id)
        flat = self._numbers_from_text(prepared, game_id)

        if game_id in BET_SIZE_RULES:
            minimum, maximum = BET_SIZE_RULES[game_id]
            if minimum <= len(grid) <= maximum:
                return grid
            if minimum <= len(flat) <= maximum:
                return flat

        return grid if grid else flat

    def _numbers_from_grid(self, prepared, game_id: Optional[str], min_per_row: int = 3) -> List[str]:
        """Reconstroi a grade de dezenas agrupando tokens por linha (coordenada Y)."""
        low, high = NUMBER_RANGE_RULES.get(game_id or "megasena", (0, 99))

        try:
            data = pytesseract.image_to_data(
                prepared, config=TESS_DIGITS, output_type=pytesseract.Output.DICT
            )
        except Exception as e:
            logger.warning("Erro no OCR posicional: %s", e)
            return []

        tokens = []
        for i, raw_text in enumerate(data.get("text", [])):
            token = (raw_text or "").strip()
            if not re.fullmatch(r"\d{2}", token):
                continue
            try:
                confidence = float(data["conf"][i])
            except (TypeError, ValueError):
                confidence = -1.0
            if confidence < 35:
                continue
            value = int(token)
            if value < low or value > high:
                continue
            tokens.append({
                "text": token,
                "x": int(data["left"][i]),
                "y": int(data["top"][i]),
                "h": max(1, int(data["height"][i])),
            })

        if not tokens:
            return []

        heights = sorted(t["h"] for t in tokens)
        tolerance = max(6, int(heights[len(heights) // 2] * 0.7))

        rows: List[List[Dict[str, Any]]] = []
        for token in sorted(tokens, key=lambda t: t["y"]):
            if rows and abs(token["y"] - rows[-1][0]["y"]) <= tolerance:
                rows[-1].append(token)
            else:
                rows.append([token])

        numbers: List[str] = []
        seen = set()
        for row in rows:
            if len(row) < min_per_row:
                continue
            for token in sorted(row, key=lambda t: t["x"]):
                if token["text"] in seen:
                    continue
                seen.add(token["text"])
                numbers.append(token["text"])

        return numbers

    def _numbers_from_text(self, prepared, game_id: Optional[str]) -> List[str]:
        """Leitura de contingencia sobre o texto corrido, sem coordenadas."""
        low, high = NUMBER_RANGE_RULES.get(game_id or "megasena", (0, 99))

        try:
            raw = pytesseract.image_to_string(prepared, config=TESS_DIGITS)
        except Exception as e:
            logger.warning("Erro no OCR de digitos: %s", e)
            return []

        numbers: List[str] = []
        seen = set()

        for token in re.findall(r"\d+", raw):
            # Papel termico costuma colar dezenas vizinhas: quebramos em pares.
            if len(token) > 2:
                limit = len(token) - (len(token) % 2)
                chunks = [token[i:i + 2] for i in range(0, limit, 2)]
            else:
                chunks = [token]

            for chunk in chunks:
                if len(chunk) != 2 or chunk in seen:
                    continue
                value = int(chunk)
                if value < low or value > high:
                    continue
                seen.add(chunk)
                numbers.append(chunk)

        return numbers

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
