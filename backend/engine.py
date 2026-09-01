import time
import os
import logging
import numpy as np
from typing import List, Dict, Any, Optional

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
            self.status_message = f"Modo Simulado/Estatístico ativo (TimesFM real não carregado: {str(e)})"
            logger.warning(f"TimesFM real não disponível localmente. Ativando motor de previsão estatístico de fallback. Erro: {e}")

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
                # O TimesFM espera uma lista de séries e freq
                forecast_result, _ = self.model.forecast([history_arr], freq=[freq])
                # Formato do forecast: (1, horizon, quantiles) ou (1, horizon)
                if len(forecast_result.shape) == 3:
                    point_forecast = forecast_result[0, :horizon, 0].tolist()
                    # Se tiver quantis (ex: 10% e 90%)
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
                engine_used = "Motor Estatístico Resiliente (Fallback)"
        else:
            # Fallback estatístico inteligente (Sazonalidade + Decomposição de Tendência + Ruído Gaussiano)
            point_forecast, lower_bound, upper_bound = self._statistical_fallback(history_arr, horizon)
            engine_used = "Motor Estatístico / Demonstração"

        elapsed_ms = round((time.time() - start_time) * 1000, 2)

        # Métricas estatísticas de resumo
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

    def _statistical_fallback(self, history: np.ndarray, horizon: int):
        """Gera uma projeção analítica sofisticada com sazonalidade e tendência."""
        n = len(history)
        t = np.arange(n)
        
        # Tendência linear básica
        p = np.polyfit(t, history, deg=1)
        slope, intercept = p[0], p[1]
        
        # Sazonalidade estimada (período 7 para dados diários ou período 12)
        period = 7 if n >= 14 else (4 if n >= 8 else 1)
        seasonal_pattern = np.zeros(period)
        detrended = history - (slope * t + intercept)
        for i in range(period):
            indices = np.arange(i, n, period)
            if len(indices) > 0:
                seasonal_pattern[i] = np.mean(detrended[indices])
        
        # Projeção futura
        future_t = np.arange(n, n + horizon)
        trend_proj = slope * future_t + intercept
        season_proj = np.array([seasonal_pattern[i % period] for i in range(horizon)])
        
        # Desvio padrão para os intervalos de confiança
        std = float(np.std(detrended[-30:] if n > 30 else detrended))
        if std == 0:
            std = float(np.mean(history)) * 0.05 or 1.0

        forecast = trend_proj + season_proj
        # Não permitir valores negativos se o histórico for todo positivo
        if np.all(history >= 0):
            forecast = np.maximum(0.0, forecast)

        lower = np.maximum(0.0 if np.all(history >= 0) else -np.inf, forecast - 1.645 * std)
        upper = forecast + 1.645 * std

        return forecast.tolist(), lower.tolist(), upper.tolist()

# Instância única global do motor
engine = TimesFMEngine()
