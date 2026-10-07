#Requires -Version 4.0
<# Moonring 한글패치 되돌리기 — Moonring.exe.bak 을 원래 자리로 되돌립니다. #>
[CmdletBinding()]
param([string]$GamePath = "")

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = New-Object Text.UTF8Encoding $false } catch {}

$Root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)

function Say($t)  { Write-Host $t }
function Bad($t)  { Write-Host $t -ForegroundColor Red }
function Good($t) { Write-Host $t -ForegroundColor Green }
function Warn($t) { Write-Host $t -ForegroundColor Yellow }

function JoinP([string]$a, [string]$b) {
  if (-not $a) { return $b }
  return ($a.TrimEnd('\', '/') + '\' + $b)
}

function Get-SteamLibraries {
  $libs = New-Object System.Collections.Generic.List[string]
  foreach ($k in @('HKCU:\Software\Valve\Steam',
                   'HKLM:\SOFTWARE\WOW6432Node\Valve\Steam',
                   'HKLM:\SOFTWARE\Valve\Steam')) {
    try {
      $p = Get-ItemProperty -Path $k -ErrorAction Stop
      foreach ($v in @($p.SteamPath, $p.InstallPath)) { if ($v) { $libs.Add(($v -replace '/', '\')) } }
    } catch {}
  }
  $extra = New-Object System.Collections.Generic.List[string]
  foreach ($l in $libs) {
    $vdf = JoinP $l 'steamapps\libraryfolders.vdf'
    $hasVdf = $false
    try { $hasVdf = Test-Path $vdf } catch { }
    if ($hasVdf) {
      $txt = Get-Content $vdf -Raw -ErrorAction SilentlyContinue
      if ($txt) { foreach ($m in [regex]::Matches($txt, '"path"\s*"([^"]+)"')) { $extra.Add(($m.Groups[1].Value -replace '\\\\', '\')) } }
    }
  }
  foreach ($d in @('C:\Program Files (x86)\Steam', 'C:\Program Files\Steam',
                   'D:\Steam', 'D:\SteamLibrary', 'E:\Steam', 'E:\SteamLibrary')) { $extra.Add($d) }
  ($libs + $extra) | Where-Object { $_ } | Select-Object -Unique
}

function Find-Game {
  param([string]$Hint)
  $cands = New-Object System.Collections.Generic.List[string]
  if ($Hint) { $cands.Add($Hint) }
  $cands.Add($Root)
  $cands.Add((Split-Path -Parent $Root))
  try { $cands.Add((Split-Path -Parent (Split-Path -Parent $Root))) } catch {}
  foreach ($lib in (Get-SteamLibraries)) { $cands.Add((JoinP $lib 'steamapps\common\Moonring')) }
  foreach ($c in $cands) {
    if (-not $c) { continue }
    try {
      if ((Split-Path -Leaf $c) -ieq 'Moonring.exe') { $c = Split-Path -Parent $c }
      if (Test-Path (Join-Path $c 'Moonring.exe')) { return (Resolve-Path $c).Path }
    } catch {}
  }
  return $null
}

Say ''
Say '============================================================'
Say '  Moonring 한글패치 되돌리기'
Say '============================================================'
Say ''

$Game = Find-Game $GamePath
while (-not $Game) {
  Warn '[!] Moonring.exe 를 자동으로 찾지 못했습니다.'
  $typed = Read-Host '    Moonring 폴더 경로 (Enter = 취소)'
  if (-not $typed) { Bad '취소했습니다.'; exit 1 }
  $Game = Find-Game ($typed.Trim('"').Trim())
}
Say ('게임 폴더 : ' + $Game)

$Exe = Join-Path $Game 'Moonring.exe'
$Bak = Join-Path $Game 'Moonring.exe.bak'

if (-not (Test-Path $Bak)) {
  Bad '[!] Moonring.exe.bak (원본 백업) 이 없습니다.'
  Say '    스팀에서 Moonring > 속성 > 설치된 파일 > 게임 파일 무결성 확인 을 실행하면'
  Say '    원본 영문판으로 복구됩니다.'
  exit 1
}

if (Get-Process -Name 'Moonring' -ErrorAction SilentlyContinue) {
  Bad '[!] Moonring 이 실행 중입니다. 게임을 완전히 종료한 뒤 다시 실행하세요.'
  exit 1
}

Copy-Item $Bak $Exe -Force
Remove-Item $Bak -Force

$lang = Join-Path $Game 'lang'
if (Test-Path $lang) {
  try { Remove-Item $lang -Recurse -Force } catch { Warn ('[!] lang 폴더를 지우지 못했습니다: ' + $lang) }
}

Say ''
Good '원본 영문판으로 되돌렸습니다.'
Say ''
