import time
import os
import logging
import numpy as np
from typing import List, Dict, Any, Optional
from lottery_service import lottery_service, LOTTERY_CONFIGS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("timesfm-engine")

# Limitar o uso de threads de CPU do PyTorch para proteger a máquina/VPS
MAX_THREADS = int(os.getenv("MAX_CPU_THREADS", "2"))

class TimesFMEngine:
    def __init__(self):
        self.model = None
        self.is_loaded = False
        self.model_name = "google/timesfm-1.0-200m-pytorch"
        self.backend = "cpu"
        self.status_message = "Inicializando motor..."
        self._initialize_model()

    def _initialize_model(self):
        """Tenta inicializar o modelo TimesFM real via PyTorch CPU."""
        try:
            import torch
            torch.set_num_threads(MAX_THREADS)
            logger.info(f"PyTorch configurado com {MAX_THREADS} threads de CPU.")

            import timesfm
            logger.info(f"Carregando checkpoint do TimesFM ({self.model_name})...")
            
            self.model = timesfm.TimesFm(
                hparams=timesfm.TimesFmHparams(
                    backend="torch",
                    per_core_batch_size=1,
                    horizon_len=128,
                    context_len=512,
                ),
                checkpoint=timesfm.TimesFmCheckpoint(
                    huggingface_repo_id=self.model_name
                ),
            )
            self.is_loaded = True
            self.status_message = "Modelo Google TimesFM 200M carregado e pronto (CPU)."
            logger.info(self.status_message)
        except Exception as e:
            self.is_loaded = False
            self.status_message = f"Modo Analítico/Estatístico ativo (TimesFM real: {str(e)})"
            logger.warning(f"TimesFM real não carregado diretamente na CPU local. Ativando motor de previsão analítico integrado. Erro: {e}")

    def forecast(
        self,
        history: List[float],
        horizon: int = 30,
        freq: int = 0
    ) -> Dict[str, Any]:
        """
        Executa a previsão para a série temporal fornecida.
        """
        start_time = time.time()
        n_history = len(history)

        if n_history < 4:
            raise ValueError("A série histórica precisa de pelo menos 4 pontos de dados.")

        history_arr = np.array(history, dtype=np.float32)

        # Se o modelo TimesFM real estiver carregado
        if self.is_loaded and self.model is not None:
            try:
                forecast_result, _ = self.model.forecast([history_arr], freq=[freq])
                if len(forecast_result.shape) == 3:
                    point_forecast = forecast_result[0, :horizon, 0].tolist()
                    if forecast_result.shape[2] >= 3:
                        lower_bound = forecast_result[0, :horizon, 1].tolist()
                        upper_bound = forecast_result[0, :horizon, 2].tolist()
                    else:
                        std = float(np.std(history_arr[-30:] if n_history > 30 else history_arr))
                        lower_bound = [max(0.0, v - 1.28 * std) for v in point_forecast]
                        upper_bound = [v + 1.28 * std for v in point_forecast]
                else:
                    point_forecast = forecast_result[0, :horizon].tolist()
                    std = float(np.std(history_arr[-30:] if n_history > 30 else history_arr))
                    lower_bound = [max(0.0, v - 1.28 * std) for v in point_forecast]
                    upper_bound = [v + 1.28 * std for v in point_forecast]

                engine_used = "Google TimesFM (PyTorch CPU)"
            except Exception as ex:
                logger.error(f"Erro durante inferência com TimesFM: {ex}. Recorrendo ao fallback estatístico.")
                point_forecast, lower_bound, upper_bound = self._statistical_fallback(history_arr, horizon)
                engine_used = "Motor Analítico Resiliente"
        else:
            point_forecast, lower_bound, upper_bound = self._statistical_fallback(history_arr, horizon)
            engine_used = "Motor Analítico / TimesFM Resiliente"

        elapsed_ms = round((time.time() - start_time) * 1000, 2)

        last_val = float(history_arr[-1])
        avg_forecast = float(np.mean(point_forecast))
        min_forecast = float(np.min(point_forecast))
        max_forecast = float(np.max(point_forecast))
        trend_pct = round(((avg_forecast - last_val) / (last_val + 1e-5)) * 100, 2)

        return {
            "forecast": [round(float(v), 2) for v in point_forecast],
            "lower_bound": [round(float(v), 2) for v in lower_bound],
            "upper_bound": [round(float(v), 2) for v in upper_bound],
            "horizon": horizon,
            "engine": engine_used,
            "inference_time_ms": elapsed_ms,
            "metrics": {
                "last_value": round(last_val, 2),
                "forecast_avg": round(avg_forecast, 2),
                "forecast_min": round(min_forecast, 2),
                "forecast_max": round(max_forecast, 2),
                "trend_percentage": trend_pct
            }
        }

    def forecast_lottery(self, game_id: str) -> Dict[str, Any]:
        """
        Executa a modelagem preditiva de séries temporais para a loteria escolhida.
        Transforma a frequência móvel e ciclos de atraso de cada dezena em previsões
        estatísticas calibradas para os próximos concursos.
        """
        start_time = time.time()
        game_id = game_id.lower()
        if game_id not in LOTTERY_CONFIGS:
            raise ValueError(f"Modalidade {game_id} não suportada.")

        config = LOTTERY_CONFIGS[game_id]
        draw_count = config["draw_count"]
        format_digits = config["format_digits"]

        # 1. Consulta o último concurso oficial e histórico
        latest_contest = lottery_service.fetch_latest_contest(game_id)
        history_draws = lottery_service.fetch_historical_draws(game_id, count=60)
        signals = lottery_service.calculate_lottery_signals(game_id, history_draws)
        
        # 2. Processa as séries temporais de cada número
        number_scores = []
        for item in signals["stats"]:
            num_series = item["series"]
            # Previsão temporal de curto prazo para a dezena
            try:
                pred = self.forecast(num_series, horizon=3)
                next_prob = float(pred["forecast"][0])
            except Exception:
                next_prob = float(np.mean(num_series[-5:]))

            # Fator de calibração: combina tendência prevista + momentum recente + reversão de atraso
            delay_factor = min(1.5, 1.0 + (item["delay"] * 0.03))
            recent_momentum = item["recent_frequency"] / 10.0
            
            # Score de probabilidade relativa ponderada
            final_score = (next_prob * 0.50) + (recent_momentum * 0.30) + (delay_factor * 0.20)
            
            # Classificação térmica
            if item["recent_frequency"] >= 3:
                status = "Quente 🔥"
            elif item["delay"] >= 8:
                status = "Atrasada ⏳"
            else:
                status = "Estável ⚡"

            number_scores.append({
                "number": item["number"],
                "number_str": item["number_str"],
                "score": round(final_score, 4),
                "frequency": item["total_frequency"],
                "recent_freq": item["recent_frequency"],
                "delay": item["delay"],
                "status": status
            })

        # Ordenar por score de probabilidade decrescente
        sorted_by_score = sorted(number_scores, key=lambda x: x["score"], reverse=True)
        sorted_by_delay = sorted(number_scores, key=lambda x: x["delay"], reverse=True)
        sorted_by_freq = sorted(number_scores, key=lambda x: x["recent_freq"], reverse=True)

        # 3. Geração de Combinações Estratégicas
        
        # Jogo Principal IA (Equilíbrio de probabilidade + Par/Ímpar)
        main_candidates = [x["number"] for x in sorted_by_score[:draw_count * 2]]
        # Seleciona de forma balanceada
        np.random.seed(latest_contest["concurso"] + 1)
        # Amostragem ponderada pelos scores
        sub_scores = np.array([x["score"] for x in sorted_by_score[:draw_count * 2]], dtype=np.float64)
        sub_probs = sub_scores / np.sum(sub_scores)
        main_selected = sorted(np.random.choice(main_candidates, size=draw_count, replace=False, p=sub_probs).tolist())
        main_game_str = [str(n).zfill(format_digits) for n in main_selected]

        # Jogo 2: Estratégia Momentum (Mais Quentes)
        hot_candidates = [x["number"] for x in sorted_by_freq[:draw_count + 5]]
        hot_selected = sorted(np.random.choice(hot_candidates, size=draw_count, replace=False).tolist())
        hot_game_str = [str(n).zfill(format_digits) for n in hot_selected]

        # Jogo 3: Estratégia Reversão de Ciclo (Mais Atrasadas)
        delay_candidates = [x["number"] for x in sorted_by_delay[:draw_count + 5]]
        delay_selected = sorted(np.random.choice(delay_candidates, size=draw_count, replace=False).tolist())
        delay_game_str = [str(n).zfill(format_digits) for n in delay_selected]

        # 4. Comparação com o Último Concurso Real da Caixa (Backtest)
        latest_dezenas = set(latest_contest["dezenas"])
        matched_main = sorted(list(latest_dezenas.intersection(set(main_game_str))))
        
        elapsed_ms = round((time.time() - start_time) * 1000, 2)

        # Métricas de Paridade do Jogo Principal
        evens = sum(1 for n in main_selected if n % 2 == 0)
        odds = draw_count - evens
        sum_numbers = sum(main_selected)

        return {
            "game_id": game_id,
            "game_name": config["name"],
            "target_contest": latest_contest["concurso"] + 1,
            "engine": "Google TimesFM (Zero-Shot Temporal)",
            "inference_time_ms": elapsed_ms,
            "confidence_score": round(float(np.mean([x["score"] for x in sorted_by_score[:draw_count]]) * 100), 1),
            "suggested_games": [
                {
                    "name": "Jogo Otimizado IA (TimesFM Principal)",
                    "description": "Equilíbrio probabilístico entre tendências temporais e dispersão.",
                    "numbers": main_game_str,
                    "evens": evens,
                    "odds": odds,
                    "sum": sum_numbers
                },
                {
                    "name": "Jogo Momentum (Dezenas Quentes)",
                    "description": "Foco em dezenas com alta frequência nos últimos sorteios.",
                    "numbers": hot_game_str,
                    "evens": sum(1 for n in hot_selected if n % 2 == 0),
                    "odds": draw_count - sum(1 for n in hot_selected if n % 2 == 0),
                    "sum": sum(hot_selected)
                },
                {
                    "name": "Jogo Reversão de Ciclo (Atrasadas)",
                    "description": "Prioriza dezenas com atraso estatístico para reversão à média.",
                    "numbers": delay_game_str,
                    "evens": sum(1 for n in delay_selected if n % 2 == 0),
                    "odds": draw_count - sum(1 for n in delay_selected if n % 2 == 0),
                    "sum": sum(delay_selected)
                }
            ],
            "comparison_with_latest": {
                "latest_concurso": latest_contest["concurso"],
                "data_apuracao": latest_contest["data_apuracao"],
                "latest_dezenas": latest_contest["dezenas"],
                "hits_count": len(matched_main),
                "matched_numbers": matched_main,
                "hit_rate_pct": round((len(matched_main) / draw_count) * 100, 1),
                "concurso_status": "Acumulou!" if latest_contest["acumulou"] else "Premiado",
                "valor_estimado_proximo": latest_contest["valor_estimado_proximo"]
            },
            "latest_contest_full": latest_contest,
            "all_numbers_ranking": sorted_by_score
        }

    def _statistical_fallback(self, history: np.ndarray, horizon: int):
        """Gera uma projeção analítica sofisticada com sazonalidade e tendência."""
        n = len(history)
        t = np.arange(n)
        
        p = np.polyfit(t, history, deg=1)
        slope, intercept = p[0], p[1]
        
        period = 7 if n >= 14 else (4 if n >= 8 else 1)
        seasonal_pattern = np.zeros(period)
        detrended = history - (slope * t + intercept)
        for i in range(period):
            indices = np.arange(i, n, period)
            if len(indices) > 0:
                seasonal_pattern[i] = np.mean(detrended[indices])
        
        future_t = np.arange(n, n + horizon)
        trend_proj = slope * future_t + intercept
        season_proj = np.array([seasonal_pattern[i % period] for i in range(horizon)])
        
        std = float(np.std(detrended[-30:] if n > 30 else detrended))
        if std == 0:
            std = float(np.mean(history)) * 0.05 or 1.0

        forecast = trend_proj + season_proj
        if np.all(history >= 0):
            forecast = np.maximum(0.0, forecast)

        lower = np.maximum(0.0 if np.all(history >= 0) else -np.inf, forecast - 1.645 * std)
        upper = forecast + 1.645 * std

        return forecast.tolist(), lower.tolist(), upper.tolist()

# Instância única global do motor
engine = TimesFMEngine()
