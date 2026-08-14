# GuardMatch AI — task runner for Windows
#
# The Makefile is the canonical task list and is what CI uses, but `make` is not
# available on a default Windows install. This script mirrors those targets so
# the same commands are available locally.
#
#   .\tasks.ps1 help
#   .\tasks.ps1 install
#   .\tasks.ps1 check

param(
    [Parameter(Position = 0)]
    [string]$Task = "help"
)

$ErrorActionPreference = "Stop"
$CondaEnv = "guardmatch"

function Invoke-InEnv {
    param([string[]]$CommandArgs)
    Write-Host "> conda run -n $CondaEnv $($CommandArgs -join ' ')" -ForegroundColor DarkGray
    & conda run -n $CondaEnv --no-capture-output @CommandArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED (exit $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

switch ($Task.ToLower()) {

    "help" {
        Write-Host ""
        Write-Host "GuardMatch AI — available tasks" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  install         Install the package with dev extras and the spaCy model"
        Write-Host "  lint            Run ruff checks"
        Write-Host "  format          Apply ruff formatting and auto-fixes"
        Write-Host "  typecheck       Run mypy in strict mode"
        Write-Host "  test            Run the full test suite with coverage"
        Write-Host "  test-fast       Run the test suite without slow tests"
        Write-Host "  gates           Run only the fairness and leakage gates"
        Write-Host "  check           lint + typecheck + test (everything CI runs)"
        Write-Host ""
        Write-Host "  generate-data   Generate the synthetic dataset"
        Write-Host "  train           Train the ranker and write versioned artifacts"
        Write-Host "  audit           Run the fairness audit against the active model"
        Write-Host "  serve           Run the API locally with reload"
        Write-Host ""
        Write-Host "  docker-build    Build the container image"
        Write-Host "  docker-up       Run the service via docker compose"
        Write-Host "  clean           Remove caches and build artifacts"
        Write-Host ""
    }

    "install" {
        Invoke-InEnv @("pip", "install", "-e", ".[dev]")
        Invoke-InEnv @("python", "-m", "spacy", "download", "en_core_web_sm")
    }

    "lint"      { Invoke-InEnv @("ruff", "check", ".") }

    "format" {
        Invoke-InEnv @("ruff", "format", ".")
        Invoke-InEnv @("ruff", "check", "--fix", ".")
    }

    "typecheck" { Invoke-InEnv @("mypy", "src") }
    "test"      { Invoke-InEnv @("pytest") }
    "test-fast" { Invoke-InEnv @("pytest", "-m", "not slow") }
    "gates"     { Invoke-InEnv @("pytest", "-m", "gate", "-v") }

    "check" {
        Invoke-InEnv @("ruff", "check", ".")
        Invoke-InEnv @("mypy", "src")
        Invoke-InEnv @("pytest")
        Write-Host ""
        Write-Host "All checks passed." -ForegroundColor Green
    }

    "generate-data" { Invoke-InEnv @("guardmatch", "generate-data") }
    "train"         { Invoke-InEnv @("guardmatch", "train") }
    "audit"         { Invoke-InEnv @("guardmatch", "audit") }

    "serve" {
        Invoke-InEnv @("uvicorn", "guardmatch.api.app:app", "--reload", "--host", "0.0.0.0", "--port", "8000")
    }

    "docker-build" {
        & docker build -t guardmatch-ai:0.1.0 .
    }

    "docker-up" {
        & docker compose up --build
    }

    "clean" {
        $targets = @(".pytest_cache", ".mypy_cache", ".ruff_cache", "htmlcov",
                     ".coverage", "coverage.xml", "build", "dist")
        foreach ($t in $targets) {
            if (Test-Path $t) {
                Remove-Item -Recurse -Force $t
                Write-Host "removed $t"
            }
        }
        Get-ChildItem -Recurse -Directory -Filter "__pycache__" |
            ForEach-Object { Remove-Item -Recurse -Force $_.FullName }
        Write-Host "Clean." -ForegroundColor Green
    }

    default {
        Write-Host "Unknown task: $Task" -ForegroundColor Red
        Write-Host "Run '.\tasks.ps1 help' to see available tasks."
        exit 1
    }
}
