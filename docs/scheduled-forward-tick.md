# Scheduling forward-test ticks on Windows

The forward testing tab ticks runs manually when you click "Refresh Now" or "Tick all active runs". For continuous operation — so forward equity curves keep updating even when you're not looking at the dashboard — schedule the standalone tick script to run automatically every weekday after market close.

This doc walks through Windows Task Scheduler setup. The script itself (`scripts/forward_tick.py`) is just a thin wrapper around `services.forward_service.tick_all_active()`; nothing in the dashboard needs to be running for it to work.

## Prerequisites

- Project synced to `C:\Users\gangar\algo-dashboard` (or update paths below for your install)
- venv at `C:\Users\gangar\venvs\algo-dashboard\` (or wherever your `python -m venv` lives)
- At least one active forward run created via the UI

## One-time setup: register the scheduled task

Open PowerShell (does not need admin) and paste this as one block:

```powershell
$action = New-ScheduledTaskAction `
    -Execute "C:\Users\gangar\venvs\algo-dashboard\Scripts\python.exe" `
    -Argument "C:\Users\gangar\algo-dashboard\scripts\forward_tick.py" `
    -WorkingDirectory "C:\Users\gangar\algo-dashboard"

$trigger = New-ScheduledTaskTrigger -Daily -At 4:00pm

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -RunOnlyIfNetworkAvailable

Register-ScheduledTask `
    -TaskName "AlgoForwardTick" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Daily forward-test tick for algo dashboard"
```

What each flag does:
- `-StartWhenAvailable` — if the laptop is asleep at 4 PM, run as soon as it wakes
- `-DontStopOnIdleEnd` — don't kill the tick if the user becomes active mid-run
- `-RunOnlyIfNetworkAvailable` — skip cleanly if you're offline (yfinance would fail anyway)

## Verify the task is registered

```powershell
Get-ScheduledTask -TaskName "AlgoForwardTick"
```

You should see `State: Ready`. After the first 4 PM trigger, it changes to `LastRunTime` showing the date.

## Run it manually (without waiting for 4 PM)

For a confidence test that everything's wired up:

```powershell
Start-ScheduledTask -TaskName "AlgoForwardTick"
```

Then a few seconds later, check the result:

```powershell
Get-ScheduledTaskInfo -TaskName "AlgoForwardTick" |
    Select-Object LastRunTime, LastTaskResult, NextRunTime
```

`LastTaskResult` of `0` means success. Any nonzero value means the script returned an error code or crashed.

## View what the script printed

Task Scheduler captures stdout/stderr only if you point `-Execute` at `cmd.exe /c ... > logfile.log`. To make logging easier without that complication, re-register the task with a logged version:

```powershell
# Unregister the simple version first
Unregister-ScheduledTask -TaskName "AlgoForwardTick" -Confirm:$false

# Re-register with logging
$logDir = "C:\Users\gangar\algo-dashboard\logs"
New-Item -Path $logDir -ItemType Directory -Force | Out-Null

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument ("-NoProfile -Command `"" +
               "& 'C:\Users\gangar\venvs\algo-dashboard\Scripts\python.exe' " +
               "'C:\Users\gangar\algo-dashboard\scripts\forward_tick.py' " +
               "*> 'C:\Users\gangar\algo-dashboard\logs\forward_tick.log'`"") `
    -WorkingDirectory "C:\Users\gangar\algo-dashboard"

$trigger = New-ScheduledTaskTrigger -Daily -At 4:00pm
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -RunOnlyIfNetworkAvailable

Register-ScheduledTask `
    -TaskName "AlgoForwardTick" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Daily forward-test tick for algo dashboard (with logging)"
```

After a run, `logs\forward_tick.log` contains output like:

```
[2026-06-03 16:00:02] forward_tick: starting
  run #1: updated  bars=1  last=2026-06-03
  run #2: no_new_bars  last=2026-06-03
[2026-06-03 16:00:04] forward_tick: done  updated=1  no_new_bars=1  error=0  skipped=0
```

## Verifying it ticked from inside the dashboard

After a scheduled run:

1. Open the Streamlit dashboard
2. Forward Testing tab
3. Select any forward run
4. The "Last processed" date should be today's date

Errors (e.g., yfinance returned no data) get stored on `forward_runs.error_msg` and shown in the detail view.

## Update / change schedule

To change the run time (e.g., to 4:30 PM):

```powershell
$task = Get-ScheduledTask -TaskName "AlgoForwardTick"
$task.Triggers[0].StartBoundary = (Get-Date -Hour 16 -Minute 30 -Second 0).ToString("yyyy-MM-ddTHH:mm:ss")
Set-ScheduledTask -InputObject $task
```

To switch to weekdays only:

```powershell
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 4:00pm
Set-ScheduledTask -TaskName "AlgoForwardTick" -Trigger $trigger
```

## Unregister (uninstall the schedule)

```powershell
Unregister-ScheduledTask -TaskName "AlgoForwardTick" -Confirm:$false
```

The script itself stays on disk; you can still run it manually with:

```powershell
algo
python scripts\forward_tick.py
```

## When the task doesn't fire

| Symptom | Likely cause | Fix |
|---|---|---|
| `LastTaskResult` is `0` but logs show errors | Script ran but a specific run failed | Check `forward_runs.error_msg` in the DB and the log file |
| `LastTaskResult` is nonzero | Python interpreter or script path is wrong | Re-check `-Execute` and `-Argument` paths match your venv + project |
| Task is `Disabled` | Got disabled manually or by group policy | `Enable-ScheduledTask -TaskName "AlgoForwardTick"` |
| Never runs because laptop is closed at 4 PM | Power settings | Already handled by `-StartWhenAvailable` (runs when the laptop wakes) |
| Runs but yfinance fails | Network blocked or market data not yet published | Errors are logged; harmless — next day's tick picks up |

## Notes on timing

- **Indian market closes 3:30 PM IST.** yfinance usually has the close available within 15-30 minutes after that. 4 PM IST gives a safe buffer.
- **Holidays / weekends:** yfinance returns no data for non-trading days. The tick logs `no_new_bars` and exits cleanly. No special handling needed.
- **Multiple machines:** if you sync this project across multiple Windows machines and each one has the scheduled task, you'll get duplicate ticks. Since the tick is idempotent (replaces existing data), this doesn't cause incorrect results — just wasted yfinance calls. Recommend keeping the task on one machine only.
- **Daylight savings:** Windows Task Scheduler handles DST automatically; the task continues to fire at "4 PM local time" through transitions.
