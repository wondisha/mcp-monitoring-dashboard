# Multi-Environment Deployment Checklist

## Pre-Deployment Checklist

### 1. Infrastructure Requirements
- [ ] SQL Server instances accessible from monitoring server
- [ ] Snowflake account credentials available
- [ ] PostgreSQL instances accessible (check firewall rules)
- [ ] Network connectivity tested to all database servers
- [ ] Service accounts created with read-only permissions

### 2. Software Requirements
- [ ] Python 3.9+ installed
- [ ] ODBC Driver 17 for SQL Server installed (Windows/Linux)
- [ ] PostgreSQL client libraries installed (if needed)
- [ ] Git installed (for version control)

### 3. Security Requirements
- [ ] Service accounts created (monitoring_user)
- [ ] Minimum permissions granted (VIEW SERVER STATE, pg_monitor, etc.)
- [ ] Passwords stored securely (environment variables or Key Vault)
- [ ] SSL/TLS certificates configured for production
- [ ] Network security groups/firewall rules configured

---

## Deployment Steps

### Step 1: Prepare Monitoring Server

```powershell
# Create directory structure
New-Item -ItemType Directory -Path "C:\Monitoring" -Force
New-Item -ItemType Directory -Path "C:\Monitoring\config" -Force
New-Item -ItemType Directory -Path "C:\Monitoring\logs" -Force
New-Item -ItemType Directory -Path "C:\Monitoring\output" -Force

# Navigate to monitoring directory
cd C:\Monitoring
```

### Step 2: Copy Files

```powershell
# Copy required files from development
Copy-Item "d:\Resume\mcp_dashboard_multi.py" -Destination "C:\Monitoring\"
Copy-Item "d:\Resume\monitoring_environments.yaml" -Destination "C:\Monitoring\config\"
Copy-Item "d:\Resume\requirements_monitoring.txt" -Destination "C:\Monitoring\"
Copy-Item "d:\Resume\setup_monitoring_env.ps1" -Destination "C:\Monitoring\"
```

### Step 3: Install Dependencies

```powershell
# Install Python packages
cd C:\Monitoring
pip install -r requirements_monitoring.txt

# Verify installation
pip list | Select-String "pyodbc|snowflake|psycopg2|pyyaml"
```

**Expected Output:**
```
pyodbc                5.3.0
psycopg2-binary       2.9.9
pyyaml                6.0.1
snowflake-connector-python 3.17.4
```

### Step 4: Configure Environment

**Edit `config/monitoring_environments.yaml`:**

```yaml
# Update these sections for your environment:
1. Server names/hostnames
2. Database names
3. Authentication methods
4. Warehouse names (Snowflake)
5. Threshold values
```

**Test Configuration Syntax:**
```powershell
python -c "import yaml; yaml.safe_load(open('config/monitoring_environments.yaml'))"
```

### Step 5: Set Up Credentials

**Option A: Interactive Setup (Recommended for Testing)**
```powershell
.\setup_monitoring_env.ps1
```

**Option B: Script-based (for Automation)**
```powershell
# Create a secure credential script
$env:SQL_PROD_PASSWORD = "YourSecurePassword"
$env:SNOWFLAKE_PROD_PASSWORD = "YourSecurePassword"
$env:POSTGRES_PROD_PASSWORD = "YourSecurePassword"
```

**Option C: Windows Credential Manager (Best for Production)**
```powershell
# Store credentials securely
cmdkey /generic:SQL_PROD_PASSWORD /user:monitoring /pass:YourPassword
cmdkey /generic:SNOWFLAKE_PROD_PASSWORD /user:monitoring /pass:YourPassword
cmdkey /generic:POSTGRES_PROD_PASSWORD /user:monitoring /pass:YourPassword
```

### Step 6: Test Connections

**Test SQL Server:**
```powershell
sqlcmd -S PROD-SQL01 -d ProdDB -E -Q "SELECT @@VERSION"
```

**Test PostgreSQL:**
```powershell
# Install PostgreSQL client first
# Then test connection
psql -h prod-postgres-01.company.local -U monitoring_user -d proddb -c "SELECT version();"
```

**Test Snowflake:**
```powershell
# Using Python
python -c "import snowflake.connector; conn = snowflake.connector.connect(user='prod_user', password='***', account='YOUR_ACCOUNT'); print('✓ Connected')"
```

### Step 7: Run Test Dashboard

**Test Development Environment First:**
```powershell
python mcp_dashboard_multi.py --env dev
```

**Test QA Environment:**
```powershell
python mcp_dashboard_multi.py --env qa
```

**Test Production Environment:**
```powershell
python mcp_dashboard_multi.py --env prod
```

**Test All Environments:**
```powershell
python mcp_dashboard_multi.py --env all
```

### Step 8: Schedule Automated Runs

**Create Scheduled Task (Windows):**

```powershell
# Create scheduled task to run every 5 minutes
$TaskName = "MonitoringDashboard"
$ScriptPath = "C:\Monitoring\mcp_dashboard_multi.py"
$PythonPath = "C:\Python39\python.exe"  # Adjust to your Python path

# Create action
$Action = New-ScheduledTaskAction -Execute $PythonPath -Argument "$ScriptPath --env all --no-browser" -WorkingDirectory "C:\Monitoring"

# Create trigger (every 5 minutes)
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 9999)

# Create task settings
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

# Register task
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Multi-environment database monitoring dashboard"

Write-Host "✓ Scheduled task created: $TaskName" -ForegroundColor Green
Write-Host "  Runs every 5 minutes" -ForegroundColor Yellow
```

