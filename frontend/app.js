// TimesFM Studio — Frontend Controller
document.addEventListener('DOMContentLoaded', () => {
    // State
    let currentSeries = {
        title: Logística ZYNEXLOG — Volume Diário de Encomendas,
        description: 90 dias de histórico com sazonalidade semanal e crescimento de frota.,
        unit: encomendas,
        dates: [],
        values: [],
        horizon: 14,
        freq: 0
    };

    let chartInstance = null;
    let presetsData = [];
    let lastForecastData = null;

    // DOM Elements
    const engineStatusText = document.getElementById('engineStatusText');
    const engineStatusPill = document.getElementById('engineStatusPill');
    const presetsList = document.getElementById('presetsList');
    const horizonInput = document.getElementById('horizonInput');
    const horizonVal = document.getElementById('horizonVal');
    const freqSelect = document.getElementById('freqSelect');
    const runForecastBtn = document.getElementById('runForecastBtn');
    const exportCsvBtn = document.getElementById('exportCsvBtn');
    const chartLoadingOverlay = document.getElementById('chartLoadingOverlay');

    const currentSeriesTitle = document.getElementById('currentSeriesTitle');
    const currentSeriesDesc = document.getElementById('currentSeriesDesc');
    const kpiLastVal = document.getElementById('kpiLastVal');
    const kpiUnit = document.getElementById('kpiUnit');
    const kpiAvgVal = document.getElementById('kpiAvgVal');
    const kpiTrendVal = document.getElementById('kpiTrendVal');
    const kpiTrendDesc = document.getElementById('kpiTrendDesc');
    const kpiMaxVal = document.getElementById('kpiMaxVal');
    const kpiMinVal = document.getElementById('kpiMinVal');
    const kpiLatency = document.getElementById('kpiLatency');
    const kpiEngine = document.getElementById('kpiEngine');

    const forecastTableBody = document.getElementById('forecastTableBody');
    const tableHorizonBadge = document.getElementById('tableHorizonBadge');

    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('fileInput');
    const fileUploadInfo = document.getElementById('fileUploadInfo');

    // 1. Inicializar Verificação de Saúde
    async function checkHealth() {
        try {
            const res = await fetch('/api/health');
            if (res.ok) {
                const data = await res.json();
                engineStatusText.textContent = data.model_loaded ? TimesFM 200M Pronto : Motor Estatístico Ativo;
                engineStatusPill.querySelector('.status-dot').style.background = data.model_loaded ? var(--success) : var(--accent);
            }
        } catch (e) {
            engineStatusText.textContent = Servidor Local Online;
        }
    }

    // 2. Carregar Séries Pré-configuradas (Presets)
    async function loadPresets() {
        try {
            const res = await fetch('/api/presets');
            const data = await res.json();
            presetsData = data.presets || [];
            renderPresetsList();

            // Selecionar o primeiro preset por padrão
            if (presetsData.length > 0) {
                selectPreset(presetsData[0].id);
            }
        } catch (e) {
            presetsList.innerHTML = <div class=preset-loading style=color: var(--danger)>Erro ao carregar presets.</div>;
        }
    }

    function renderPresetsList() {
        presetsList.innerHTML = '';
        presetsData.forEach((p, idx) => {
            const btn = document.createElement('button');
            btn.className = preset-btn ;
            btn.dataset.id = p.id;
            btn.innerHTML = 
                <span class=preset-btn-title></span>
                <span class=preset-btn-desc></span>
            ;
            btn.addEventListener('click', () => selectPreset(p.id));
            presetsList.appendChild(btn);
        });
    }

    function selectPreset(presetId) {
        const preset = presetsData.find(p => p.id === presetId);
        if (!preset) return;

        // Atualizar botões
        document.querySelectorAll('.preset-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.id === presetId);
        });

        // Limpar info de upload
        fileUploadInfo.style.display = 'none';

        // Atualizar estado
        currentSeries = {
            title: preset.title,
            description: preset.description,
            unit: preset.unit || 'unidades',
            dates: [...preset.dates],
            values: [...preset.values],
            horizon: preset.suggested_horizon || 14,
            freq: parseInt(freqSelect.value, 10)
        };

        // Atualizar UI
        horizonInput.value = currentSeries.horizon;
        horizonVal.textContent = ${currentSeries.horizon} passos;
        currentSeriesTitle.textContent = currentSeries.title;
        currentSeriesDesc.textContent = currentSeries.description;
        kpiUnit.textContent = currentSeries.unit;

        // Executar previsão automaticamente
        executeForecast();
    }

    // 3. Execução da Inferência
    async function executeForecast() {
        if (!currentSeries.values || currentSeries.values.length === 0) return;

        chartLoadingOverlay.style.display = 'flex';
        runForecastBtn.disabled = true;

        try {
            const payload = {
                history: currentSeries.values,
                dates: currentSeries.dates,
                horizon: parseInt(horizonInput.value, 10),
                freq: parseInt(freqSelect.value, 10)
            };

            const res = await fetch('/api/forecast', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Erro na inferência');
            }

            const data = await res.json();
            lastForecastData = data;

            updateKPIs(data);
            renderChart(data);
            renderTable(data);

        } catch (error) {
            alert(Erro ao calcular previsão: );
        } finally {
            chartLoadingOverlay.style.display = 'none';
            runForecastBtn.disabled = false;
        }
    }

    // 4. Atualizar Métricas e KPIs
    function updateKPIs(data) {
        const m = data.metrics;
        kpiLastVal.textContent = m.last_value.toLocaleString('pt-BR');
        kpiAvgVal.textContent = m.forecast_avg.toLocaleString('pt-BR');
        
        const isPositive = m.trend_percentage >= 0;
        kpiTrendVal.textContent = ${isPositive ? '+' : ''}%;
        kpiTrendVal.style.color = isPositive ? 'var(--success)' : 'var(--danger)';
        kpiTrendDesc.textContent = isPositive ? 'Tendência de Alta' : 'Tendência de Baixa';

        kpiMaxVal.textContent = m.forecast_max.toLocaleString('pt-BR');
        kpiMinVal.textContent = m.forecast_min.toLocaleString('pt-BR');

        kpiLatency.textContent = ${data.inference_time_ms} ms;
        kpiEngine.textContent = data.engine;
    }

    // 5. Renderizar Gráfico Interativo com Chart.js
    function renderChart(data) {
        const ctx = document.getElementById('forecastChart').getContext('2d');

        const histLabels = currentSeries.dates.length === currentSeries.values.length
            ? currentSeries.dates
            : currentSeries.values.map((_, i) => T-);

        const futureLabels = data.future_dates || [];
        const allLabels = [...histLabels, ...futureLabels];

        const historyPadded = [...currentSeries.values, ...Array(data.horizon).fill(null)];
        
        // A linha de previsão começa no último valor histórico para continuidade visual
        const forecastPadded = Array(currentSeries.values.length - 1).fill(null);
        forecastPadded.push(currentSeries.values[currentSeries.values.length - 1]);
        forecastPadded.push(...data.forecast);

        const lowerPadded = Array(currentSeries.values.length - 1).fill(null);
        lowerPadded.push(currentSeries.values[currentSeries.values.length - 1]);
        lowerPadded.push(...data.lower_bound);

        const upperPadded = Array(currentSeries.values.length - 1).fill(null);
        upperPadded.push(currentSeries.values[currentSeries.values.length - 1]);
        upperPadded.push(...data.upper_bound);

        if (chartInstance) {
            chartInstance.destroy();
        }

        // Criar gradiente para a área histórica
        const histGradient = ctx.createLinearGradient(0, 0, 0, 350);
        histGradient.addColorStop(0, 'rgba(59, 130, 246, 0.25)');
        histGradient.addColorStop(1, 'rgba(59, 130, 246, 0.0)');

        chartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: allLabels,
                datasets: [
                    {
                        label: 'Limite Superior (90%)',
                        data: upperPadded,
                        borderColor: 'transparent',
                        backgroundColor: 'rgba(56, 189, 248, 0.12)',
                        fill: '+1',
                        pointRadius: 0,
                        tension: 0.3
                    },
                    {
                        label: 'Limite Inferior (90%)',
                        data: lowerPadded,
                        borderColor: 'transparent',
                        backgroundColor: 'transparent',
                        fill: false,
                        pointRadius: 0,
                        tension: 0.3
                    },
                    {
                        label: 'Histórico Registrado',
                        data: historyPadded,
                        borderColor: '#3b82f6',
                        backgroundColor: histGradient,
                        borderWidth: 2.2,
                        fill: true,
                        pointRadius: currentSeries.values.length > 50 ? 0 : 3,
                        pointHoverRadius: 5,
                        tension: 0.25
                    },
                    {
                        label: 'Previsão TimesFM',
                        data: forecastPadded,
                        borderColor: '#38bdf8',
                        borderWidth: 2.5,
                        borderDash: [5, 4],
                        backgroundColor: 'transparent',
                        pointRadius: 4,
                        pointBackgroundColor: '#38bdf8',
                        pointBorderColor: '#080c14',
                        pointBorderWidth: 2,
                        pointHoverRadius: 6,
                        tension: 0.25
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    intersect: false,
                    mode: 'index'
                },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: 'rgba(12, 18, 30, 0.95)',
                        borderColor: '#1e2d4a',
                        borderWidth: 1,
                        titleColor: '#f8fafc',
                        bodyColor: '#94a3b8',
                        padding: 12,
                        cornerRadius: 8,
                        callbacks: {
                            label: function(context) {
                                if (context.raw === null || context.dataset.label.includes('Limite')) return null;
                                return  :  ;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { color: 'rgba(30, 45, 74, 0.4)' },
                        ticks: {
                            color: '#64748b',
                            maxTicksLimit: 12,
                            font: { family: 'Inter', size: 11 }
                        }
                    },
                    y: {
                        grid: { color: 'rgba(30, 45, 74, 0.4)' },
                        ticks: {
                            color: '#64748b',
                            font: { family: 'JetBrains Mono', size: 11 }
                        }
                    }
                }
            }
        });
    }

    // 6. Renderizar Tabela de Previsões
    function renderTable(data) {
        forecastTableBody.innerHTML = '';
        tableHorizonBadge.textContent = ${data.horizon} passos futuros;

        data.forecast.forEach((val, idx) => {
            const dateStr = data.future_dates[idx] || Passo +;
            const lower = data.lower_bound[idx];
            const upper = data.upper_bound[idx];
            const spread = upper - lower;
            const isUncertain = spread > (val * 0.4);

            const tr = document.createElement('tr');
            tr.innerHTML = 
                <td><strong></strong></td>
                <td style=color: var(--accent); font-weight: 600;></td>
                <td style=color: #f87171;></td>
                <td style=color: #34d399;></td>
                <td>
                    <span class=risk-badge >
                        
                    </span>
                </td>
            ;
            forecastTableBody.appendChild(tr);
        });
    }

    // 7. Eventos de Upload de Arquivo
    dropzone.addEventListener('click', () => fileInput.click());

    dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropzone.classList.add('dragover');
    });

    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));

    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
            handleFileUpload(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFileUpload(e.target.files[0]);
        }
    });

    async function handleFileUpload(file) {
        const formData = new FormData();
        formData.append('file', file);

        fileUploadInfo.style.display = 'block';
        fileUploadInfo.innerHTML = Lendo <strong></strong>...;

        try {
            const res = await fetch('/api/upload-csv', {
                method: 'POST',
                body: formData
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Erro ao processar arquivo.');
            }

            const data = await res.json();

            // Desmarcar botões de preset
            document.querySelectorAll('.preset-btn').forEach(btn => btn.classList.remove('active'));

            currentSeries = {
                title: Dados Importados: ,
                description: ${data.total_rows} registros lidos da coluna ".,
 unit: 'unidades',
 dates: data.dates,
 values: data.values,
 horizon: parseInt(horizonInput.value, 10),
 freq: parseInt(freqSelect.value, 10)
 };

 currentSeriesTitle.textContent = currentSeries.title;
 currentSeriesDesc.textContent = currentSeries.description;
 kpiUnit.textContent = currentSeries.unit;

 fileUploadInfo.innerHTML = <strong></strong>: pontos identificados com sucesso!;

 executeForecast();
 } catch (err) {
 fileUploadInfo.style.background = 'rgba(239, 68, 68, 0.15)';
 fileUploadInfo.style.borderColor = 'rgba(239, 68, 68, 0.4)';
 fileUploadInfo.style.color = '#fca5a5';
 fileUploadInfo.innerHTML = Erro: ;
 }
 }

 // 8. Controles e Eventos de UI
 horizonInput.addEventListener('input', (e) => {
 horizonVal.textContent = ${e.target.value} passos;
 });

 runForecastBtn.addEventListener('click', () => {
 executeForecast();
 });

 exportCsvBtn.addEventListener('click', () => {
 if (!lastForecastData) {
 alert('Calcule uma previsão antes de exportar.');
 return;
 }

 let csvContent = data:text/csv;charset=utf-8,Data_Passo,Previsao_TimesFM,Limite_Inferior_90,Limite_Superior_90\n;
 lastForecastData.forecast.forEach((val, idx) => {
 const dateStr = lastForecastData.future_dates[idx] || T+;
 const lower = lastForecastData.lower_bound[idx];
 const upper = lastForecastData.upper_bound[idx];
 csvContent += ,,,\n;
 });

 const encodedUri = encodeURI(csvContent);
 const link = document.createElement(a);
 link.setAttribute(href, encodedUri);
 link.setAttribute(download, imesfm_previsao_.csv);
 document.body.appendChild(link);
 link.click();
 document.body.removeChild(link);
 });

 // Iniciar
 checkHealth();
 loadPresets();
});
