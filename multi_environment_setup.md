# Multi-Environment Monitoring Dashboard Setup Guide

**Date:** December 8, 2024  
**Purpose:** Deploy monitoring dashboard across multiple environments with SQL Server, Snowflake, and PostgreSQL support

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Monitoring Dashboard                      │
│                  (mcp_dashboard_multi.py)                    │
└─────────────────────────────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
   ┌────▼────┐      ┌─────▼──────┐    ┌─────▼──────┐
   │   DEV   │      │     QA     │    │    PROD    │
   └────┬────┘      └─────┬──────┘    └─────┬──────┘
        │                 │                  │
   ┌────┴────────┬────────┴────────┬─────────┴──────┐
   │             │                 │                 │
┌──▼───┐  ┌────▼────┐  ┌─────▼──────┐  ┌──────▼────┐
│ SQL  │  │Snowflake│  │ PostgreSQL │  │  SQL(n)   │
└──────┘  └─────────┘  └────────────┘  └───────────┘
```

---

## Configuration File Structure

### 1. Environment Configuration (YAML)

**File:** `monitoring_environments.yaml`

```yaml
# Multi-Environment Monitoring Configuration
# Supports: SQL Server, Snowflake, PostgreSQL

environments:
  dev:
    name: "Development"
    enabled: true
    databases:
      - type: "sqlserver"
        name: "DEV-SQL01"
        server: "DEV-SQL01"
        database: "DevDB"
        auth: "windows"  # or "sql"
        username: ""  # for SQL auth
        password: ""  # for SQL auth
        port: 1433
        
      - type: "sqlserver"
        name: "DEV-SQL02"
        server: "DEV-SQL02\\INSTANCE01"
        database: "DevDB"
        auth: "windows"
        
      - type: "snowflake"
        name: "DEV-Snowflake"
        account: "DEV_ACCOUNT"
        user: "dev_user"
        password: "${SNOWFLAKE_DEV_PASSWORD}"  # Environment variable
        warehouse: "DEV_WH"
        database: "DEV_DB"
        schema: "PUBLIC"
        role: "DEV_ROLE"
        
      - type: "postgresql"
        name: "DEV-PostgreSQL"
        host: "dev-postgres.company.com"
        port: 5432
        database: "devdb"
        user: "dev_user"
        password: "${POSTGRES_DEV_PASSWORD}"
        sslmode: "require"

  qa:
    name: "Quality Assurance"
    enabled: true
    databases:
      - type: "sqlserver"
        name: "QA-SQL01"
        server: "QA-SQL01"
        database: "QADB"
        auth: "windows"
        
      - type: "sqlserver"
        name: "QA-SQL02"
        server: "QA-SQL02"
        database: "QADB"
        auth: "sql"
        username: "qa_monitor"
        password: "${SQL_QA_PASSWORD}"
        
      - type: "snowflake"
        name: "QA-Snowflake"
        account: "QA_ACCOUNT"
        user: "qa_user"
        password: "${SNOWFLAKE_QA_PASSWORD}"
        warehouse: "QA_WH"
        
      - type: "postgresql"
        name: "QA-PostgreSQL-Primary"
        host: "qa-postgres-primary.company.com"
        port: 5432
        database: "qadb"
        user: "qa_user"
        password: "${POSTGRES_QA_PASSWORD}"
        
      - type: "postgresql"
        name: "QA-PostgreSQL-Replica"
        host: "qa-postgres-replica.company.com"
        port: 5432
        database: "qadb"
        user: "qa_user"
        password: "${POSTGRES_QA_PASSWORD}"
        read_only: true

  prod:
    name: "Production"
    enabled: true
    databases:
      - type: "sqlserver"
        name: "PROD-SQL01"
        server: "PROD-SQL01"
        database: "ProdDB"
        auth: "windows"
        connection_timeout: 10
        
      - type: "sqlserver"
        name: "PROD-SQL02"
        server: "PROD-SQL02"
        database: "ProdDB"
        auth: "windows"
        
      - type: "sqlserver"
        name: "PROD-SQL03-AlwaysOn"
        server: "PROD-AG-LISTENER"
        database: "ProdDB"
        auth: "sql"
        username: "prod_monitor"
        password: "${SQL_PROD_PASSWORD}"
        application_intent: "ReadOnly"
        
      - type: "snowflake"
        name: "PROD-Snowflake"
        account: "PROD_ACCOUNT"
        user: "prod_user"
        password: "${SNOWFLAKE_PROD_PASSWORD}"
        warehouse: "PROD_WH"
        database: "PROD_DB"
        role: "MONITORING_ROLE"
        
      - type: "postgresql"
        name: "PROD-PostgreSQL-Primary"
        host: "prod-postgres-01.company.com"
        port: 5432
        database: "proddb"
        user: "monitoring_user"
        password: "${POSTGRES_PROD_PASSWORD}"
        sslmode: "require"
        
      - type: "postgresql"
        name: "PROD-PostgreSQL-Replica-01"
        host: "prod-postgres-replica-01.company.com"
        port: 5432
        database: "proddb"
        user: "monitoring_user"
        password: "${POSTGRES_PROD_PASSWORD}"
        sslmode: "require"
        read_only: true
        
      - type: "postgresql"
        name: "PROD-PostgreSQL-Replica-02"
        host: "prod-postgres-replica-02.company.com"
        port: 5432
        database: "proddb"
        user: "monitoring_user"
        password: "${POSTGRES_PROD_PASSWORD}"
        sslmode: "require"
        read_only: true