**Verify Scheduled Task:**
```powershell
Get-ScheduledTask -TaskName "MonitoringDashboard"
```

**Create Linux Cron Job:**
```bash
# Edit crontab
crontab -e

# Add this line (runs every 5 minutes)
*/5 * * * * /usr/bin/python3 /opt/monitoring/mcp_dashboard_multi.py --env all --no-browser >> /var/log/monitoring_dashboard.log 2>&1
```

---

## Post-Deployment Validation

### Checklist

- [ ] Dashboard HTML file generated successfully
- [ ] All environments showing "SUCCESS" status
- [ ] Metrics displayed correctly for each database type
- [ ] No error messages in logs
- [ ] Scheduled task running automatically
- [ ] Dashboard auto-refresh working (5 minutes)
- [ ] Threshold alerts displaying correctly
- [ ] Replication lag showing for replicas
- [ ] Log files created in monitoring_logs/

### Verify Dashboard Content

**SQL Server Metrics:**
- [ ] Sessions count displayed
- [ ] Blocked sessions showing
- [ ] Storage usage percentage
- [ ] Top queries by CPU
- [ ] Performance counters

**Snowflake Metrics:**
- [ ] Active queries count
- [ ] Credit usage (24 hours)
- [ ] Query spill metrics
- [ ] Warehouse activity

**PostgreSQL Metrics:**
- [ ] Connection count and usage %
- [ ] Cache hit ratio
- [ ] Replication lag (for replicas)
- [ ] Long running queries

### Check Log Files

```powershell
# View recent logs
Get-Content "C:\Monitoring\monitoring_*.log" -Tail 50
```

**Look for:**
- ✓ "Collecting metrics for [environment]..."
- ✓ "Dashboard generated successfully!"
- ✗ No ERROR or CRITICAL messages

---

## Troubleshooting

### Issue: "pyodbc not found"

**Solution:**
```powershell
# Ensure ODBC Driver 17 installed
odbcconf /q /a {ENUM_DRIVERS}

# Reinstall pyodbc
pip uninstall pyodbc
pip install pyodbc
```

### Issue: "PostgreSQL connection timeout"

**Solution:**
```powershell
# Test network connectivity
Test-NetConnection -ComputerName prod-postgres-01.company.local -Port 5432

# Check pg_hba.conf on PostgreSQL server allows connections
# On PostgreSQL server:
sudo nano /var/lib/pgsql/data/pg_hba.conf
# Add: host all monitoring_user 10.0.0.0/8 md5
sudo systemctl reload postgresql
```

### Issue: "Snowflake authentication failed"

**Solution:**
```powershell
# Verify account identifier format
# Correct format: <account_locator>.<region>.<cloud>
# Example: xy12345.us-east-1.aws

# Test with snowsql CLI
snowsql -a EEJRNQB-JM98615 -u prod_user

# Check if MFA is enabled (not supported by connector - disable for service account)
```

### Issue: "Environment variable not found"

**Solution:**
```powershell
# List all environment variables
Get-ChildItem Env: | Where-Object { $_.Name -like "*PASSWORD*" }

# Re-run setup script
.\setup_monitoring_env.ps1

# Or set manually
$env:SQL_PROD_PASSWORD = "YourPassword"
```

---

## Maintenance

### Daily Tasks
- [ ] Review dashboard for ERROR status
- [ ] Check replication lag < 60 seconds
- [ ] Verify credit usage within budget
- [ ] Review blocked sessions

### Weekly Tasks
- [ ] Review log files for errors
- [ ] Check disk space for log retention
- [ ] Verify all scheduled tasks running
- [ ] Review threshold alerts

### Monthly Tasks
- [ ] Rotate passwords
- [ ] Review and update thresholds
- [ ] Archive old log files
- [ ] Test disaster recovery (DR) connections
- [ ] Update Python packages: `pip install --upgrade -r requirements_monitoring.txt`

---

## Rollback Plan

If issues occur after deployment:

1. **Stop Scheduled Task:**
   ```powershell
   Disable-ScheduledTask -TaskName "MonitoringDashboard"
   ```

2. **Review Logs:**
   ```powershell
   Get-Content "C:\Monitoring\monitoring_*.log" | Select-String "ERROR"
   ```

3. **Test Connections Manually:**
   ```powershell
   python mcp_dashboard_multi.py --env dev --debug
   ```

4. **Revert Configuration:**
   ```powershell
   # Restore previous config
   Copy-Item "C:\Monitoring\config\monitoring_environments.yaml.backup" -Destination "C:\Monitoring\config\monitoring_environments.yaml"
   ```

5. **Re-enable Task:**
   ```powershell
   Enable-ScheduledTask -TaskName "MonitoringDashboard"
   ```

---

## Support Contacts

- **DBA Team:** dba-team@company.com
- **DevOps Team:** devops-team@company.com
- **Snowflake Support:** https://community.snowflake.com/

---

## Documentation Links

- SQL Server DMVs: https://docs.microsoft.com/en-us/sql/relational-databases/system-dynamic-management-views/
- Snowflake ACCOUNT_USAGE: https://docs.snowflake.com/en/sql-reference/account-usage.html
- PostgreSQL Monitoring: https://www.postgresql.org/docs/current/monitoring.html

---

**Deployment Date:** ___________  
**Deployed By:** ___________  
**Approved By:** ___________  
**Status:** [ ] DEV [ ] QA [ ] PROD
