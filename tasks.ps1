# GuardMatch AI - task runner for Windows
#
# The Makefile is the canonical task list and is what CI mirrors, but `make` is
# not available on a default Windows install. This script mirrors those targets
# so the same commands are available locally.
#
# The repository holds two runtimes. Every task changes into the directory it
# belongs to, so a contributor never has to know whether a command is a backend
# or a frontend concern.
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
$RepoRoot = $PSScriptRoot
$Backend  = Join-Path $RepoRoot "backend"
$Frontend = Join-Path $RepoRoot "frontend"

function Invoke-InEnv {
    # Backend task: run inside the conda environment, from backend/.
    param([string[]]$CommandArgs)
    Write-Host "> [backend] conda run -n $CondaEnv $($CommandArgs -join ' ')" -ForegroundColor DarkGray
    Push-Location $Backend
    try {
        & conda run -n $CondaEnv --no-capture-output @CommandArgs
        if ($LASTEXITCODE -ne 0) {
            Write-Host "FAILED (exit $LASTEXITCODE)" -ForegroundColor Red
            exit $LASTEXITCODE
        }
    }
    finally {
        Pop-Location
    }
}

function Invoke-InWeb {
    # Frontend task: run from frontend/, no conda involved.
    param([string]$Exe, [string[]]$CommandArgs)

    # NODE LAUNCHERS MUST BE THE .cmd SHIM, NOT THE BARE NAME
    #
    # On Windows, `npm` resolves to npm.ps1, and that shim builds a command
    # string and runs it through Invoke-Expression. A splatted array of
    # arguments does not survive that: the arguments are folded into the string
    # and re-parsed, and npm receives nothing it recognises. Every frontend task
    # here failed with npm's usage message, which reads like a bad task name
    # rather than a launcher problem.
    #
    # The .cmd shim passes arguments through as a normal argument list, so it is
    # used explicitly. Typing `npm run lint` by hand works, which is why this
    # went unnoticed: the fault only appears through a splat.
    if ($Exe -in @("npm", "npx")) { $Exe = "$Exe.cmd" }

    Write-Host "> [frontend] $Exe $($CommandArgs -join ' ')" -ForegroundColor DarkGray
    if (-not (Test-Path $Frontend)) {
        Write-Host "frontend/ does not exist yet - skipping." -ForegroundColor Yellow
        return
    }
    Push-Location $Frontend
    try {
        & $Exe @CommandArgs
        if ($LASTEXITCODE -ne 0) {
            Write-Host "FAILED (exit $LASTEXITCODE)" -ForegroundColor Red
            exit $LASTEXITCODE
        }
    }
    finally {
        Pop-Location
    }
}

switch ($Task.ToLower()) {

    "help" {
        Write-Host ""
        Write-Host "GuardMatch AI - available tasks" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  Backend" -ForegroundColor Cyan
        Write-Host "  install         Install the backend with dev extras and the spaCy model"
        Write-Host "  lint            Run ruff checks"
        Write-Host "  format          Apply ruff formatting and auto-fixes"
        Write-Host "  typecheck       Run mypy in strict mode"
        Write-Host "  test            Run the full test suite with coverage"
        Write-Host "  test-fast       Run the test suite without slow tests"
        Write-Host "  gates           Run only the fairness and leakage gates"
        Write-Host ""
        Write-Host "  generate-data   Generate the synthetic dataset"
        Write-Host "  train           Train the ranker and write versioned artifacts"
        Write-Host "  audit           Run the fairness audit against the active model"
        Write-Host "  serve           Run the API locally with reload"
        Write-Host ""
        Write-Host "  Frontend" -ForegroundColor Cyan
        Write-Host "  web-install     Install frontend dependencies from the lockfile"
        Write-Host "  web-dev         Run the dev server against a local API on :8000"
        Write-Host "  web-lint        Run eslint"
        Write-Host "  web-typecheck   Type check without emitting"
        Write-Host "  web-test        Run the frontend unit tests"
        Write-Host "  web-build       Produce the standalone production build"
        Write-Host ""
        Write-Host "  Everything" -ForegroundColor Cyan
        Write-Host "  check           Every check CI runs, both runtimes"
        Write-Host "  docker-build    Build both container images"
        Write-Host "  docker-up       Run the full stack via docker compose"
        Write-Host "  clean           Remove caches and build artifacts"
        Write-Host ""
    }

    # -----------------------------------------------------------------------
    # Backend
    # -----------------------------------------------------------------------

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

    "generate-data" { Invoke-InEnv @("guardmatch", "generate-data") }
    "train"         { Invoke-InEnv @("guardmatch", "train") }
    "audit"         { Invoke-InEnv @("guardmatch", "audit") }

    "serve" {
        Invoke-InEnv @("uvicorn", "guardmatch.api.app:app", "--reload", "--host", "0.0.0.0", "--port", "8000")
    }

    # -----------------------------------------------------------------------
    # Frontend
    # -----------------------------------------------------------------------

    "web-install"   { Invoke-InWeb "npm" @("ci") }
    "web-dev"       { Invoke-InWeb "npm" @("run", "dev") }
    "web-lint"      { Invoke-InWeb "npm" @("run", "lint") }
    "web-typecheck" { Invoke-InWeb "npm" @("run", "typecheck") }
    "web-test"      { Invoke-InWeb "npm" @("test") }
    "web-build"     { Invoke-InWeb "npm" @("run", "build") }

    # -----------------------------------------------------------------------
    # Everything
    # -----------------------------------------------------------------------

    "check" {
        Invoke-InEnv @("ruff", "check", ".")
        Invoke-InEnv @("mypy", "src")
        Invoke-InEnv @("pytest")
        Invoke-InWeb "npm" @("run", "lint")
        Invoke-InWeb "npx" @("tsc", "--noEmit")
        Invoke-InWeb "npm" @("test")
        Invoke-InWeb "npm" @("run", "build")
        Write-Host ""
        Write-Host "All checks passed." -ForegroundColor Green
    }

    "docker-build" {
        & docker build -t guardmatch-ai:0.1.0 $Backend
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & docker build -t guardmatch-web:0.1.0 $Frontend
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }

    "docker-up" {
        & docker compose up --build
    }

    "clean" {
        $backendTargets = @(".pytest_cache", ".mypy_cache", ".ruff_cache", "htmlcov",
                            ".coverage", "coverage.xml", "build", "dist")
        foreach ($t in $backendTargets) {
            $path = Join-Path $Backend $t
            if (Test-Path $path) {
                Remove-Item -Recurse -Force $path
                Write-Host "removed backend/$t"
            }
        }
        $frontendTargets = @(".next", "out", "coverage")
        foreach ($t in $frontendTargets) {
            $path = Join-Path $Frontend $t
            if (Test-Path $path) {
                Remove-Item -Recurse -Force $path
                Write-Host "removed frontend/$t"
            }
        }
        Get-ChildItem -Path $Backend -Recurse -Directory -Filter "__pycache__" |
            ForEach-Object { Remove-Item -Recurse -Force $_.FullName }
        Write-Host "Clean." -ForegroundColor Green
    }

    default {
        Write-Host "Unknown task: $Task" -ForegroundColor Red
        Write-Host "Run '.\tasks.ps1 help' to see available tasks."
        exit 1
    }
}