# Dashboard Settings
dashboard:
  refresh_interval: 300  # seconds (5 minutes)
  output_file: "monitoring_dashboard.html"
  open_browser: true
  timezone: "UTC"
  
# Alert Thresholds
thresholds:
  sqlserver:
    page_life_expectancy_min: 300
    buffer_cache_hit_ratio_min: 90
    blocked_sessions_max: 5
    cpu_ms_warning: 1000
    cpu_ms_critical: 10000
    index_fragmentation_warning: 10
    index_fragmentation_critical: 30
    
  snowflake:
    local_spill_gb_warning: 1.0
    remote_spill_gb_critical: 0.1
    credit_daily_max: 100
    queue_time_warning_sec: 60
    
  postgresql:
    connections_warning_pct: 80
    connections_critical_pct: 95
    cache_hit_ratio_min: 90
    bloat_warning_pct: 20
    bloat_critical_pct: 40
    replication_lag_warning_sec: 60
    replication_lag_critical_sec: 300

# Logging
logging:
  enabled: true
  level: "INFO"  # DEBUG, INFO, WARNING, ERROR
  file: "monitoring_logs/dashboard_{date}.log"
  retention_days: 30
```

---

## Environment Variables Setup

### Windows PowerShell

**File:** `set_monitoring_env.ps1`

```powershell
# Monitoring Dashboard Environment Variables
# Run this script before starting the dashboard

# SQL Server Credentials
$env:SQL_QA_PASSWORD = "YourQAPassword"
$env:SQL_PROD_PASSWORD = "YourProdPassword"

# Snowflake Credentials
$env:SNOWFLAKE_DEV_PASSWORD = "YourDevSnowflakePassword"
$env:SNOWFLAKE_QA_PASSWORD = "YourQASnowflakePassword"
$env:SNOWFLAKE_PROD_PASSWORD = "YourProdSnowflakePassword"

# PostgreSQL Credentials
$env:POSTGRES_DEV_PASSWORD = "YourDevPostgresPassword"
$env:POSTGRES_QA_PASSWORD = "YourQAPostgresPassword"
$env:POSTGRES_PROD_PASSWORD = "YourProdPostgresPassword"

Write-Host "✓ Environment variables set successfully" -ForegroundColor Green
Write-Host "Run: python mcp_dashboard_multi.py --env prod" -ForegroundColor Cyan
```

### Linux/MacOS Bash

**File:** `set_monitoring_env.sh`

```bash
#!/bin/bash
# Monitoring Dashboard Environment Variables

export SQL_QA_PASSWORD="YourQAPassword"
export SQL_PROD_PASSWORD="YourProdPassword"

export SNOWFLAKE_DEV_PASSWORD="YourDevSnowflakePassword"
export SNOWFLAKE_QA_PASSWORD="YourQASnowflakePassword"
export SNOWFLAKE_PROD_PASSWORD="YourProdSnowflakePassword"

export POSTGRES_DEV_PASSWORD="YourDevPostgresPassword"
export POSTGRES_QA_PASSWORD="YourQAPostgresPassword"
export POSTGRES_PROD_PASSWORD="YourProdPostgresPassword"

