#Requires -Version 4.0
<#
  Moonring 한글패치 적용기
  파이썬 없이, 윈도우 기본 PowerShell 만으로 Moonring.exe 안의 파일을 교체합니다.
#>
[CmdletBinding()]
param([string]$GamePath = "", [switch]$Elevated)

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = New-Object Text.UTF8Encoding $false } catch {}

Add-Type -AssemblyName System.IO.Compression | Out-Null
Add-Type -AssemblyName System.IO.Compression.FileSystem | Out-Null

try {
  Add-Type -TypeDefinition @'
using System;
using System.IO;
public class MoonringOffsetStream : Stream {
  private Stream _b; private long _off; private long _len;
  public MoonringOffsetStream(Stream b, long off, long len){ _b=b; _off=off; _len=len; _b.Position=off; }
  public override bool CanRead { get { return true; } }
  public override bool CanSeek { get { return true; } }
  public override bool CanWrite { get { return false; } }
  public override long Length { get { return _len; } }
  public override long Position {
    get { return _b.Position - _off; }
    set { _b.Position = _off + value; }
  }
  public override int Read(byte[] buf, int o, int c) {
    long rem = _len - Position; if (c > rem) c = (int)rem; if (c <= 0) return 0;
    return _b.Read(buf, o, c);
  }
  public override long Seek(long off, SeekOrigin origin) {
    long p;
    if (origin == SeekOrigin.Begin) p = off;
    else if (origin == SeekOrigin.Current) p = Position + off;
    else p = _len + off;
    Position = p; return p;
  }
  public override void SetLength(long v) { throw new NotSupportedException(); }
  public override void Write(byte[] b, int o, int c) { throw new NotSupportedException(); }
  public override void Flush() { }
}
'@
} catch {
  if (-not ($_.Exception.Message -match 'already exists|이미')) { throw }
}

$Root     = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$Payload  = Join-Path $Root 'patch'
$ManPath  = Join-Path $Root 'manifest.txt'

function Say($t)  { Write-Host $t }
function Warn($t) { Write-Host $t -ForegroundColor Yellow }
function Bad($t)  { Write-Host $t -ForegroundColor Red }
function Good($t) { Write-Host $t -ForegroundColor Green }

