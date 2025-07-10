# Get the installed directory of this script
$InstalledDir = Split-Path -Parent -Path $MyInvocation.MyCommand.Definition
Set-Location -Path $InstalledDir

# Add NodeJS directory to PATH
$NodeJSPath = Join-Path $InstalledDir 'nodejs'
if (-not ($env:PATH -split ';' | Select-String -Pattern $NodeJSPath -SimpleMatch)) {
    $env:PATH = "$NodeJSPath;$env:PATH"
#   [System.Environment]::SetEnvironmentVariable('PATH', $env:PATH, [System.EnvironmentVariableTarget]::User)
}

# Check for uvx.exe and uv.exe
$uvPath = (Get-Command 'uv.exe','uvx.exe' -ErrorAction SilentlyContinue)
if (-not $uvPath) {
    Write-Host "UV not found, installing UV..."
    irm https://astral.sh/uv/install.ps1 | iex
    $uvPath = Join-Path $env:USERPROFILE ".local\bin"
    $env:PATH = "$uvPath;$env:PATH"
}

# Activate or create virtual environment
$venvPath = Join-Path $InstalledDir ".venv\Scripts\activate.ps1"
if (-Not (Test-Path $venvPath)) {
    Write-Host "Creating virtual environment..."
    uv venv --prompt console-chat-gpt
}
& $venvPath

# Check and install Python packages from requirements.txt
$requirementsFile = Join-Path $InstalledDir 'requirements.txt'
if (Test-Path $requirementsFile) {
    Write-Host "Installing Python packages from requirements.txt..."
    uv pip install -r $requirementsFile
}

# Execute the main Python script
$mainPy = Join-Path $InstalledDir 'main.py'
if (Test-Path $mainPy) {
    Write-Host "Executing main.py..."
    uv run main.py
} else {
    Write-Host "main.py not found in $InstalledDir"
}
