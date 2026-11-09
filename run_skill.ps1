# PowerShell helper. Default read-only/dry run. See references/automation-and-launch.md.
param(
    [Parameter(Mandatory=$true)][string]$Config,
    [ValidateSet("doctor","run","deploy","compile","launch")][string]$Action = "run",
    [switch]$Fix,
    [switch]$RigAccessories,
    [switch]$RepairSeams,
    [switch]$Deploy,
    [switch]$Compile,
    [switch]$Launch,
    [switch]$GameTest,
    [switch]$Execute,
    [switch]$AllowPendingPreview,
    [switch]$NoHeightPrompt,
    [string]$Audit = ""
)
$ErrorActionPreference = "Stop"
$Tool = Join-Path $PSScriptRoot "scripts/auto_workflow.py"
$argsList = @($Tool, $Action, "--config", $Config)
if ($Fix) { $argsList += "--fix" }
if ($RigAccessories) { $argsList += "--rig-accessories" }
if ($RepairSeams) { $argsList += "--repair-seams" }
if ($Deploy) { $argsList += "--deploy" }
if ($Compile) { $argsList += "--compile" }
if ($Launch) { $argsList += "--launch" }
if ($GameTest) { $argsList += "--game-test" }
if ($Execute) { $argsList += "--execute" }
if ($NoHeightPrompt) { $argsList += "--no-height-prompt" }
if ($AllowPendingPreview) { $argsList += "--allow-pending-preview" }
if ($Audit) { $argsList += @("--audit", $Audit) }
& python @argsList
exit $LASTEXITCODE
