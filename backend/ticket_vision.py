"""
Camada de visao computacional da leitura de comprovantes.

Responsabilidade unica: transformar pixels em numeros de 2 digitos posicionados.
Nao conhece modalidade, nao valida aposta e nao conversa com a API da Caixa - quem
decide o que aquilo significa e o ticket_scanner.
"""

import logging
from typing import Any, Dict, List, Optional

from lottery_rules import BET_SIZE_RULES, NUMBER_RANGE_RULES

logger = logging.getLogger("ticket-vision")

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

# Termos usados para pontuar a orientacao correta da foto do comprovante.
ORIENTATION_ANCHORS = (
    "loteria", "caixa", "concurso", "aposta", "lotomania", "quina",
    "lotofacil", "mega", "valor", "sena", "federal",
)

TESS_DIGITS = "--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789"
TESS_TEXT = "--oem 3 --psm 6"


class TicketVision:
    """Decodifica, orienta, realca e extrai dezenas posicionadas do comprovante."""

    def is_available(self):
        """Diz, sem eufemismo, se a stack optica esta de pe neste container."""
        if not CV_AVAILABLE:
            return False, "OpenCV nao instalado no container (opencv-python-headless)."
        if not OCR_AVAILABLE:
            return False, "pytesseract nao instalado no container."
        try:
            pytesseract.get_tesseract_version()
        except Exception as e:
            return False, f"Binario do Tesseract indisponivel no sistema: {e}"
        return True, "ok"

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
    def decode(self, image_bytes: bytes):
        try:
            buf = np.frombuffer(image_bytes, dtype=np.uint8)
            return cv2.imdecode(buf, cv2.IMREAD_COLOR)
        except Exception as e:
            logger.warning("Erro ao decodificar imagem: %s", e)
            return None
    def auto_orient(self, image):
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
    def _grayscale(self, image, max_width: int = 2000):
        """Normaliza escala e contraste antes de qualquer binarizacao."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        width = gray.shape[1]
        if width != max_width and width > 0:
            factor = max_width / float(width)
            interp = cv2.INTER_CUBIC if factor > 1 else cv2.INTER_AREA
            gray = cv2.resize(gray, None, fx=factor, fy=factor, interpolation=interp)

        gray = cv2.bilateralFilter(gray, 7, 60, 60)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        return clahe.apply(gray)

    def _prepare_variants(self, image, max_width: int = 2000) -> List[Any]:
        """
        Gera binarizacoes alternativas do mesmo comprovante.

        Motivo: a linha das dezenas e a maior e mais grossa do bilhete. Um
        adaptiveThreshold com bloco pequeno cabe inteiro dentro do traco dessa fonte,
        calcula media igual ao proprio traco e APAGA o numero - some justamente a
        unica linha que interessa. Otsu global preserva texto grosso; o adaptativo
        salva papel amassado com sombra. Testamos os dois e ficamos com o que produzir
        uma aposta valida.
        """
        gray = self._grayscale(image, max_width)

        otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

        # Bloco proporcional a largura, nunca menor que a altura de uma linha grossa
        block = max(41, int(gray.shape[1] * 0.04) | 1)
        adaptive = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block, 12
        )

        return [otsu, adaptive, gray]

    def _prepare(self, image, max_width: int = 2000):
        """Variante principal (Otsu), usada na leitura de texto e na orientacao."""
        return self._prepare_variants(image, max_width)[0]

    def ocr(self, image, config: str) -> str:
        try:
            prepared = self._prepare(image)
            return pytesseract.image_to_string(prepared, config=config)
        except Exception as e:
            logger.warning("Erro no OCR: %s", e)
            return ""
    def extract_numbers(self, image, game_id: Optional[str]) -> List[str]:
        """
        Extrai as dezenas apostadas.

        O comprovante tem muito numero que NAO e dezena: data, hora, valor, CPF,
        codigo da aposta, numero do concurso. Ler o texto corrido inteiro traz esse
        lixo junto. Por isso a leitura primaria usa as coordenadas de cada token e
        reconstroi a GRADE impressa: so linhas com varios numeros de 2 digitos
        alinhados sao aceitas como dezenas.
        """
        rules = BET_SIZE_RULES.get(game_id)
        best_effort: List[str] = []

        for prepared in self._prepare_variants(image):
            grid = self._numbers_from_grid(prepared, game_id)
            if rules and rules[0] <= len(grid) <= rules[1]:
                return grid

            flat = self._numbers_from_text(prepared, game_id)
            if rules and rules[0] <= len(flat) <= rules[1]:
                return flat

            if not best_effort:
                best_effort = grid or flat

        return best_effort

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
                "w": max(1, int(data["width"][i])),
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

        profiles = [self._row_profile(sorted(r, key=lambda t: t["x"])) for r in rows]

        anchors = [i for i, p in enumerate(profiles)
                   if len(p["tokens"]) >= min_per_row and self._is_bet_row(p, game_id)]
        if not anchors:
            return []

        block = self._bet_block(profiles, anchors)

        numbers: List[str] = []
        seen = set()
        for index in block:
            for token in profiles[index]["tokens"]:
                if token["text"] in seen:
                    continue
                seen.add(token["text"])
                numbers.append(token["text"])

        return numbers

    def _bet_block(self, profiles: List[Dict[str, Any]], anchors: List[int]) -> List[int]:
        """
        Monta o bloco da aposta e recupera a linha final curta.

        Na Lotomania a grade fecha com uma linha de apenas duas dezenas ("[97] [00]").
        Exigir tres numeros por linha descartaria justamente ela e reprovaria um bilhete
        valido por ler 48 de 50. Entao: as linhas cheias ancoram o bloco, e uma linha
        vizinha e absorvida quando tem a mesma altura de digito e comeca na mesma coluna.
        """
        block = set(anchors)
        reference = profiles[anchors[0]]

        for index, profile in enumerate(profiles):
            if index in block or not profile["tokens"]:
                continue
            if not any(abs(index - a) == 1 for a in block):
                continue

            same_size = 0.7 <= profile["height"] / max(1, reference["height"]) <= 1.4
            same_column = abs(profile["tokens"][0]["x"] - reference["tokens"][0]["x"]) <= reference["width"]
            if same_size and same_column:
                block.add(index)

        return sorted(block)

    def _row_profile(self, row: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Resume uma linha: altura tipica dos digitos e folga entre os numeros."""
        heights = sorted(t["h"] for t in row)
        widths = sorted(t["w"] for t in row)
        gaps = [row[i + 1]["x"] - (row[i]["x"] + row[i]["w"]) for i in range(len(row) - 1)]
        gaps.sort()
        return {
            "tokens": row,
            "height": heights[len(heights) // 2],
            "width": widths[len(widths) // 2],
            "gap": gaps[len(gaps) // 2] if gaps else 0,
        }

    def _is_bet_row(self, profile: Dict[str, Any], game_id: Optional[str]) -> bool:
        """
        Separa a linha da aposta das linhas de codigo do comprovante.

        O comprovante traz sequencias longas e continuas de digitos (codigo da aposta,
        CNPJ do loterico, terminal). Quando o OCR quebra uma dessas sequencias, ela vira
        uma fileira de numeros de 2 digitos colados - e sem este filtro seria conferida
        como se fossem as dezenas do jogador. Aposta impressa tem folga entre os numeros;
        codigo nao tem.
        """
        maximum = BET_SIZE_RULES.get(game_id, (0, 60))[1]
        if len(profile["tokens"]) > maximum:
            return False

        # Digitos colados: folga menor que um terco da largura do proprio numero
        return profile["gap"] >= profile["width"] * 0.33

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



ticket_vision = TicketVision()
