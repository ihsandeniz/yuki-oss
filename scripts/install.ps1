# Yuki — Windows kaynak kurulumu (install.sh eşi; indir, oku, çalıştır — iex/boru yok).
#
#   Invoke-WebRequest -OutFile install.ps1 https://github.com/ihsandeniz/yuki-oss/releases/download/<sürüm>/install.ps1
#   notepad install.ps1
#   powershell -ExecutionPolicy Bypass -File install.ps1 -Kaynak yuki-oss-kaynak.tar.gz
#   ya da klondan:  powershell -ExecutionPolicy Bypass -File scripts\install.ps1
#
# Ne yapar: kaynağı (bu klon ya da -Kaynak <tar.gz>) %LOCALAPPDATA%\Yuki altına kopyalar, orada
# Python 3.12+ ile venv kurar (~1.3 GB paket), %LOCALAPPDATA%\Yuki\yuki.cmd başlatıcısını ve
# Başlat menüsü kısayolunu yazar. Yönetici izni istemez, sistem dosyasına dokunmaz.
# Hazır paket (Python gerektirmeyen) isteyen Yuki-Setup-<sürüm>.exe'yi kullanır; bu betik
# kaynak kurulumu içindir.
#
# Seçenekler:  -Onek <dizin>   kurulum yeri (varsayılan %LOCALAPPDATA%\Yuki)
#              -Kaynak <dosya> kaynak tar.gz (varsayılan: betiğin bulunduğu klon)
#              -Menusuz        Başlat menüsü kısayolu yazma
#              -Kaldir         kurulumu ve kısayolu sil (kullanıcı verisi ~\.yuki kalır)
# Çıkış: 0 tamam · 1 kurulum hatası · 2 kullanım/ön koşul hatası
[CmdletBinding()]
param(
  [string]$Onek = "",
  [string]$Kaynak = "",
  [switch]$Menusuz,
  [switch]$Kaldir
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

function Dur([int]$kod, [string]$msj) { [Console]::Error.WriteLine($msj); exit $kod }

$ev = [Environment]::GetFolderPath('UserProfile')
$yerel = $env:LOCALAPPDATA
if (-not $yerel) { $yerel = Join-Path $ev '.local/share' }   # Windows dışı (yalnız sınav)
if (-not $Onek) { $Onek = Join-Path $yerel 'Yuki' }

# Güvenlik kapısı: önek boş, sürücü kökü, kullanıcı klasörü ya da LOCALAPPDATA'nın kendisi olamaz
# (Remove-Item -Recurse burada koşar).
$tam = [IO.Path]::GetFullPath($Onek).TrimEnd('\', '/')
$yasak = @($ev, $yerel) | Where-Object { $_ } | ForEach-Object { [IO.Path]::GetFullPath($_).TrimEnd('\', '/') }
$kok = [IO.Path]::GetPathRoot([IO.Path]::GetFullPath($Onek)).TrimEnd('\', '/')
if (-not $tam -or $tam -eq $kok -or ($yasak -contains $tam)) { Dur 2 "tehlikeli onek: $Onek" }

$baslatici = Join-Path $Onek 'yuki.cmd'
$programlar = [Environment]::GetFolderPath('Programs')   # Windows dışında boş döner
$menu = if ($programlar) { Join-Path $programlar 'Yuki.lnk' } else { $null }

if ($Kaldir) {
  if (Test-Path -LiteralPath $Onek) { Remove-Item -LiteralPath $Onek -Recurse -Force }
  if ($menu -and (Test-Path -LiteralPath $menu)) { Remove-Item -LiteralPath $menu -Force }
  Write-Host "Yuki kaldirildi (kullanici verisi ~\.yuki duruyor)"; exit 0
}

if ($Kaynak -and -not (Test-Path -LiteralPath $Kaynak)) { Dur 2 "kaynak yok: $Kaynak" }

# Python 3.12+ bul: py başlatıcısı (python.org kurulumu) önce, sonra PATH'teki python.
$py = $null
$adaylar = @(@('py', '-3.14'), @('py', '-3.13'), @('py', '-3.12'), @('python'), @('python3'))
foreach ($a in $adaylar) {
  if (-not (Get-Command $a[0] -ErrorAction SilentlyContinue)) { continue }
  $arg = @($a | Select-Object -Skip 1) + @('-c', 'import sys,venv,ensurepip; sys.exit(sys.version_info < (3,12))')
  & $a[0] @arg 2>$null | Out-Null
  if ($LASTEXITCODE -eq 0) { $py = $a; break }
}
if (-not $py) { Dur 2 "Python 3.12 ya da yenisi gerekli: https://www.python.org/downloads/ (ya da Yuki-Setup.exe kullanin)" }

# Kaynağı yerleştir (yarım kurulum geçici klasörde kalır, başarıda yer değiştirir).
$yeni = "$Onek.yeni.$PID"
try {
  New-Item -ItemType Directory -Force -Path $yeni | Out-Null
  if ($Kaynak) {
    tar -xzf $Kaynak -C $yeni --strip-components=1
    if ($LASTEXITCODE -ne 0) { throw "tar acilamadi: $Kaynak" }
  } else {
    $klon = Split-Path -Parent $PSScriptRoot
    if ((Get-Command git -ErrorAction SilentlyContinue) -and (Test-Path (Join-Path $klon '.git'))) {
      $arsiv = "$yeni.tar"
      git -C $klon archive --format=tar -o $arsiv HEAD
      tar -xf $arsiv -C $yeni; Remove-Item -LiteralPath $arsiv -Force
    } else {
      Copy-Item -Path (Join-Path $klon '*') -Destination $yeni -Recurse -Force
    }
  }
  if (-not (Test-Path (Join-Path $yeni 'backend/requirements.txt'))) { throw "kaynakta backend/requirements.txt yok" }

  Write-Host "-> paketler kuruluyor (~1.3 GB, birkac dakika)..."
  $venv = Join-Path $yeni 'backend/venv'
  & $py[0] @($py | Select-Object -Skip 1) -m venv $venv
  if ($LASTEXITCODE -ne 0) { throw "venv kurulamadi" }
  $vpy = Join-Path $venv 'Scripts/python.exe'
  if (-not (Test-Path $vpy)) { $vpy = Join-Path $venv 'bin/python' }
  & $vpy -m pip install --disable-pip-version-check -q -r (Join-Path $yeni 'backend/requirements.txt')
  if ($LASTEXITCODE -ne 0) { throw "pip kurulumu basarisiz" }

  if (Test-Path -LiteralPath $Onek) { Remove-Item -LiteralPath $Onek -Recurse -Force }
  Move-Item -LiteralPath $yeni -Destination $Onek
} catch {
  if (Test-Path -LiteralPath $yeni) { Remove-Item -LiteralPath $yeni -Recurse -Force }
  Dur 1 "kurulum hatasi: $($_.Exception.Message)"
}

# Başlatıcı: yuki.cmd [--no-ui]. Port: YUKI_PORT (varsayılan 8001).
@"
@echo off
rem Yuki baslaticisi (install.ps1 yazdi). Port: YUKI_PORT (varsayilan 8001).
cd /d "$Onek\backend"
if not defined MEMORY_BACKEND set MEMORY_BACKEND=sqlite
if not defined YUKI_PORT set YUKI_PORT=8001
if /i not "%~1"=="--no-ui" start "" /b powershell -NoProfile -WindowStyle Hidden -Command "for(`$i=0;`$i -lt 60;`$i++){try{Invoke-WebRequest -UseBasicParsing http://127.0.0.1:%YUKI_PORT%/health ^| Out-Null; Start-Process http://127.0.0.1:%YUKI_PORT%/ui; break}catch{Start-Sleep 1}}"
venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port %YUKI_PORT%
"@ | Set-Content -LiteralPath $baslatici -Encoding ASCII

if (-not $Menusuz -and $menu) {
  $k = (New-Object -ComObject WScript.Shell).CreateShortcut($menu)
  $k.TargetPath = $baslatici; $k.WorkingDirectory = $Onek; $k.Save()
}

Write-Host "Yuki kuruldu: $Onek"
Write-Host "  Baslat: $baslatici   (yalniz motor: --no-ui) -> http://127.0.0.1:8001/ui"
exit 0
