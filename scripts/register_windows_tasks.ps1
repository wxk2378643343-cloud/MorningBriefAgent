$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pythonPath = (Get-Command python -ErrorAction Stop).Source
$pythonwPath = Join-Path (Split-Path -Parent $pythonPath) "pythonw.exe"
if (-not (Test-Path -LiteralPath $pythonwPath -PathType Leaf)) {
    throw "pythonw.exe was not found next to the active interpreter: $pythonPath"
}
$currentUser = "$env:USERDOMAIN\$env:USERNAME"

$principal = New-ScheduledTaskPrincipal `
    -UserId $currentUser `
    -LogonType Interactive `
    -RunLevel Limited

$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable

function Register-DailyWorkflow {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Arguments,
        [Parameter(Mandatory = $true)]
        [string]$At
    )

    $action = New-ScheduledTaskAction `
        -Execute $pythonPath `
        -Argument $Arguments `
        -WorkingDirectory $projectRoot
    $trigger = New-ScheduledTaskTrigger `
        -Daily `
        -At ([datetime]::ParseExact($At, "HH:mm", $null))
    $task = New-ScheduledTask `
        -Action $action `
        -Trigger $trigger `
        -Principal $principal `
        -Settings $settings `
        -Description "MorningBriefAgent workflow: $Arguments"
    Register-ScheduledTask -TaskName $Name -InputObject $task -Force | Out-Null
}

function Register-LogonWorkflow {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Arguments
    )

    $action = New-ScheduledTaskAction `
        -Execute $pythonwPath `
        -Argument $Arguments `
        -WorkingDirectory $projectRoot
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $botSettings = New-ScheduledTaskSettingsSet `
        -MultipleInstances IgnoreNew `
        -StartWhenAvailable `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 1)
    $task = New-ScheduledTask `
        -Action $action `
        -Trigger $trigger `
        -Principal $principal `
        -Settings $botSettings `
        -Description "MorningBriefAgent logon workflow: $Arguments"
    Register-ScheduledTask -TaskName $Name -InputObject $task -Force | Out-Null
}

function Register-ReconcileWorkflow {
    $action = New-ScheduledTaskAction `
        -Execute $pythonwPath `
        -Argument "main.py reconcile" `
        -WorkingDirectory $projectRoot
    $trigger = New-ScheduledTaskTrigger `
        -Once `
        -At (Get-Date).AddMinutes(1) `
        -RepetitionInterval (New-TimeSpan -Minutes 30) `
        -RepetitionDuration (New-TimeSpan -Days 3650)
    $reconcileSettings = New-ScheduledTaskSettingsSet `
        -MultipleInstances IgnoreNew `
        -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
    $task = New-ScheduledTask `
        -Action $action `
        -Trigger $trigger `
        -Principal $principal `
        -Settings $reconcileSettings `
        -Description "Replay due MorningBriefAgent Outbox records every 30 minutes without a console window."
    Register-ScheduledTask -TaskName "MorningBriefAgentReconcile" -InputObject $task -Force | Out-Null
}

Register-DailyWorkflow -Name "DailyTodoMorningPush" -Arguments "main.py todo-morning" -At "06:00"
Register-DailyWorkflow -Name "KaoyanMorningBrief" -Arguments "main.py brief" -At "06:30"
Register-DailyWorkflow -Name "MorningChatDigest" -Arguments "main.py chat" -At "07:00"
Register-DailyWorkflow -Name "MorningGlobalNews" -Arguments "main.py news" -At "07:45"
Register-DailyWorkflow -Name "FundDailyAdvisor1400" -Arguments "main.py fund" -At "14:00"
Register-DailyWorkflow -Name "DailyTodoEveningReview" -Arguments "main.py todo-evening" -At "23:00"
Register-LogonWorkflow -Name "MorningBriefAgentBot" -Arguments "-m server.feishu_bot_server"
Register-ReconcileWorkflow

Write-Host "Registered MorningBriefAgent Windows tasks from $projectRoot"
Get-ScheduledTask |
    Where-Object { $_.TaskName -in @(
        "DailyTodoMorningPush",
        "KaoyanMorningBrief",
        "MorningChatDigest",
        "MorningGlobalNews",
        "FundDailyAdvisor1400",
        "DailyTodoEveningReview",
        "MorningBriefAgentBot",
        "MorningBriefAgentReconcile"
    ) } |
    Select-Object TaskName, State
