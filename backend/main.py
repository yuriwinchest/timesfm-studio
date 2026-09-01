import os
import io
import time
import pandas as pd
import numpy as np
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from engine import engine
from lottery_service import lottery_service, LOTTERY_CONFIGS

app = FastAPI(
    title="TimesFM Studio API",
    description="Interface e API para previsão de séries temporais com Google TimesFM e Loterias Caixa",
    version="1.1.0"
)

# Habilitar CORS para desenvolvimento local
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Modelos Pydantic para Séries Temporais Genéricas
class ForecastRequest(BaseModel):
    history: List[float] = Field(..., description="Lista de valores históricos numéricos")
    dates: Optional[List[str]] = Field(default=None, description="Lista opcional de datas correspondentes")
    horizon: int = Field(default=30, ge=1, le=365, description="Número de passos a prever")
    freq: int = Field(default=0, description="Frequência (0=alta frequência/diária, 1=semanal, 2=mensal)")

class ForecastResponse(BaseModel):
    success: bool
    forecast: List[float]
    lower_bound: List[float]
    upper_bound: List[float]
    future_dates: List[str]
    horizon: int
    engine: str
    inference_time_ms: float
    metrics: Dict[str, Any]

# Modelos Pydantic para Loterias
class LotteryPredictRequest(BaseModel):
    game_id: str = Field(default="megasena", description="Identificador da loteria: megasena, quina, lotofacil, lotomania")

@app.get("/api/health")
def health_check():
    """Retorna o status de integridade do servidor e do modelo."""
    return {
        "status": "online",
        "model_loaded": engine.is_loaded,
        "model_name": engine.model_name,
        "status_message": engine.status_message,
        "backend": engine.backend,
        "supported_lotteries": list(LOTTERY_CONFIGS.keys()),
        "timestamp": time.time()
    }

# ==========================================
# ROTAS DO MÓDULO DE LOTERIAS CAIXA
# ==========================================

@app.get("/api/lottery/games")
def get_lottery_games():
    """Retorna a lista de modalidades de loteria suportadas."""
    return {
        "games": lottery_service.get_supported_games()
    }

@app.get("/api/lottery/info/{game_id}")
def get_lottery_info(game_id: str):
    """Consulta o último concurso oficial em tempo real na API da Caixa."""
    try:
        data = lottery_service.fetch_latest_contest(game_id)
        return {
            "success": True,
            "data": data
        }
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar dados da Caixa: {str(e)}")

@app.get("/api/lottery/contest/{game_id}/{contest_number}")
def get_lottery_contest(game_id: str, contest_number: int):
    """Retorna os dados oficiais de um concurso específico pelo número (ex: 2962, 6707, 3051)."""
    try:
        data = lottery_service.fetch_contest_by_number(game_id, contest_number)
        return {
            "success": True,
            "data": data
        }
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar dados do concurso {contest_number}: {str(e)}")

