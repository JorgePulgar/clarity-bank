# start_demo.ps1 — Arranca API + dashboard y abre el navegador
# Uso: .\start_demo.ps1

$Root = $PSScriptRoot
$Venv = Join-Path $Root ".venv\Scripts"
$Python = Join-Path $Venv "python.exe"
$Pip    = Join-Path $Venv "pip.exe"
$Uvicorn   = Join-Path $Venv "uvicorn.exe"
$Streamlit = Join-Path $Venv "streamlit.exe"

Write-Host "`n=== ClarityBank Demo ===" -ForegroundColor Cyan

# 1. Instalar dependencias si faltan
Write-Host "[1/4] Instalando dependencias..." -ForegroundColor Yellow
& $Pip install -r "$Root\requirements.txt" -q
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: pip install fallo. Revisa requirements.txt." -ForegroundColor Red
    exit 1
}

# 2. Crear directorio data/ si no existe
$DataDir = Join-Path $Root "data"
if (-not (Test-Path $DataDir)) { New-Item -ItemType Directory $DataDir | Out-Null }

# 3. Arrancar uvicorn en ventana separada
Write-Host "[2/4] Arrancando API en http://127.0.0.1:8000 ..." -ForegroundColor Yellow
$ApiProc = Start-Process -FilePath "powershell.exe" `
    -ArgumentList "-NoExit", "-Command", "& '$Uvicorn' api.main:app --reload --port 8000" `
    -WorkingDirectory $Root `
    -PassThru

# 4. Esperar a que la API responda
Write-Host "[3/4] Esperando que la API este lista..." -ForegroundColor Yellow
$Timeout = 30
$Ready = $false
for ($i = 0; $i -lt $Timeout; $i++) {
    Start-Sleep -Seconds 1
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -ErrorAction Stop
        if ($r.StatusCode -eq 200) { $Ready = $true; break }
    } catch {}
    Write-Host "  esperando... ($($i+1)s)" -ForegroundColor DarkGray
}

if (-not $Ready) {
    Write-Host "ERROR: API no respondio en $Timeout s. Revisa la ventana de uvicorn." -ForegroundColor Red
    exit 1
}
Write-Host "  API OK" -ForegroundColor Green

# 5. Arrancar Streamlit (abre navegador automaticamente en localhost:8501)
Write-Host "[4/4] Abriendo dashboard en http://localhost:8501 ..." -ForegroundColor Yellow
Set-Location $Root
& $Streamlit run "$Root\dashboard\streamlit_app.py" --server.port 8501
