import os
import io
import time
import logging
import threading
import pandas as pd
import numpy as np
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from engine import engine
from lottery_service import lottery_service, LotteryUnavailable, LOTTERY_CONFIGS
from lottery_history import lottery_history
from ticket_scanner import ticket_scanner
from ticket_checker import check_ticket

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

class TicketCheckRequest(BaseModel):
    game_id: str = Field(..., description="Modalidade do bilhete: megasena, quina, lotofacil, lotomania")
    numbers: List[str] = Field(..., min_length=1, max_length=60, description="Dezenas apostadas no bilhete")
    contest: Optional[int] = Field(default=None, ge=1, le=99999, description="Numero do concurso; vazio usa o ultimo")
    games: Optional[List[List[str]]] = Field(default=None, description="Lista de jogos individuais no comprovante")

@app.on_event("startup")
def aquecer_historico_oficial():
    """
    Baixa o historico real da Caixa em segundo plano assim que o servidor sobe.

    Sem isso, o primeiro visitante de cada modalidade espera os ~5s da busca concurso
    a concurso. Como sorteio ja realizado nunca muda, esse custo e pago uma unica vez
    e o cache em disco atravessa deploys.
    """
    def aquecer():
        log = logging.getLogger("startup")

        # Ordem importa: primeiro os quatro ultimos concursos (4 chamadas baratas que
        # ja deixam o dashboard de pe e gravadas em disco), so depois o historico. Ao
        # contrario, uma rajada de historico derruba ate a consulta do ultimo concurso.
        for game_id in LOTTERY_CONFIGS:
            try:
                dados = lottery_service.fetch_latest_contest(game_id)
                log.info("Ultimo concurso de %s pronto: #%s", game_id, dados.get("concurso"))
            except Exception as e:
                log.warning("Ultimo concurso de %s indisponivel: %s", game_id, e)
            time.sleep(5)

        for game_id in LOTTERY_CONFIGS:
            try:
                total = len(lottery_service.fetch_historical_draws(game_id, count=60))
                log.info("Historico de %s pronto: %d concursos reais", game_id, total)
            except Exception as e:
                log.warning("Historico de %s adiado: %s", game_id, e)
            time.sleep(30)

    threading.Thread(target=aquecer, name="aquecer-historico", daemon=True).start()

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

@app.get("/api/lottery/source-status")
def source_status():
    """Testa a fonte oficial agora e reporta o erro exato de cada modalidade."""
    return {
        "fonte": "servicebus2.caixa.gov.br",
        "modalidades": lottery_service.diagnose(),
        "cache_historico": {g: lottery_history.cached_count(g) for g in LOTTERY_CONFIGS},
        "diretorio_cache": lottery_history.cache_dir or "(nenhum gravavel)",
    }

@app.get("/api/lottery/source-probe")
def source_probe():
    """
    Testa varias formas de falar com a Caixa e diz qual atravessa o bloqueio.

    A VPS recebe 403 em ~20ms enquanto a mesma chamada funciona de fora dela. Sem
    terminal na maquina, e o proprio servidor que precisa medir as alternativas.
    """
    from lottery_probe import executar
    return executar()

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
    except LotteryUnavailable as lu:
        raise HTTPException(status_code=503, detail=str(lu))
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
    except LotteryUnavailable as lu:
        raise HTTPException(status_code=503, detail=str(lu))
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
    except LotteryUnavailable as lu:
        raise HTTPException(status_code=503, detail=str(lu))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro durante a predição da loteria: {str(e)}")

# ==========================================
# ROTAS DE CONFERÊNCIA DE BILHETES FÍSICOS
# ==========================================

MAX_TICKET_IMAGE_BYTES = 8 * 1024 * 1024
ALLOWED_TICKET_MIMES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}

@app.get("/api/lottery/scanner-status")
def scanner_status():
    """Diagnóstico honesto do módulo óptico: diz se OCR e leitor de QR estão de pé."""
    available, reason = ticket_scanner.is_available()
    return {
        "ocr_available": available,
        "detail": reason,
        "note": ("O QR do comprovante da Caixa não carrega as dezenas apostadas. "
                 "As dezenas são lidas do texto impresso via OCR e sempre confirmadas pelo usuário.")
    }

@app.post("/api/lottery/scan-ticket")
async def scan_ticket(file: UploadFile = File(...), game_id: Optional[str] = Form(default=None)):
    """
    Recebe a foto do comprovante e devolve modalidade, concurso e dezenas lidas.
    Nunca confere sozinho: o retorno exige confirmação do usuário na tela.
    """
    if file.content_type not in ALLOWED_TICKET_MIMES:
        raise HTTPException(status_code=415, detail=f"Formato de imagem não suportado: {file.content_type}")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Arquivo de imagem vazio.")
    if len(content) > MAX_TICKET_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Imagem acima de 8MB. Reduza a resolução da foto.")

    hint = game_id.lower() if game_id and game_id.lower() in LOTTERY_CONFIGS else None
    result = ticket_scanner.scan(content, hint_game=hint)
    return {"success": result["success"], "data": result}

@app.post("/api/lottery/check-ticket")
def check_ticket_route(payload: TicketCheckRequest):
    """Confere as dezenas informadas contra o resultado oficial da Caixa."""
    try:
        result = check_ticket(payload.game_id, payload.numbers, payload.contest, payload.games)
        return {"success": True, "data": result}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Erro ao conferir o bilhete na base da Caixa: {str(e)}")

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