echo "✓ Environment variables set successfully"
echo "Run: python mcp_dashboard_multi.py --env prod"
```

---

## Python Dependencies

**File:** `requirements.txt`

```txt
# Database Connectors
pyodbc==5.3.0                    # SQL Server
snowflake-connector-python==3.17.4  # Snowflake
psycopg2-binary==2.9.9           # PostgreSQL

# Configuration & Utilities
pyyaml==6.0.1                    # YAML config parsing
python-dotenv==1.0.0             # Environment variable management
jinja2==3.1.2                    # HTML templating

# Optional: Encryption for sensitive data
cryptography==41.0.7             # Password encryption
```

**Installation:**
```powershell
pip install -r requirements.txt
```

---

## Dashboard Script Structure

### Main Script: `mcp_dashboard_multi.py`

**Features:**
- ✅ Multi-environment support (DEV, QA, PROD)
- ✅ Multiple database types (SQL Server, Snowflake, PostgreSQL)
- ✅ Parallel metric collection (threading)
- ✅ Environment variable substitution
- ✅ Configurable thresholds
- ✅ Error handling per database
- ✅ HTML dashboard generation
- ✅ Auto-refresh capability
- ✅ Logging to file

**Command Line Usage:**
```powershell
# Monitor specific environment
python mcp_dashboard_multi.py --env prod

# Monitor multiple environments
python mcp_dashboard_multi.py --env dev,qa,prod

# Monitor all enabled environments
python mcp_dashboard_multi.py --env all

# Monitor with custom config file
python mcp_dashboard_multi.py --config custom_config.yaml --env prod

# Generate dashboard without opening browser
python mcp_dashboard_multi.py --env prod --no-browser

# Debug mode with verbose logging
python mcp_dashboard_multi.py --env dev --debug
```

---

## PostgreSQL Monitoring Queries

### 1. Connection & Session Metrics

```sql
-- Active Connections
SELECT 
    COUNT(*) as total_connections,
    COUNT(*) FILTER (WHERE state = 'active') as active,
    COUNT(*) FILTER (WHERE state = 'idle') as idle,
    COUNT(*) FILTER (WHERE wait_event_type IS NOT NULL) as waiting
FROM pg_stat_activity
WHERE pid != pg_backend_pid();

-- Connection Limit Check
SELECT 
    setting::int as max_connections,
    (SELECT COUNT(*) FROM pg_stat_activity) as current_connections,
    ROUND((SELECT COUNT(*)::numeric FROM pg_stat_activity) / setting::numeric * 100, 1) as usage_pct
FROM pg_settings
WHERE name = 'max_connections';
```

### 2. Database Performance

```sql
-- Cache Hit Ratio
SELECT 
    datname,
    ROUND((blks_hit::numeric / NULLIF(blks_hit + blks_read, 0)) * 100, 2) as cache_hit_ratio,
    pg_size_pretty(pg_database_size(datname)) as size
FROM pg_stat_database
WHERE datname NOT IN ('template0', 'template1')
ORDER BY cache_hit_ratio DESC;

-- Long Running Queries
SELECT 
    pid,
    now() - query_start as duration,
    state,
    LEFT(query, 100) as query_preview
FROM pg_stat_activity
WHERE state != 'idle'
  AND query_start < now() - interval '5 minutes'
ORDER BY duration DESC
LIMIT 10;
```

### 3. Table Bloat & Maintenance

```sql
-- Table Bloat Estimation
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as total_size,
    n_live_tup as live_tuples,
    n_dead_tup as dead_tuples,
    ROUND((n_dead_tup::numeric / NULLIF(n_live_tup + n_dead_tup, 0)) * 100, 1) as bloat_pct,
    last_vacuum,
    last_autovacuum
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 20;
```

### 4. Replication Lag (for replicas)

```sql
-- Replication Status
SELECT 
    client_addr,
    state,
    sync_state,
    pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) as lag_bytes,
    EXTRACT(EPOCH FROM (now() - replay_timestamp))::int as lag_seconds
FROM pg_stat_replication;

-- On Replica: Check Lag
SELECT 
    now() - pg_last_xact_replay_timestamp() as replication_lag;
```

### 5. Index Usage

```sql
-- Unused Indexes
SELECT 
    schemaname,
    tablename,
    indexname,
    pg_size_pretty(pg_relation_size(indexrelid)) as index_size,
    idx_scan as scans,
    idx_tup_read as tuples_read
