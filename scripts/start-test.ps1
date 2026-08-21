# start-test.ps1
$env:PYTHONUTF8 = "1"
Set-Location C:\Dev\YTDigest
$env:YTDIGEST_CONFIG_PATH = "C:\Dev\YTDigest\config.test.yaml"
$env:YTDIGEST_DB_PATH = "C:\Dev\YTDigest\data\ytdigest-test.db"
$env:YTDIGEST_LOG_DIR = "C:\Dev\YTDigest\logs\test"
$env:SENTRY_ENVIRONMENT = "test"
.venv\Scripts\python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8002
