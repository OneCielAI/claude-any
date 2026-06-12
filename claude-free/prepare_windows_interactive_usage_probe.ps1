param(
    [string]$Model = "claude-sonnet-4-5",
    [int]$TargetTotalTokens = 1000000,
    [int]$TokensPerCall = 50000,
    [int]$Seed = 451045
)

$ErrorActionPreference = "Stop"

function Get-FreeTcpPort {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Parse("127.0.0.1"), 0)
    try {
        $listener.Start()
        return $listener.LocalEndpoint.Port
    }
    finally {
        $listener.Stop()
    }
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Resolve-Path (Join-Path $ScriptDir "..")
$RunScript = Join-Path $ScriptDir "run_real_billing_load_probe.py"

if (-not (Test-Path $RunScript)) {
    throw "Missing $RunScript"
}

$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) {
    $python = (Get-Command py -ErrorAction SilentlyContinue).Source
}
if (-not $python) {
    throw "Python was not found on PATH."
}

Write-Host "[claude-free] generating dry-run prompt set..."
$output = & $python $RunScript `
    --mode routed `
    --model $Model `
    --target-total-tokens $TargetTotalTokens `
    --tokens-per-call $TokensPerCall `
    --seed $Seed `
    --prompts-only 2>&1

$output | ForEach-Object { Write-Host $_ }

$evidenceLine = $output | Where-Object { $_ -match "^Evidence directory:\s+(.+)$" } | Select-Object -Last 1
if (-not $evidenceLine) {
    throw "Could not find evidence directory in generator output."
}
$EvidenceDir = ($evidenceLine -replace "^Evidence directory:\s+", "").Trim()
$EvidenceDir = (Resolve-Path $EvidenceDir).Path
$PromptsDir = Join-Path $EvidenceDir "prompts"
$ConfigDir = Join-Path $EvidenceDir "claude-any-config"
$RouterPort = Get-FreeTcpPort

New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null

$copyPromptPath = Join-Path $EvidenceDir "copy-prompt.ps1"
$sendUsagePath = Join-Path $EvidenceDir "send-usage.ps1"
$sendPromptPath = Join-Path $EvidenceDir "send-prompt.ps1"
$submitPromptPath = Join-Path $EvidenceDir "submit-prompt-continue.ps1"
$resumeRoutedPath = Join-Path $EvidenceDir "resume-routed-claude.ps1"
$launchRoutedPath = Join-Path $EvidenceDir "launch-claude-any-routed.ps1"
$collectLogsPath = Join-Path $EvidenceDir "collect-logs.ps1"
$checkpointsPath = Join-Path $EvidenceDir "usage-checkpoints.md"
$stepsPath = Join-Path $EvidenceDir "WINDOWS_INTERACTIVE_STEPS.md"

$copyPromptContent = @"
param(
    [Parameter(Mandatory = `$true)]
    [int]`$Index
)

`$ErrorActionPreference = "Stop"
`$PromptPath = Join-Path "$PromptsDir" ("call-{0:D3}.txt" -f `$Index)
if (-not (Test-Path `$PromptPath)) {
    throw "Prompt file not found: `$PromptPath"
}
`$text = Get-Content -Raw -Encoding UTF8 `$PromptPath
`$text | Set-Clipboard
`$estimated = [math]::Floor(`$text.Length / 4)
Write-Host "Copied prompt #`$Index to clipboard."
Write-Host "File: `$PromptPath"
Write-Host "Chars: `$(`$text.Length); rough tokens: `$estimated"
Write-Host "Paste into Claude Code, wait for completion, then run /usage and capture the screen."
"@
$copyPromptContent | Set-Content -Path $copyPromptPath -Encoding UTF8

$sendUsageContent = @"
param(
    [int]`$DelaySeconds = 3
)

`$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms
Write-Host "Focus the Claude Code window now. Sending /usage in `$DelaySeconds seconds..."
Start-Sleep -Seconds `$DelaySeconds
Set-Clipboard "/usage"
[System.Windows.Forms.SendKeys]::SendWait("^v")
Start-Sleep -Milliseconds 150
[System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
Write-Host "Sent /usage to the focused window."
"@
$sendUsageContent | Set-Content -Path $sendUsagePath -Encoding UTF8

$sendPromptContent = @"
param(
    [Parameter(Mandatory = `$true)]
    [int]`$Index,
    [int]`$DelaySeconds = 5
)