FROM pg_stat_user_indexes
WHERE idx_scan = 0
  AND schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY pg_relation_size(indexrelid) DESC
LIMIT 20;
```

---

## Deployment Steps

### Step 1: Prepare Configuration Files

```powershell
# Create directory structure
New-Item -ItemType Directory -Path "D:\Monitoring" -Force
New-Item -ItemType Directory -Path "D:\Monitoring\config" -Force
New-Item -ItemType Directory -Path "D:\Monitoring\logs" -Force
New-Item -ItemType Directory -Path "D:\Monitoring\output" -Force

# Copy configuration files
Copy-Item "monitoring_environments.yaml" -Destination "D:\Monitoring\config\"
Copy-Item "mcp_dashboard_multi.py" -Destination "D:\Monitoring\"
Copy-Item "requirements.txt" -Destination "D:\Monitoring\"
```

### Step 2: Install Dependencies

```powershell
cd D:\Monitoring
python -m pip install -r requirements.txt
```

### Step 3: Configure Environment Variables

```powershell
# Option 1: Run script each time
.\set_monitoring_env.ps1

# Option 2: Set system environment variables permanently
[Environment]::SetEnvironmentVariable("SQL_PROD_PASSWORD", "YourPassword", "User")
[Environment]::SetEnvironmentVariable("SNOWFLAKE_PROD_PASSWORD", "YourPassword", "User")
[Environment]::SetEnvironmentVariable("POSTGRES_PROD_PASSWORD", "YourPassword", "User")
```

### Step 4: Test Connection to Each Database

```powershell
# Test SQL Server
sqlcmd -S PROD-SQL01 -d ProdDB -E -Q "SELECT @@VERSION"

# Test PostgreSQL
psql -h prod-postgres-01.company.com -U monitoring_user -d proddb -c "SELECT version();"

# Test Snowflake (using Python)
python -c "import snowflake.connector; conn = snowflake.connector.connect(user='prod_user', password='...', account='PROD_ACCOUNT'); print('✓ Snowflake connected')"
```

### Step 5: Run Dashboard

```powershell
# Single environment
python mcp_dashboard_multi.py --env prod

# All environments
python mcp_dashboard_multi.py --env all

# Schedule as Windows Task (runs every 5 minutes)
$Action = New-ScheduledTaskAction -Execute "python" -Argument "D:\Monitoring\mcp_dashboard_multi.py --env all --no-browser"
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 9999)
Register-ScheduledTask -TaskName "MonitoringDashboard" -Action $Action -Trigger $Trigger -Description "Multi-environment database monitoring"
```

---

## Security Best Practices

### 1. Credential Management

**DO:**
- ✅ Use environment variables for passwords
- ✅ Use Windows Credential Manager or Azure Key Vault
- ✅ Rotate passwords regularly (90 days)
- ✅ Use read-only service accounts for monitoring
- ✅ Encrypt configuration files containing sensitive data

**DON'T:**
- ❌ Store passwords in YAML files
- ❌ Commit credentials to Git repositories
- ❌ Use admin accounts for monitoring
- ❌ Share credentials across environments

### 2. Network Security

```yaml
# Use SSL/TLS for all connections
sqlserver:
  encrypt: true
  trust_server_certificate: false  # Verify SSL cert

postgresql:
  sslmode: "require"  # or "verify-full"

snowflake:
  # SSL enabled by default
```

### 3. Service Account Permissions

**SQL Server (Minimum Permissions):**
```sql
USE master;
CREATE LOGIN [monitoring_user] WITH PASSWORD = 'StrongPassword123!';

USE YourDatabase;
CREATE USER [monitoring_user] FOR LOGIN [monitoring_user];

-- Grant VIEW DATABASE STATE for DMVs
GRANT VIEW DATABASE STATE TO [monitoring_user];
GRANT VIEW SERVER STATE TO [monitoring_user];

-- Grant SELECT on specific tables (if needed)
GRANT SELECT ON sys.database_files TO [monitoring_user];
```

**PostgreSQL (Minimum Permissions):**
```sql
CREATE ROLE monitoring_user WITH LOGIN PASSWORD 'StrongPassword123!';

-- Grant connection to database
GRANT CONNECT ON DATABASE proddb TO monitoring_user;

-- Grant usage on schema
GRANT USAGE ON SCHEMA public TO monitoring_user;