# ------------------------------------------------------------------ manifest
$Man = @{}
if (Test-Path $ManPath) {
  foreach ($line in (Get-Content $ManPath -Encoding UTF8)) {
    $l = $line -replace "^\uFEFF", ''
    if ($l -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$') { $Man[$Matches[1]] = $Matches[2] }
  }
}

Say ''
Say '============================================================'
Say '  Moonring 한글패치'
if ($Man.patch_version) { Say ('  패치 버전 : ' + $Man.patch_version) }
if ($Man.game_build)    { Say ('  대상 게임 : Moonring ' + $Man.game_build) }
Say '============================================================'
Say ''

if (-not (Test-Path $Payload)) {
  Bad '[!] patch 폴더가 없습니다. 압축을 폴더째로 풀었는지 확인하세요.'
  exit 1
}

# --------------------------------------------------------------- 게임 찾기
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
      foreach ($v in @($p.SteamPath, $p.InstallPath)) {
        if ($v) { $libs.Add(($v -replace '/', '\')) }
      }
    } catch {}
  }
  $extra = New-Object System.Collections.Generic.List[string]
  foreach ($l in $libs) {
    $vdf = JoinP $l 'steamapps\libraryfolders.vdf'
    $hasVdf = $false
    try { $hasVdf = Test-Path $vdf } catch { }
    if ($hasVdf) {
      $txt = Get-Content $vdf -Raw -ErrorAction SilentlyContinue
      if ($txt) {
        foreach ($m in [regex]::Matches($txt, '"path"\s*"([^"]+)"')) {
          $extra.Add(($m.Groups[1].Value -replace '\\\\', '\'))
        }
      }
    }
  }
  foreach ($d in @('C:\Program Files (x86)\Steam', 'C:\Program Files\Steam',
                   'D:\Steam', 'D:\SteamLibrary', 'E:\Steam', 'E:\SteamLibrary')) {
    $extra.Add($d)
  }
  ($libs + $extra) | Where-Object { $_ } | Select-Object -Unique
}

function Find-Game {
  param([string]$Hint)
  $cands = New-Object System.Collections.Generic.List[string]
  if ($Hint) { $cands.Add($Hint) }
  $cands.Add($Root)
  $cands.Add((Split-Path -Parent $Root))
  try { $cands.Add((Split-Path -Parent (Split-Path -Parent $Root))) } catch {}
  foreach ($lib in (Get-SteamLibraries)) {
    $cands.Add((JoinP $lib 'steamapps\common\Moonring'))
  }
  foreach ($c in $cands) {
    if (-not $c) { continue }
    try {
      if ((Split-Path -Leaf $c) -ieq 'Moonring.exe') { $c = Split-Path -Parent $c }
      $exe = Join-Path $c 'Moonring.exe'
      if (Test-Path $exe) { return (Resolve-Path $c).Path }
    } catch {}
  }
  return $null
}

$Game = Find-Game $GamePath
while (-not $Game) {
  Warn '[!] Moonring.exe 를 자동으로 찾지 못했습니다.'
  Say  '    스팀 라이브러리에서 Moonring > 관리 > 로컬 파일 보기 로 폴더를 연 뒤,'
  Say  '    주소창의 경로를 복사해 아래에 붙여넣으세요. (그냥 Enter 치면 취소)'
  $typed = Read-Host '    Moonring 폴더 경로'
  if (-not $typed) { Bad '취소했습니다.'; exit 1 }
  $Game = Find-Game ($typed.Trim('"').Trim())
}
Say ('게임 폴더 : ' + $Game)

$Exe = Join-Path $Game 'Moonring.exe'
$Bak = Join-Path $Game 'Moonring.exe.bak'

# ------------------------------------------------------------- 쓰기 권한 확인
$probe = Join-Path $Game ('.ko_write_test_' + [Guid]::NewGuid().ToString('N') + '.tmp')
try {
  [IO.File]::WriteAllText($probe, 'x')
  Remove-Item $probe -Force
} catch {
  Warn '[!] 게임 폴더에 쓸 권한이 없습니다. 관리자 권한으로 다시 실행합니다...'
  $psArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"",
              '-GamePath', "`"$Game`"", '-Elevated')
  Start-Process -FilePath 'powershell.exe' -ArgumentList $psArgs -Verb RunAs
  exit 0
}

# ---------------------------------------------------------------- 게임 실행중?
if (Get-Process -Name 'Moonring' -ErrorAction SilentlyContinue) {
  Bad '[!] Moonring 이 실행 중입니다. 게임을 완전히 종료한 뒤 다시 실행하세요.'
  exit 1
}

# 원본으로 삼을 파일 (백업이 있으면 그것이 진짜 원본)
$Src = if (Test-Path $Bak) { $Bak } else { $Exe }

# ------------------------------------------------------------------ 버전 확인
if ($Man.source_sha256) {
  Say '원본 파일 확인 중...'
  $h = ''
  try { $h = (Get-FileHash $Src -Algorithm SHA256).Hash.ToLower() } catch { }
  if ($h -and $h -ne $Man.source_sha256.ToLower()) {
    Warn ''
    Warn '[!] 이 패치가 만들어진 게임 버전과 원본 파일이 다릅니다.'
    Warn ('    패치 기준 : ' + $Man.source_sha256)
    Warn ('    현재 파일 : ' + $h)
    Warn '    게임이 업데이트된 것 같습니다. 그대로 적용하면 게임이 켜지지 않거나'
    Warn '    일부 내용이 원래대로 돌아갈 수 있습니다.'
    $go = Read-Host '    그래도 적용할까요? (y/N)'
    if ($go -notmatch '^[yY]') { Bad '취소했습니다.'; exit 1 }
  } elseif ($h) {
    Say '원본 파일 확인 : 일치'
  }
}

# -------------------------------------------------------------------- 백업
if (Test-Path $Bak) {
  Say '원본 백업 확인 : Moonring.exe.bak (이미 있음)'
} else {
  Say '원본 백업 생성 : Moonring.exe.bak'
  Copy-Item $Exe $Bak -Force
}
$Src = $Bak

# ------------------------------------------------------- exe 안의 zip 구조 파악
function Get-ZipLayout([string]$path) {
  $fs = [IO.File]::OpenRead($path)
  try {
    $len = $fs.Length
    $tailLen = [int][Math]::Min(70000, $len)
    $fs.Position = $len - $tailLen
    $tail = New-Object byte[] ([int]$tailLen)
    $read = 0
    while ($read -lt $tailLen) {
      $n = $fs.Read($tail, $read, $tailLen - $read)
      if ($n -le 0) { break }
      $read += $n
    }
    $idx = -1
    for ($i = $tailLen - 22; $i -ge 0; $i--) {
      if ($tail[$i] -eq 0x50 -and $tail[$i+1] -eq 0x4B -and $tail[$i+2] -eq 0x05 -and $tail[$i+3] -eq 0x06) { $idx = $i; break }
    }
    if ($idx -lt 0) { throw 'exe 안에서 zip 끝 표식(EOCD)을 찾지 못했습니다.' }
    $cdSize   = [int64][BitConverter]::ToUInt32($tail, $idx + 12)
    $cdRecOff = [int64][BitConverter]::ToUInt32($tail, $idx + 16)
    $eocdAbs  = $len - $tailLen + $idx
    $cdAbs    = $eocdAbs - $cdSize
    $delta    = $cdAbs - $cdRecOff

    # 중앙 디렉터리를 훑어 가장 앞선 로컬 헤더 위치를 찾는다
    $fs.Position = $cdAbs
    $cd = New-Object byte[] ([int]$cdSize)
    $read = 0
    while ($read -lt $cdSize) {
      $n = $fs.Read($cd, $read, [int]($cdSize - $read))
      if ($n -le 0) { break }
      $read += $n
    }
    $minOff = [int64]::MaxValue
    $p = 0
    while ($p + 46 -le $cd.Length) {
      if (-not ($cd[$p] -eq 0x50 -and $cd[$p+1] -eq 0x4B -and $cd[$p+2] -eq 0x01 -and $cd[$p+3] -eq 0x02)) { break }
      $o = [int64][BitConverter]::ToUInt32($cd, $p + 42)
      if ($o -lt $minOff) { $minOff = $o }
      $fnL = [int][BitConverter]::ToUInt16($cd, $p + 28)
      $exL = [int][BitConverter]::ToUInt16($cd, $p + 30)
      $cmL = [int][BitConverter]::ToUInt16($cd, $p + 32)
      $p += 46 + $fnL + $exL + $cmL
    }
    if ($minOff -eq [int64]::MaxValue) { $minOff = 0 }
    return [pscustomobject]@{ Delta = $delta; StubLength = ($minOff + $delta) }
  } finally { $fs.Dispose() }
}

$layout = Get-ZipLayout $Src
if ($layout.StubLength -le 0) { throw 'exe 앞부분(실행 스텁) 크기를 계산하지 못했습니다.' }
Say ('exe 구조 확인 : 스텁 {0:N0} 바이트' -f $layout.StubLength)

# ------------------------------------------------------------- 교체 파일 목록
$replace = @{}
$payloadFull = (Resolve-Path $Payload).Path
foreach ($f in (Get-ChildItem -Path $payloadFull -Recurse -File)) {
  $rel = $f.FullName.Substring($payloadFull.Length).TrimStart('\', '/') -replace '\\', '/'
  $replace[$rel] = $f.FullName
}
Say ('교체할 파일 : {0}개' -f $replace.Count)

# ------------------------------------------------------------------- 재패킹
$Tmp = $Exe + '.new'
if (Test-Path $Tmp) { Remove-Item $Tmp -Force }

Say '패치 적용 중... (30초~2분)'
$copied = 0
$outFs = [IO.File]::Create($Tmp)
try {
  # 1) 실행 스텁 복사
  $in = [IO.File]::OpenRead($Src)
  try {
    $buf  = New-Object byte[] 1048576
    $left = [int64]$layout.StubLength
    while ($left -gt 0) {
      $want = [int][Math]::Min([int64]$buf.Length, $left)
      $n = $in.Read($buf, 0, $want)
      if ($n -le 0) { throw '실행 스텁 복사에 실패했습니다.' }
      $outFs.Write($buf, 0, $n)
      $left -= $n
    }
  } finally { $in.Dispose() }

  # 2) zip 다시 쓰기 (교체 대상은 건너뛰고 원본 항목 복사)
  $srcIn = [IO.File]::OpenRead($Src)
  $zipIn = $null
  if ($layout.Delta -gt 0) {
    $zipIn = New-Object MoonringOffsetStream -ArgumentList $srcIn, ([int64]$layout.Delta), ($srcIn.Length - [int64]$layout.Delta)
  } else {
    $zipIn = $srcIn
  }
  $srcZip = New-Object IO.Compression.ZipArchive -ArgumentList $zipIn, ([IO.Compression.ZipArchiveMode]::Read)
  $dstZip = New-Object IO.Compression.ZipArchive -ArgumentList $outFs, ([IO.Compression.ZipArchiveMode]::Create), $true
  try {
    foreach ($e in $srcZip.Entries) {
      if ($replace.ContainsKey($e.FullName)) { continue }
      $ne = $dstZip.CreateEntry($e.FullName, [IO.Compression.CompressionLevel]::NoCompression)
      $a = $e.Open(); $b = $ne.Open()
      try { $a.CopyTo($b, 1048576) } finally { $b.Dispose(); $a.Dispose() }
      $copied++
    }
    foreach ($rel in ($replace.Keys | Sort-Object)) {
      $ne = $dstZip.CreateEntry($rel, [IO.Compression.CompressionLevel]::NoCompression)
      $b = $ne.Open()
      $fi = [IO.File]::OpenRead($replace[$rel])
      try { $fi.CopyTo($b, 1048576) } finally { $fi.Dispose(); $b.Dispose() }
      $copied++
    }
  } finally {
    $dstZip.Dispose(); $srcZip.Dispose()
    if ($layout.Delta -gt 0) { $zipIn.Dispose() }
    $srcIn.Dispose()
  }
} catch {
  $outFs.Dispose()
  if (Test-Path $Tmp) { Remove-Item $Tmp -Force }
  Bad ('[!] 패치 중 오류: ' + $_.Exception.Message)
  Bad '    원본 파일은 그대로입니다.'
  exit 1
}
$outFs.Dispose()

# -------------------------------------------------------------------- 검증
Say '결과 검사 중...'
try {
  $vl = Get-ZipLayout $Tmp
  $vin = [IO.File]::OpenRead($Tmp)
  $vs  = if ($vl.Delta -gt 0) { New-Object MoonringOffsetStream -ArgumentList $vin, ([int64]$vl.Delta), ($vin.Length - [int64]$vl.Delta) } else { $vin }
  $vz  = New-Object IO.Compression.ZipArchive -ArgumentList $vs, ([IO.Compression.ZipArchiveMode]::Read)
  $count = $vz.Entries.Count
  $need  = @('loc.lua', 'main.lua', 'lang/ko.csv', 'assets/ko/main_pixel.fnt')
  $missing = @()
  foreach ($n in $need) { if (-not $vz.GetEntry($n)) { $missing += $n } }
  $vz.Dispose(); if ($vl.Delta -gt 0) { $vs.Dispose() }; $vin.Dispose()
  if ($missing.Count -gt 0) { throw ('빠진 파일: ' + ($missing -join ', ')) }
  if ($count -lt $copied) { throw ('항목 수 이상 ({0} < {1})' -f $count, $copied) }
  Say ('결과 검사 : 항목 {0}개 정상' -f $count)
} catch {
  if (Test-Path $Tmp) { Remove-Item $Tmp -Force }
  Bad ('[!] 만들어진 파일이 이상합니다: ' + $_.Exception.Message)
  Bad '    적용을 취소했습니다. 원본 파일은 그대로입니다.'
  exit 1
}

# -------------------------------------------------------------------- 교체
Move-Item -Path $Tmp -Destination $Exe -Force

# ------------------------------------------------- 번역 파일을 게임 폴더에도
$koSrc = Join-Path (Join-Path $Payload 'lang') 'ko.csv'
if (Test-Path $koSrc) {
  $langDir = Join-Path $Game 'lang'
  if (-not (Test-Path $langDir)) { New-Item -ItemType Directory -Path $langDir | Out-Null }
  Copy-Item $koSrc (Join-Path $langDir 'ko.csv') -Force
}

Say ''
Good '완료! 게임을 실행하면 한글로 나옵니다.'
Say ''
Say '  · 번역을 고치고 싶다면 : Moonring\lang\ko.csv 를 엑셀로 열어 ko 칸만 수정'
Say '  · 원래대로 되돌리려면 : 되돌리기.bat 실행'
Say ''
if ($Elevated) { Read-Host '엔터를 누르면 창이 닫힙니다' | Out-Null }
