# Multi-Environment Monitoring Dashboard - Environment Setup
# Run this script before starting the dashboard
# Usage: .\setup_monitoring_env.ps1

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Database Monitoring - Environment Setup" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# SQL Server Credentials
Write-Host "SQL Server Credentials:" -ForegroundColor Yellow
$env:SQL_DEV_PASSWORD = Read-Host "Enter DEV SQL Server password (or press Enter to skip)" -AsSecureString | ConvertFrom-SecureString
$env:SQL_QA_PASSWORD = Read-Host "Enter QA SQL Server password (or press Enter to skip)" -AsSecureString | ConvertFrom-SecureString
$env:SQL_PROD_PASSWORD = Read-Host "Enter PROD SQL Server password (or press Enter to skip)" -AsSecureString | ConvertFrom-SecureString

# Snowflake Credentials
Write-Host "`nSnowflake Credentials:" -ForegroundColor Yellow
$env:SNOWFLAKE_DEV_PASSWORD = Read-Host "Enter DEV Snowflake password (or press Enter to skip)" -AsSecureString | ConvertFrom-SecureString
$env:SNOWFLAKE_QA_PASSWORD = Read-Host "Enter QA Snowflake password (or press Enter to skip)" -AsSecureString | ConvertFrom-SecureString
$env:SNOWFLAKE_PROD_PASSWORD = Read-Host "Enter PROD Snowflake password (or press Enter to skip)" -AsSecureString | ConvertFrom-SecureString

# PostgreSQL Credentials
Write-Host "`nPostgreSQL Credentials:" -ForegroundColor Yellow
$env:POSTGRES_DEV_PASSWORD = Read-Host "Enter DEV PostgreSQL password (or press Enter to skip)" -AsSecureString | ConvertFrom-SecureString
$env:POSTGRES_QA_PASSWORD = Read-Host "Enter QA PostgreSQL password (or press Enter to skip)" -AsSecureString | ConvertFrom-SecureString
$env:POSTGRES_PROD_PASSWORD = Read-Host "Enter PROD PostgreSQL password (or press Enter to skip)" -AsSecureString | ConvertFrom-SecureString

Write-Host "`n✓ Environment variables configured for current session" -ForegroundColor Green
Write-Host "`nNote: These variables are temporary and will be lost when you close PowerShell." -ForegroundColor Yellow
Write-Host "To make them permanent, add them to your PowerShell profile or use Windows Environment Variables." -ForegroundColor Yellow

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Quick Start Commands" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

Write-Host "`n1. Monitor Development environment:" -ForegroundColor White
Write-Host "   python mcp_dashboard_multi.py --env dev" -ForegroundColor Gray

Write-Host "`n2. Monitor QA environment:" -ForegroundColor White
Write-Host "   python mcp_dashboard_multi.py --env qa" -ForegroundColor Gray

Write-Host "`n3. Monitor Production environment:" -ForegroundColor White
Write-Host "   python mcp_dashboard_multi.py --env prod" -ForegroundColor Gray

Write-Host "`n4. Monitor all enabled environments:" -ForegroundColor White
Write-Host "   python mcp_dashboard_multi.py --env all" -ForegroundColor Gray

Write-Host "`n5. Monitor multiple specific environments:" -ForegroundColor White
Write-Host "   python mcp_dashboard_multi.py --env dev,qa,prod" -ForegroundColor Gray

Write-Host "`n6. Debug mode with verbose logging:" -ForegroundColor White
Write-Host "   python mcp_dashboard_multi.py --env prod --debug" -ForegroundColor Gray

Write-Host "`n========================================`n" -ForegroundColor Cyan

# Optionally save to permanent environment (User scope)
$savePermanent = Read-Host "Do you want to save credentials to User environment variables permanently? (yes/no)"

if ($savePermanent -eq "yes" -or $savePermanent -eq "y") {
    Write-Host "`nSaving to User environment variables..." -ForegroundColor Yellow
    
    # Note: In production, consider using Windows Credential Manager or Azure Key Vault instead
    # This is a simplified example for demonstration
    
    if ($env:SQL_PROD_PASSWORD) {
        [Environment]::SetEnvironmentVariable("SQL_PROD_PASSWORD", $env:SQL_PROD_PASSWORD, "User")
    }
    if ($env:SNOWFLAKE_PROD_PASSWORD) {
        [Environment]::SetEnvironmentVariable("SNOWFLAKE_PROD_PASSWORD", $env:SNOWFLAKE_PROD_PASSWORD, "User")
    }
    if ($env:POSTGRES_PROD_PASSWORD) {
        [Environment]::SetEnvironmentVariable("POSTGRES_PROD_PASSWORD", $env:POSTGRES_PROD_PASSWORD, "User")
    }
    
    Write-Host "✓ Credentials saved to User environment variables" -ForegroundColor Green
    Write-Host "Note: Restart PowerShell to use saved credentials" -ForegroundColor Yellow
} else {
    Write-Host "`nCredentials not saved permanently. Remember to re-run this script in new sessions." -ForegroundColor Yellow
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Installation Check" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# Check Python
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✓ Python: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ Python not found - Install from https://www.python.org/" -ForegroundColor Red
}

# Check required Python packages
$packages = @("pyodbc", "snowflake-connector-python", "psycopg2-binary", "pyyaml")

Write-Host "`nChecking Python packages:" -ForegroundColor Yellow
foreach ($package in $packages) {
    try {
        $result = python -m pip show $package 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  ✓ $package installed" -ForegroundColor Green
        } else {
            Write-Host "  ✗ $package not installed" -ForegroundColor Red
        }
    } catch {
        Write-Host "  ✗ $package not installed" -ForegroundColor Red
    }
}

Write-Host "`nTo install missing packages, run:" -ForegroundColor Yellow
Write-Host "  pip install -r requirements.txt" -ForegroundColor Gray

Write-Host "`n========================================`n" -ForegroundColor Cyan