-- Grant pg_monitor role (PostgreSQL 10+)
GRANT pg_monitor TO monitoring_user;
```

**Snowflake (Minimum Permissions):**
```sql
CREATE ROLE MONITORING_ROLE;

-- Grant usage on warehouse
GRANT USAGE ON WAREHOUSE PROD_WH TO ROLE MONITORING_ROLE;

-- Grant access to ACCOUNT_USAGE schema
GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO ROLE MONITORING_ROLE;

-- Create user and assign role
CREATE USER monitoring_user PASSWORD = 'StrongPassword123!' DEFAULT_ROLE = MONITORING_ROLE;
GRANT ROLE MONITORING_ROLE TO USER monitoring_user;
```

---

## Troubleshooting

### Common Issues

**1. "Unable to import pyodbc"**
```powershell
# Ensure ODBC Driver 17 for SQL Server is installed
# Download from: https://docs.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server

# Verify installation
odbcconf /q /a {ENUM_DRIVERS}
```

**2. "PostgreSQL connection timeout"**
```powershell
# Check firewall rules
Test-NetConnection -ComputerName prod-postgres-01.company.com -Port 5432

# Verify pg_hba.conf allows connections from your IP
# On PostgreSQL server:
psql -U postgres -c "SHOW hba_file"
```

**3. "Snowflake authentication error"**
```powershell
# Verify account identifier format
# Format: <account_locator>.<region>.<cloud>
# Example: xy12345.us-east-1.aws

# Test with snowsql CLI
snowsql -a PROD_ACCOUNT -u prod_user
```

**4. "Environment variable not found"**
```powershell
# Verify variables are set
Get-ChildItem Env: | Where-Object { $_.Name -like "*PASSWORD*" }

# Re-run environment setup script
.\set_monitoring_env.ps1
```

---

## Monitoring Dashboard Features

### Multi-Environment View

```
┌──────────────────────────────────────────────────────────┐
│  📊 Multi-Environment Database Monitoring Dashboard      │
│  Environment: Production | Last Updated: 2024-12-08 10:30│
└──────────────────────────────────────────────────────────┘

┌─────────────────┬─────────────────┬─────────────────────┐
│  PROD-SQL01     │  PROD-SQL02     │  PROD-SQL03-AlwaysOn│
│  Status: ✅     │  Status: ✅     │  Status: ✅ (RO)    │
│  Sessions: 145  │  Sessions: 89   │  Sessions: 12       │
│  CPU: 25%       │  CPU: 15%       │  CPU: 5%            │
│  Blocked: 0     │  Blocked: 2 ⚠️  │  Blocked: 0         │
└─────────────────┴─────────────────┴─────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  PROD-Snowflake                                          │
│  Status: ✅ | Warehouse: PROD_WH (Running)              │
│  Active Queries: 8 | Credits (24h): 45.23              │
│  Query Spill: ⚠️ 3 queries, 2.5 GB local spill         │
└─────────────────────────────────────────────────────────┘

┌──────────────────────┬──────────────────────────────────┐
│  PROD-PostgreSQL-Pri │  PROD-PostgreSQL-Replica-01      │
│  Status: ✅          │  Status: ✅ | Lag: 2 sec ✅      │
│  Connections: 45/100 │  Connections: 12/100             │
│  Cache Hit: 98.5% ✅ │  Cache Hit: 99.1% ✅             │
└──────────────────────┴──────────────────────────────────┘
```

---

## Next Steps

1. **Review and customize** `monitoring_environments.yaml` for your infrastructure
2. **Set up service accounts** with minimum required permissions
3. **Configure environment variables** securely
4. **Test connectivity** to all databases
5. **Run dashboard** for each environment (dev → qa → prod)
6. **Schedule automated runs** using Task Scheduler or cron
7. **Set up alerting** based on threshold breaches
8. **Document** environment-specific configurations

---

## Support Matrix

| Database Type | Windows | Linux | macOS | Tested Version |
|--------------|---------|-------|-------|----------------|
| SQL Server   | ✅      | ✅    | ✅    | 2019-2025     |
| Snowflake    | ✅      | ✅    | ✅    | Latest        |
| PostgreSQL   | ✅      | ✅    | ✅    | 12-16         |

---

**Ready to deploy? Start with DEV environment and gradually roll out to QA and PROD.**