`$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms
`$PromptPath = Join-Path "$PromptsDir" ("call-{0:D3}.txt" -f `$Index)
if (-not (Test-Path `$PromptPath)) {
    throw "Prompt file not found: `$PromptPath"
}
`$text = Get-Content -Raw -Encoding UTF8 `$PromptPath
`$text | Set-Clipboard
`$estimated = [math]::Floor(`$text.Length / 4)
Write-Host "Prepared prompt #`$Index."
Write-Host "File: `$PromptPath"
Write-Host "Chars: `$(`$text.Length); rough tokens: `$estimated"
Write-Host "Focus the Claude Code window now. Pasting and submitting in `$DelaySeconds seconds..."
Start-Sleep -Seconds `$DelaySeconds
[System.Windows.Forms.SendKeys]::SendWait("^v")
Start-Sleep -Milliseconds 250
[System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
Write-Host "Sent prompt #`$Index to the focused window."
"@
$sendPromptContent | Set-Content -Path $sendPromptPath -Encoding UTF8

$submitPromptContent = @"
param(
    [Parameter(Mandatory = `$true)]
    [int]`$Index,
    [int]`$TimeoutSeconds = 1800,
    [string]`$SessionId = ""
)

`$ErrorActionPreference = "Stop"
`$env:CLAUDE_ANY_CONFIG_DIR = "$ConfigDir"
`$env:CLAUDE_ANY_ROUTER_PORT = "$RouterPort"
`$env:ANTHROPIC_BASE_URL = "http://127.0.0.1:$RouterPort"
`$env:ANTHROPIC_MODEL = "claude-any-anthropic-$Model"
`$env:CLAUDE_ANY_PROVIDER = "anthropic"
`$env:CLAUDE_ANY_MODEL_ALIAS = "claude-any-anthropic-$Model"
`$env:CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY = "1"
`$env:CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS = "1"
`$env:CLAUDE_CODE_ATTRIBUTION_HEADER = "0"
Remove-Item Env:\ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:\ANTHROPIC_AUTH_TOKEN -ErrorAction SilentlyContinue

`$PromptPath = Join-Path "$PromptsDir" ("call-{0:D3}.txt" -f `$Index)
if (-not (Test-Path `$PromptPath)) {
    throw "Prompt file not found: `$PromptPath"
}

try {
    `$health = Invoke-RestMethod -Uri "http://127.0.0.1:$RouterPort/health" -TimeoutSec 5
    Write-Host "Router health: `$(`$health.status) pid=`$(`$health.pid) version=`$(`$health.version)"
}
catch {
    throw "claude-any router is not reachable on port $RouterPort. Run launch-claude-any-routed.ps1 first and keep it open."
}

`$CallsDir = Join-Path "$EvidenceDir" "calls"
New-Item -ItemType Directory -Force -Path `$CallsDir | Out-Null
`$Prefix = "interactive-submit-{0:D3}" -f `$Index
`$StdoutPath = Join-Path `$CallsDir ("`$Prefix.stdout.txt")
`$StderrPath = Join-Path `$CallsDir ("`$Prefix.stderr.txt")
`$DebugPath = Join-Path `$CallsDir ("`$Prefix.debug.log")
`$MetaPath = Join-Path `$CallsDir ("`$Prefix.meta.json")

`$ClaudeArgs = @()
if (`$SessionId) {
    `$ClaudeArgs += @("--resume", `$SessionId)
}
else {
    `$ClaudeArgs += "-c"
}
`$ClaudeArgs += @("-p", "--debug", "--debug-file", `$DebugPath)

`$text = Get-Content -Raw -Encoding UTF8 `$PromptPath
`$estimated = [math]::Floor(`$text.Length / 4)
Write-Host "Submitting prompt #`$Index through claude -p without clipboard paste."
Write-Host "File: `$PromptPath"
Write-Host "Chars: `$(`$text.Length); rough tokens: `$estimated"
Write-Host "Stdout: `$StdoutPath"
Write-Host "Stderr: `$StderrPath"
Write-Host "Debug:  `$DebugPath"

`$psi = [System.Diagnostics.ProcessStartInfo]::new()
`$psi.FileName = "claude"
foreach (`$arg in `$ClaudeArgs) {
    [void]`$psi.ArgumentList.Add(`$arg)
}
`$psi.WorkingDirectory = "$Root"
`$psi.UseShellExecute = `$false
`$psi.RedirectStandardInput = `$true
`$psi.RedirectStandardOutput = `$true
`$psi.RedirectStandardError = `$true

`$startedAt = [DateTimeOffset]::UtcNow
`$proc = [System.Diagnostics.Process]::Start(`$psi)
`$stdoutTask = `$proc.StandardOutput.ReadToEndAsync()
`$stderrTask = `$proc.StandardError.ReadToEndAsync()
`$proc.StandardInput.Write(`$text)
`$proc.StandardInput.Close()

if (-not `$proc.WaitForExit(`$TimeoutSeconds * 1000)) {
    try { `$proc.Kill(`$true) } catch {}
    throw "claude -p timed out after `$TimeoutSeconds seconds."
}

`$stdout = `$stdoutTask.GetAwaiter().GetResult()
`$stderr = `$stderrTask.GetAwaiter().GetResult()
`$stdout | Set-Content -Path `$StdoutPath -Encoding UTF8
`$stderr | Set-Content -Path `$StderrPath -Encoding UTF8

`$meta = [ordered]@{
    index = `$Index
    prompt_path = `$PromptPath
    prompt_chars = `$text.Length
    estimated_tokens = `$estimated
    exit_code = `$proc.ExitCode
    started_at = `$startedAt.ToString("o")
    finished_at = [DateTimeOffset]::UtcNow.ToString("o")
    claude_args = `$ClaudeArgs
    stdout_path = `$StdoutPath
    stderr_path = `$StderrPath
    debug_path = `$DebugPath
}
`$meta | ConvertTo-Json -Depth 5 | Set-Content -Path `$MetaPath -Encoding UTF8

Write-Host "Exit code: `$(`$proc.ExitCode)"
Write-Host "Saved meta: `$MetaPath"
Write-Host "After this finishes, reopen/return to Claude Code and run /usage for the visible quota screenshot."
exit `$proc.ExitCode
"@
$submitPromptContent | Set-Content -Path $submitPromptPath -Encoding UTF8

$resumeRoutedContent = @"
`$ErrorActionPreference = "Stop"
`$env:CLAUDE_ANY_CONFIG_DIR = "$ConfigDir"
`$env:CLAUDE_ANY_ROUTER_PORT = "$RouterPort"
`$env:ANTHROPIC_BASE_URL = "http://127.0.0.1:$RouterPort"
`$env:ANTHROPIC_MODEL = "claude-any-anthropic-$Model"
`$env:CLAUDE_ANY_PROVIDER = "anthropic"
`$env:CLAUDE_ANY_MODEL_ALIAS = "claude-any-anthropic-$Model"
`$env:CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY = "1"
`$env:CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS = "1"
`$env:CLAUDE_CODE_ATTRIBUTION_HEADER = "0"
Remove-Item Env:\ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:\ANTHROPIC_AUTH_TOKEN -ErrorAction SilentlyContinue

try {
    `$health = Invoke-RestMethod -Uri "http://127.0.0.1:$RouterPort/health" -TimeoutSec 5
    Write-Host "Router health: `$(`$health.status) pid=`$(`$health.pid) version=`$(`$health.version)"
}
catch {
    throw "claude-any router is not reachable on port $RouterPort. Run launch-claude-any-routed.ps1 first and keep it open."
}

& claude -c
"@
$resumeRoutedContent | Set-Content -Path $resumeRoutedPath -Encoding UTF8

$launchRoutedContent = @"
`$ErrorActionPreference = "Stop"
`$env:CLAUDE_ANY_CONFIG_DIR = "$ConfigDir"
`$env:CLAUDE_ANY_ROUTER_PORT = "$RouterPort"

`$TranscriptPath = Join-Path "$EvidenceDir" "windows-terminal-transcript.txt"
try {
    Start-Transcript -Path `$TranscriptPath -Append | Out-Null
}
catch {
    Write-Warning "Start-Transcript failed: `$(`$_.Exception.Message)"
}

try {
    if (Test-Path "$Root\claude_any.py") {
        `$exe = "python"
        `$arguments = @(
            "$Root\claude_any.py",
            "cli",
            "--ca-provider", "anthropic",
            "--ca-model", "$Model",
            "--ca-provider-option", "route_through_router=true",
            "--ca-log-level", "TRACE"
        )
        & `$exe @arguments
    }
    else {
        `$exe = "claude-any"
        `$arguments = @(
            "--ca-provider", "anthropic",
            "--ca-model", "$Model",
            "--ca-provider-option", "route_through_router=true",
            "--ca-log-level", "TRACE"
        )
        & `$exe @arguments
    }
}
finally {
    try { Stop-Transcript | Out-Null } catch {}
}
"@
$launchRoutedContent | Set-Content -Path $launchRoutedPath -Encoding UTF8

$collectLogsContent = @"
`$ErrorActionPreference = "Continue"
`$Dest = Join-Path "$EvidenceDir" "collected-logs"
New-Item -ItemType Directory -Force -Path `$Dest | Out-Null

`$Paths = @(
    "$ConfigDir",
    "`$env:USERPROFILE\.config\claude-any",
    "`$env:APPDATA\claude-any",
    "`$env:LOCALAPPDATA\claude-any"
) | Where-Object { `$_ -and (Test-Path `$_) } | Select-Object -Unique

foreach (`$Path in `$Paths) {
    `$safe = (`$Path -replace "[:\\\/ ]", "_").Trim("_")
    `$out = Join-Path `$Dest `$safe
    New-Item -ItemType Directory -Force -Path `$out | Out-Null
    foreach (`$name in @("router.log", "requests.jsonl", "responses.jsonl", "context-usage.json", "rate-limit-state.json")) {
        `$src = Join-Path `$Path `$name
        if (Test-Path `$src) {
            Copy-Item `$src (Join-Path `$out `$name) -Force
            Write-Host "Copied `$src"
        }
    }
}

Write-Host "Logs collected under `$Dest"
"@
$collectLogsContent | Set-Content -Path $collectLogsPath -Encoding UTF8

$manifest = Get-Content -Raw -Encoding UTF8 (Join-Path $EvidenceDir "prompt-manifest.json") | ConvertFrom-Json
$rows = @()
foreach ($m in $manifest) {
    $rows += "| $($m.call_index) | $($m.estimated_input_tokens) | pending | pending | pending | |"
}

$checkpointContent = @"
# Interactive Usage Checkpoints

Evidence dir: `$EvidenceDir`
Model: `$Model`
Mode: anthropic routed through claude-any
Router port: `$RouterPort`

Before starting:

- Run /usage in Claude Code and capture the screen.
- Save the screenshot as usage-before.png in this directory.

After each prompt:

- Wait for the assistant answer to fully finish.
- Run /usage.
- Save the screenshot as usage-after-call-NNN.png.
- Fill the table.

| Call | Estimated input tokens | /usage before | /usage after | Delta visible? | Notes |
|---:|---:|---|---|---|---|
$($rows -join "`n")

Final:

- Run /usage one more time.
- Run `.\collect-logs.ps1`.
- Keep windows-terminal-transcript.txt, screenshots, router logs, and summary.json together.
"@
$checkpointContent | Set-Content -Path $checkpointsPath -Encoding UTF8

$stepsContent = @"
# Windows Interactive Claude Usage Probe

This evidence set is prepared for an interactive Windows Claude Code run.

Nothing in this folder has called Anthropic yet. Real quota is consumed only when
you launch Claude Code and paste/submit the generated prompts.

## 1. Launch routed Claude Code

From PowerShell:

    Set-ExecutionPolicy -Scope Process Bypass
    & "$launchRoutedPath"

In the Claude Code session:

1. Confirm the status line shows the expected model/mode.
2. Run /usage.
3. Capture the screen as usage-before.png.

## 2. Send load prompts

In a second PowerShell window, copy each prompt to the clipboard:

    Set-ExecutionPolicy -Scope Process Bypass
    & "$copyPromptPath" -Index 1

Paste into Claude Code and submit. After the answer finishes, run /usage and
save a screenshot. Repeat with -Index 2, -Index 3, and so on.

If the prompt is too large for reliable paste, keep the routed router running
and submit the file directly from PowerShell:

    & "$submitPromptPath" -Index 1

Then return to Claude Code, run /usage, and save the screenshot.

If the original interactive window is no longer attached to the same latest
conversation, reopen it through the same routed environment:

    & "$resumeRoutedPath"

## 3. Collect logs

After the final /usage screenshot:

    & "$collectLogsPath"

## 4. Evidence to keep

- usage-before.png
- usage-after-call-*.png
- windows-terminal-transcript.txt
- summary.json
- prompt-manifest.json
- collected-logs/

## Safety

The generated prompt set targets about $TargetTotalTokens input tokens. This may
consume real Claude/Anthropic quota. Stop after a smaller number of calls if the
usage delta is already clear.
"@
$stepsContent | Set-Content -Path $stepsPath -Encoding UTF8

Write-Host ""
Write-Host "Windows interactive usage probe prepared:"
Write-Host "  Evidence: $EvidenceDir"
Write-Host "  Steps:    $stepsPath"
Write-Host "  Launch:   $launchRoutedPath"
Write-Host "  Copy:     $copyPromptPath"
Write-Host "  Submit:   $submitPromptPath"
Write-Host "  Resume:   $resumeRoutedPath"
Write-Host "  Logs:     $collectLogsPath"
