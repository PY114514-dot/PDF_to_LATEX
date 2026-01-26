# Tesseract OCR Auto-Install Script for Windows
# UTF-8 encoding

Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "  Tesseract OCR Auto-Install Script" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host ""

$tesseractUrl = "https://digi.bib.uni-mannheim.de/tesseract/tesseract-ocr-w64-setup-5.3.3.20231005.exe"
$installerPath = "$env:TEMP\tesseract-installer.exe"
$installDir = "C:\Program Files\Tesseract-OCR"

Write-Host "Step 1/3: Downloading Tesseract OCR 5.3.3..." -ForegroundColor Yellow

try {
    $webClient = New-Object System.Net.WebClient
    $webClient.DownloadFile($tesseractUrl, $installerPath)
    Write-Host "Download completed!" -ForegroundColor Green
} catch {
    Write-Host "Download failed: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please download and install manually:" -ForegroundColor Yellow
    Write-Host "1. Visit: https://github.com/UB-Mannheim/tesseract/wiki"
    Write-Host "2. Download tesseract-ocr-w64-setup.exe"
    Write-Host "3. Run installer and install to default location"
    Write-Host "4. Make sure to select 'Chinese (Simplified)' language pack"
    exit 1
}

Write-Host ""
Write-Host "Step 2/3: Installing Tesseract OCR..." -ForegroundColor Yellow
Write-Host "Install location: $installDir"
Write-Host "Note: Chinese language pack will be included" -ForegroundColor Magenta

try {
    $process = Start-Process -FilePath $installerPath -ArgumentList "/S" -Wait -PassThru
    
    if ($process.ExitCode -eq 0) {
        Write-Host "Tesseract installed successfully!" -ForegroundColor Green
    } else {
        Write-Host "Installation may have failed, exit code: $($process.ExitCode)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "Installation failed: $_" -ForegroundColor Red
    exit 1
}

Remove-Item $installerPath -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Step 3/3: Configuring environment..." -ForegroundColor Yellow

$tesseractExe = Join-Path $installDir "tesseract.exe"
if (Test-Path $tesseractExe) {
    Write-Host "Tesseract executable found: $tesseractExe" -ForegroundColor Green
    
    $currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($currentPath -notlike "*$installDir*") {
        Write-Host "Adding Tesseract to User PATH..." -ForegroundColor Yellow
        [Environment]::SetEnvironmentVariable("Path", "$currentPath;$installDir", "User")
        Write-Host "PATH updated!" -ForegroundColor Green
    } else {
        Write-Host "Tesseract already in PATH" -ForegroundColor Green
    }
} else {
    Write-Host "tesseract.exe not found, installation may have failed" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "  Installation Complete!" -ForegroundColor Green
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Close and reopen PowerShell/Terminal (to refresh PATH)"
Write-Host "2. Run 'tesseract --version' to verify"
Write-Host "3. Restart your PDF2LaTeX application"
Write-Host ""
Write-Host "Tesseract location: $installDir"
Write-Host ""
