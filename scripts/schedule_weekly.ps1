<#
.SYNOPSIS
    Manages the Windows Scheduled Task for Groww Reviews Weekly Pulse Pipeline.

.DESCRIPTION
    Creates, queries, triggers, or unregisters the weekly scheduled task in Windows Task Scheduler.
    Runs every Monday at 08:00 AM using the project's virtual environment python executable.

.PARAMETER Action
    The action to perform: 'Register', 'Unregister', 'Status', or 'RunNow'. Default: 'Register'.

.PARAMETER TaskName
    Name of the scheduled task. Default: 'GrowwReviewsPulse'.

.PARAMETER At
    Time of day to run (e.g. '08:00AM'). Default: '08:00AM'.

.PARAMETER DayOfWeek
    Day of week to run. Default: 'Monday'.

.EXAMPLE
    .\scripts\schedule_weekly.ps1 -Action Register
    .\scripts\schedule_weekly.ps1 -Action Status
    .\scripts\schedule_weekly.ps1 -Action RunNow
    .\scripts\schedule_weekly.ps1 -Action Unregister
#>

[CmdletBinding()]
param(
    [ValidateSet("Register", "Unregister", "Status", "RunNow")]
    [string]$Action = "Register",

    [string]$TaskName = "GrowwReviewsPulse",
    [string]$At = "08:00AM",
    [string]$DayOfWeek = "Monday"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "Groww Reviews Weekly Pulse - Windows Task Scheduler Helper" -ForegroundColor Cyan
Write-Host "Project Root : $ProjectRoot" -ForegroundColor Gray
Write-Host "Python Exec  : $VenvPython" -ForegroundColor Gray
Write-Host "Action       : $Action" -ForegroundColor Gray
Write-Host "==================================================================" -ForegroundColor Cyan

# Verify virtual environment Python
if (-not (Test-Path $VenvPython)) {
    Write-Warning "Virtual environment python was not found at $VenvPython."
    Write-Host "Falling back to system 'python.exe'." -ForegroundColor Yellow
    $ExecPath = "python.exe"
} else {
    $ExecPath = $VenvPython
}

switch ($Action) {
    "Register" {
        Write-Host "Registering scheduled task '$TaskName' to run every $DayOfWeek at $At..." -ForegroundColor Green
        
        $taskAction = New-ScheduledTaskAction `
            -Execute $ExecPath `
            -Argument "src\orchestrate.py" `
            -WorkingDirectory $ProjectRoot

        $taskTrigger = New-ScheduledTaskTrigger `
            -Weekly `
            -DaysOfWeek $DayOfWeek `
            -At $At

        $taskSettings = New-ScheduledTaskSettingsSet `
            -AllowStartIfOnBatteries `
            -DontStopIfGoingOnBatteries `
            -StartWhenAvailable `
            -ExecutionTimeLimit (New-TimeSpan -Hours 1)

        # Unregister existing task if present to update cleanly
        $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($existing) {
            Write-Host "Updating existing scheduled task '$TaskName'..." -ForegroundColor Yellow
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        }

        Register-ScheduledTask `
            -TaskName $TaskName `
            -Action $taskAction `
            -Trigger $taskTrigger `
            -Settings $taskSettings `
            -Description "Weekly pulse aggregation for Groww Play Store reviews, LLM clustering, and Google Workspace MCP delivery."

        Write-Host "[OK] Task '$TaskName' successfully registered in Windows Task Scheduler!" -ForegroundColor Green
        Get-ScheduledTask -TaskName $TaskName | Format-Table -Property TaskName, State
    }

    "Status" {
        $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($task) {
            Write-Host "Task '$TaskName' is currently registered." -ForegroundColor Green
            $info = Get-ScheduledTaskInfo -TaskName $TaskName
            [PSCustomObject]@{
                TaskName        = $task.TaskName
                State           = $task.State
                LastRunTime     = $info.LastRunTime
                LastTaskResult  = $info.LastTaskResult
                NextRunTime     = $info.NextRunTime
                NumberOfMissedRuns = $info.NumberOfMissedRuns
            } | Format-List
        } else {
            Write-Warning "Task '$TaskName' is NOT registered."
        }
    }

    "RunNow" {
        $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if (-not $task) {
            Write-Error "Task '$TaskName' is not registered. Run with -Action Register first."
        }
        Write-Host "Triggering task '$TaskName' immediately..." -ForegroundColor Green
        Start-ScheduledTask -TaskName $TaskName
        Start-Sleep -Seconds 2
        Get-ScheduledTask -TaskName $TaskName | Format-Table -Property TaskName, State
    }

    "Unregister" {
        $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($task) {
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
            Write-Host "[OK] Task '$TaskName' successfully unregistered." -ForegroundColor Green
        } else {
            Write-Host "Task '$TaskName' is not registered. Nothing to remove." -ForegroundColor Gray
        }
    }
}