@app.post("/api/lottery/predict")
def predict_lottery(payload: LotteryPredictRequest):
    """Executa a modelagem de séries temporais com TimesFM para prever o próximo concurso."""
    try:
        result = engine.forecast_lottery(payload.game_id)
        return {
            "success": True,
            "data": result
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro durante a predição da loteria: {str(e)}")

# ==========================================
# ROTAS DE SÉRIES TEMPORAIS GERAIS (PRESETS & UPLOAD)
# ==========================================

@app.get("/api/presets")
def get_presets():
    """Retorna séries temporais de demonstração ricas em padrões reais."""
    np.random.seed(42)
    days_90 = pd.date_range(end=pd.Timestamp.today(), periods=90, freq='D')
    base_deliveries = 120 + np.linspace(0, 80, 90)
    weekday_effect = np.array([25, 30, 28, 35, 45, 10, -30])[days_90.dayofweek]
    noise_deliv = np.random.normal(0, 8, 90)
    zynex_values = np.round(np.maximum(20, base_deliveries + weekday_effect + noise_deliv), 1).tolist()

    base_sales = 45 + np.sin(np.linspace(0, 12, 90)) * 15
    sales_values = np.round(np.maximum(10, base_sales + np.random.normal(0, 5, 90)), 2).tolist()

    hours_120 = pd.date_range(end=pd.Timestamp.today(), periods=120, freq='h')
    base_cpu = 35 + 20 * np.sin(np.linspace(0, 20, 120)) + np.random.normal(0, 4, 120)
    cpu_values = np.round(np.clip(base_cpu, 5, 98), 1).tolist()

    return {
        "presets": [
            {
                "id": "zynexlog_entregas",
                "title": "Logística ZYNEXLOG — Volume Diário de Encomendas",
                "description": "90 dias de histórico de entregas com sazonalidade nos finais de semana e crescimento de frota.",
                "unit": "encomendas",
                "dates": [d.strftime('%Y-%m-%d') for d in days_90],
                "values": zynex_values,
                "suggested_horizon": 14
            },
            {
                "id": "ecommerce_vendas",
                "title": "Varejo & E-commerce — Faturamento Diário (R$ mil)",
                "description": "Padrões de compra de clientes, picos promocionais e ciclos quinzenais.",
                "unit": "R$ mil",
                "dates": [d.strftime('%Y-%m-%d') for d in days_90],
                "values": sales_values,
                "suggested_horizon": 30
            },
            {
                "id": "servidor_carga",
                "title": "Infraestrutura Cloud — Carga de CPU e Tráfego (Horário)",
                "description": "120 horas de métricas de carga dos servidores e requisições HTTP.",
                "unit": "% CPU",
                "dates": [d.strftime('%Y-%m-%d %H:00') for d in hours_120],
                "values": cpu_values,
                "suggested_horizon": 24
            }
        ]
    }

@app.post("/api/forecast", response_model=ForecastResponse)
def run_forecast(payload: ForecastRequest):
    """Executa a previsão com o modelo TimesFM ou motor analítico."""
    try:
        result = engine.forecast(
            history=payload.history,
            horizon=payload.horizon,
            freq=payload.freq
        )

        future_dates = []
        if payload.dates and len(payload.dates) == len(payload.history):
            try:
                last_date = pd.to_datetime(payload.dates[-1])
                future_dt_range = pd.date_range(
                    start=last_date + pd.Timedelta(days=1),
                    periods=payload.horizon,
                    freq='D'
                )
                future_dates = [d.strftime('%Y-%m-%d') for d in future_dt_range]
            except Exception:
                future_dates = [f"+{i+1}" for i in range(payload.horizon)]
        else:
            future_dates = [f"T+{i+1}" for i in range(payload.horizon)]

        return ForecastResponse(
            success=True,
            forecast=result["forecast"],
            lower_bound=result["lower_bound"],
            upper_bound=result["upper_bound"],
            future_dates=future_dates,
            horizon=result["horizon"],
            engine=result["engine"],
            inference_time_ms=result["inference_time_ms"],
            metrics=result["metrics"]
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/upload-csv")
async def upload_csv(file: UploadFile = File(...)):
    """Recebe um arquivo CSV/Excel, detecta colunas e extrai a série temporal."""
    try:
        contents = await file.read()
        try:
            df = pd.read_csv(io.BytesIO(contents))
        except Exception:
            df = pd.read_excel(io.BytesIO(contents))

        if df.empty:
            raise HTTPException(status_code=400, detail="O arquivo enviado está vazio.")

        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        date_cols = [c for c in df.columns if 'data' in c.lower() or 'date' in c.lower() or 'time' in c.lower() or 'dia' in c.lower()]

        if not numeric_cols:
            raise HTTPException(status_code=400, detail="Nenhuma coluna numérica encontrada no arquivo.")

        target_col = numeric_cols[0]
        date_col = date_cols[0] if date_cols else None

        values = df[target_col].dropna().tolist()
        dates = []
        if date_col:
            dates = df[date_col].astype(str).tolist()[:len(values)]
        else:
            dates = [f"Ponto {i+1}" for i in range(len(values))]

        return {
            "filename": file.filename,
            "total_rows": len(values),
            "columns": df.columns.tolist(),
            "selected_value_column": target_col,
            "selected_date_column": date_col,
            "values": values,
            "dates": dates
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao processar arquivo: {str(e)}")

# Montar o frontend estático se a pasta existir
frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_path):
    app.mount("/static", StaticFiles(directory=frontend_path), name="static")

    @app.get("/")
    def serve_index():
        return FileResponse(os.path.join(frontend_path, "index.html"))
