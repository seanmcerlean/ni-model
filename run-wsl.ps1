param(
    [ValidateSet("static", "parquet", "full")]
    [string]$Mode = "parquet",

    [ValidateRange(1, 65535)]
    [int]$Port = 8000,

    [switch]$Help,

    [switch]$CheckDependencies
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    throw "WSL is not installed or wsl.exe is not on PATH."
}

$projectDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$distribution = $env:NI_MODEL_WSL_DISTRO

if ($projectDirectory -match '^\\\\wsl(?:\.localhost)?\\([^\\]+)(\\.*)$') {
    if (-not $distribution) {
        $distribution = $Matches[1]
    }
    $wslProject = $Matches[2].Replace('\', '/')
} else {
    $conversionArgs = @()
    if ($distribution) {
        $conversionArgs += @("--distribution", $distribution)
    }
    $wslProject = (& wsl.exe @conversionArgs wslpath -u $projectDirectory).Trim()
}

if (-not $wslProject) {
    throw "Could not translate the repository path into WSL."
}

$wslArgs = @()
if ($distribution) {
    $wslArgs += @("--distribution", $distribution)
}
$wslArgs += @("--cd", $wslProject)
if ($CheckDependencies) {
    $wslArgs += "./check-dependencies.sh"
} elseif ($Help) {
    $wslArgs += @("./run.sh", "--help")
} else {
    $wslArgs += @("./run.sh", "--mode", $Mode, "--port", $Port)
}

& wsl.exe @wslArgs
exit $LASTEXITCODE
