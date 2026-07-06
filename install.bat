@echo off
setlocal EnableDelayedExpansion

:: Check if NO_COLOR is set or CI is true
set "USE_COLOR=1"
if defined NO_COLOR set "USE_COLOR=0"
if "%CI%"=="true" set "USE_COLOR=0"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$useColor = '%USE_COLOR%' -eq '1'; ^
   $spin = @('⠋','⠙','⠹','⠸','⠼','⠴','⠦','⠧','⠇','⠏'); ^
   function Write-Typewriter($text, $color='White') { ^
     if ($useColor) { ^
       $text.ToCharArray() | ForEach-Object { ^
         Write-Host -NoNewline $_ -ForegroundColor $color; ^
         Start-Sleep -Milliseconds 10 ^
       }; Write-Host ^
     } else { ^
       Write-Host $text ^
     } ^
   }; ^
   Clear-Host; ^
   if ($useColor) { ^
     Write-Host '  ┌────────────────────────────────────────────────────────┐' -ForegroundColor Magenta; ^
     Write-Host '  │   ▲ STEALTH DOWNLOADER — High-Speed Telegram Daemon    │' -ForegroundColor Magenta; ^
     Write-Host '  └────────────────────────────────────────────────────────┘' -ForegroundColor Magenta; ^
   } else { ^
     Write-Host '=================================================='; ^
     Write-Host '      Telegram Downloader Installer (Windows)'; ^
     Write-Host '=================================================='; ^
   }; ^
   Write-Typewriter 'Starting system diagnostics...' 'Cyan'; ^
   Write-Host ''; ^
   Write-Host -NoNewline 'Checking Python environment...'; ^
   Start-Sleep -Milliseconds 300; ^
   $py = Get-Command python -ErrorAction SilentlyContinue; ^
   if (-not $py) { ^
     if ($useColor) { ^
       Write-Host \"`r`e[31m[x]`e[0m Python is not installed or not in PATH.\" -ForegroundColor Red; ^
     } else { ^
       Write-Host \"`r[x] Python is not installed or not in PATH.\"; ^
     } ^
     Write-Typewriter 'Please install Python 3.12+ and try again.' 'Yellow'; ^
     exit 1; ^
   }; ^
   $ver = (python --version 2>&1); ^
   if ($useColor) { ^
     Write-Host \"`r`e[32m[✓]`e[0m Python found: $ver\" -ForegroundColor Green; ^
   } else { ^
     Write-Host \"`r[✓] Python found: $ver\"; ^
   }; ^
   Start-Sleep -Milliseconds 200; ^
   Write-Host ''; ^
   Write-Typewriter 'Resolving dependencies...' 'Cyan'; ^
   if ($useColor) { ^
     $job = Start-Job -ScriptBlock { pip install -r requirements.txt; return $LASTEXITCODE }; ^
     $i = 0; ^
     while ($job.State -eq 'Running') { ^
       $char = $spin[$i]; ^
       Write-Host -NoNewline \"`r`e[36m[$char]`e[0m Installing python packages (telethon, cryptg, rich, dotenv)...\"; ^
       $i = ($i + 1) % $spin.Count; ^
       Start-Sleep -Milliseconds 80; ^
     }; ^
     $exitCode = Receive-Job -Job $job; ^
     Remove-Job -Job $job; ^
     Write-Host -NoNewline \"`r`e[K\"; ^
     if ($exitCode -ne 0) { ^
       Write-Host \"`e[31m[x] Failed to install dependencies via pip.`e[0m\" -ForegroundColor Red; ^
       exit 1; ^
     } ^
     Write-Host \"`e[32m[✓] Dependencies successfully resolved.`e[0m\" -ForegroundColor Green; ^
   } else { ^
     Write-Host 'Installing python packages...'; ^
     pip install -r requirements.txt; ^
     if ($LASTEXITCODE -ne 0) { ^
       Write-Host '[x] Failed to install dependencies.'; ^
       exit 1; ^
     } ^
     Write-Host '[✓] Dependencies resolved.'; ^
   }; ^
   Start-Sleep -Milliseconds 300; ^
   Write-Host ''; ^
   Write-Typewriter 'Launching configuration wizard...' 'Cyan'; ^
   Start-Sleep -Milliseconds 300;"

if %errorlevel% neq 0 (
    echo.
    echo [x] Installer encountered an error.
    pause
    exit /b 1
)

echo.
python configure.py
pause
