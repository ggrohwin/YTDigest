# start.ps1
$env:PYTHONUTF8 = "1"
Set-Location C:\Dev\YTDigest
.venv\Scripts\python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8001
