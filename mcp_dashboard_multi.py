#!/usr/bin/env python3
"""
Multi-Environment Database Monitoring Dashboard
Supports: SQL Server, Snowflake, PostgreSQL
Environments: DEV, QA, PROD (configurable)
"""

import os
import sys
import yaml
import json
import argparse
import logging
import webbrowser
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Database connectors
try:
    import pyodbc
except ImportError:
    pyodbc = None
    
try:
    import snowflake.connector
except ImportError:
    snowflake = None
    
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    psycopg2 = None


class DatabaseMonitor:
    """Base class for database monitoring"""
    
    def __init__(self, config, thresholds):
        self.config = config
        self.thresholds = thresholds
        self.name = config.get('name', 'Unknown')
        self.type = config.get('type', 'unknown')
        
    def collect_metrics(self):
        """Override in subclass"""
        raise NotImplementedError


class SQLServerMonitor(DatabaseMonitor):
    """SQL Server monitoring"""
    
    def collect_metrics(self):
        if not pyodbc:
            return {'status': 'ERROR', 'error': 'pyodbc not installed'}
            
        metrics = {
            'name': self.name,
            'type': 'sqlserver',
            'sessions': {},
            'storage': {},
            'performance': {},
            'index_health': [],
            'top_queries': []
        }
        
        try:
            # Build connection string
            server = self.config['server']
            database = self.config['database']
            auth = self.config.get('auth', 'windows')
            
            if auth == 'windows':
                conn_str = f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};DATABASE={database};Trusted_Connection=yes;'
            else:
                username = self.config['username']
                password = self._get_password()
                conn_str = f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};DATABASE={database};UID={username};PWD={password};'
            
            # Add optional parameters
            if self.config.get('application_intent'):
                conn_str += f"ApplicationIntent={self.config['application_intent']};"
                
            conn = pyodbc.connect(conn_str, timeout=self.config.get('connection_timeout', 10))
            cursor = conn.cursor()
            
            # Sessions
            cursor.execute("""
                SELECT 
                    COUNT(DISTINCT s.session_id) as total,
                    SUM(CASE WHEN s.status = 'running' THEN 1 ELSE 0 END) as running,
                    SUM(CASE WHEN s.status = 'sleeping' THEN 1 ELSE 0 END) as sleeping,
                    SUM(CASE WHEN r.blocking_session_id > 0 THEN 1 ELSE 0 END) as blocked
                FROM sys.dm_exec_sessions s
                LEFT JOIN sys.dm_exec_requests r ON s.session_id = r.session_id
                WHERE s.is_user_process = 1
            """)
            row = cursor.fetchone()
            metrics['sessions'] = {
                'total': row[0] or 0,
                'running': row[1] or 0,
                'sleeping': row[2] or 0,
                'blocked': row[3] or 0
            }
            
            # Storage
            cursor.execute("""
                SELECT 
                    name,
                    (size * 8.0 / 1024) as size_mb,
                    (FILEPROPERTY(name, 'SpaceUsed') * 8.0 / 1024) as used_mb
                FROM sys.database_files
                WHERE type_desc = 'ROWS'
            """)
            row = cursor.fetchone()
            if row:
                metrics['storage'] = {
                    'name': row[0],
                    'total_mb': round(row[1], 2),
                    'used_mb': round(row[2], 2),
                    'free_mb': round(row[1] - row[2], 2),
                    'used_percent': round((row[2] / row[1]) * 100, 1) if row[1] > 0 else 0
                }
            
            # Performance counters
            cursor.execute("""
                SELECT counter_name, cntr_value
                FROM sys.dm_os_performance_counters
                WHERE (object_name LIKE '%SQL Statistics%' 
                   AND counter_name IN ('Batch Requests/sec', 'SQL Compilations/sec'))
                   OR (object_name LIKE '%Buffer Manager%' 
                   AND counter_name IN ('Page life expectancy', 'Buffer cache hit ratio'))
            """)
            for row in cursor.fetchall():
                key = row[0].replace(' ', '_').replace('/', '_').lower()
                metrics['performance'][key] = row[1]
            
            # Top 10 queries by CPU
            cursor.execute("""
                SELECT TOP 10
                    SUBSTRING(qt.text, (qs.statement_start_offset/2)+1,
                        ((CASE qs.statement_end_offset
                            WHEN -1 THEN DATALENGTH(qt.text)
                            ELSE qs.statement_end_offset
                        END - qs.statement_start_offset)/2) + 1) AS query_text,
                    qs.execution_count,
                    qs.total_worker_time / 1000 AS total_cpu_ms,
                    qs.total_elapsed_time / 1000 AS total_elapsed_ms,
                    qs.total_logical_reads
                FROM sys.dm_exec_query_stats qs
                CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) qt
                WHERE qt.dbid = DB_ID()
                ORDER BY qs.total_worker_time DESC
            """)
            for row in cursor.fetchall():
                if row[0]:
                    query_text = row[0].strip()[:100]
                    metrics['top_queries'].append({
                        'query': query_text + '...' if len(row[0]) > 100 else query_text,
                        'executions': row[1],
                        'cpu_ms': row[2],
                        'elapsed_ms': row[3],
                        'logical_reads': row[4]
                    })
            
            cursor.close()
            conn.close()
            metrics['status'] = 'SUCCESS'
            
        except Exception as e:
            metrics['status'] = 'ERROR'
            metrics['error'] = str(e)
            logging.error(f"SQL Server {self.name}: {e}")
        
        return metrics
    
    def _get_password(self):
        """Get password from environment variable"""
        password = self.config.get('password', '')
        if password.startswith('${') and password.endswith('}'):
            env_var = password[2:-1]
            return os.environ.get(env_var, '')
        return password


class SnowflakeMonitor(DatabaseMonitor):
    """Snowflake monitoring"""
    
    def collect_metrics(self):
        if not snowflake:
            return {'status': 'ERROR', 'error': 'snowflake-connector-python not installed'}
            
        metrics = {
            'name': self.name,
            'type': 'snowflake',
            'warehouses': [],
            'credits': {},
            'storage': [],
            'queries': {},
            'spill': {}
        }
        
        try:
            # Get password from environment variable
            password = self._get_password()
            
            conn = snowflake.connector.connect(
                user=self.config['user'],
                password=password,
                account=self.config['account'],
                warehouse=self.config.get('warehouse'),
                database=self.config.get('database'),
                schema=self.config.get('schema', 'PUBLIC'),
                role=self.config.get('role')
            )
            cursor = conn.cursor()
            
            # Warehouse utilization
            cursor.execute("""
                SELECT 
                    warehouse_name,
                    COUNT(*) as query_count,
                    AVG(execution_time) / 1000 as avg_execution_sec
                FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
                WHERE start_time >= DATEADD(HOUR, -1, CURRENT_TIMESTAMP())
                AND warehouse_name IS NOT NULL
                GROUP BY warehouse_name
                ORDER BY query_count DESC
                LIMIT 5
            """)
            for row in cursor.fetchall():
                metrics['warehouses'].append({
                    'name': row[0],
                    'queries': row[1],
                    'avg_exec': round(row[2], 2) if row[2] else 0
                })
            
            # Credit consumption
            cursor.execute("""
                SELECT 
                    warehouse_name,
                    SUM(credits_used) as total_credits
                FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
                WHERE start_time >= DATEADD(DAY, -1, CURRENT_TIMESTAMP())
                GROUP BY warehouse_name
                ORDER BY total_credits DESC
            """)
            for row in cursor.fetchall():
                metrics['credits'][row[0]] = float(round(row[1], 4))
            
            # Storage usage
            cursor.execute("""
                SELECT 
                    database_name,
                    AVG(average_database_bytes) / (1024*1024*1024) as db_gb
                FROM SNOWFLAKE.ACCOUNT_USAGE.DATABASE_STORAGE_USAGE_HISTORY
                WHERE usage_date >= DATEADD(DAY, -1, CURRENT_DATE())
                GROUP BY database_name
                HAVING db_gb > 0
                ORDER BY db_gb DESC
                LIMIT 5
            """)
            for row in cursor.fetchall():
                metrics['storage'].append({
                    'database': row[0],
                    'size_gb': round(row[1], 2)
                })
            
            # Active queries
            cursor.execute("""
                SELECT COUNT(*) 
                FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
                WHERE start_time >= DATEADD(MINUTE, -5, CURRENT_TIMESTAMP())
                AND execution_status = 'RUNNING'
            """)
            metrics['queries']['active'] = cursor.fetchone()[0]
            
            # Query spill
            cursor.execute("""
                SELECT 
                    COUNT(*) as queries_with_spill,
                    SUM(BYTES_SPILLED_TO_LOCAL_STORAGE) / (1024*1024*1024) as local_gb,
                    SUM(BYTES_SPILLED_TO_REMOTE_STORAGE) / (1024*1024*1024) as remote_gb
                FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
                WHERE start_time >= DATEADD(HOUR, -1, CURRENT_TIMESTAMP())
                AND (BYTES_SPILLED_TO_LOCAL_STORAGE > 0 OR BYTES_SPILLED_TO_REMOTE_STORAGE > 0)
            """)
            row = cursor.fetchone()
            if row and row[0]:
                metrics['spill'] = {
                    'queries_with_spill': row[0],
                    'local_gb': round(row[1] or 0, 3),
                    'remote_gb': round(row[2] or 0, 3)
                }
            else:
                metrics['spill'] = {'queries_with_spill': 0, 'local_gb': 0, 'remote_gb': 0}
            
            cursor.close()
            conn.close()
            metrics['status'] = 'SUCCESS'
            
        except Exception as e:
            metrics['status'] = 'ERROR'
            metrics['error'] = str(e)
            logging.error(f"Snowflake {self.name}: {e}")
        
        return metrics
    
    def _get_password(self):
        password = self.config.get('password', '')
        if password.startswith('${') and password.endswith('}'):
            env_var = password[2:-1]
            return os.environ.get(env_var, '')
        return password


class PostgreSQLMonitor(DatabaseMonitor):
    """PostgreSQL monitoring"""
    
    def collect_metrics(self):
        if not psycopg2:
            return {'status': 'ERROR', 'error': 'psycopg2 not installed'}
            
        metrics = {
            'name': self.name,
            'type': 'postgresql',
            'connections': {},
            'databases': [],
            'cache_hit_ratio': 0,
            'long_queries': [],
            'replication': {}
        }
        
        try:
            password = self._get_password()
            
            conn = psycopg2.connect(
                host=self.config['host'],
                port=self.config.get('port', 5432),
                database=self.config['database'],
                user=self.config['user'],
                password=password,
                sslmode=self.config.get('sslmode', 'prefer'),
                connect_timeout=10
            )
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Connections
            cursor.execute("""
                SELECT 
                    (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') as max_conn,
                    COUNT(*) as current_conn,
                    COUNT(*) FILTER (WHERE state = 'active') as active_conn,
                    COUNT(*) FILTER (WHERE state = 'idle') as idle_conn,
                    COUNT(*) FILTER (WHERE wait_event_type IS NOT NULL) as waiting_conn
                FROM pg_stat_activity
                WHERE pid != pg_backend_pid()
            """)
            row = cursor.fetchone()
            metrics['connections'] = {
                'max': row['max_conn'],
                'current': row['current_conn'],
                'active': row['active_conn'],
                'idle': row['idle_conn'],
                'waiting': row['waiting_conn'],
                'usage_pct': round((row['current_conn'] / row['max_conn']) * 100, 1)
            }
            
            # Cache hit ratio
            cursor.execute("""
                SELECT 
                    datname,
                    ROUND((blks_hit::numeric / NULLIF(blks_hit + blks_read, 0)) * 100, 2) as hit_ratio,
                    pg_size_pretty(pg_database_size(datname)) as size
                FROM pg_stat_database
                WHERE datname = current_database()
            """)
            row = cursor.fetchone()
            if row:
                metrics['cache_hit_ratio'] = float(row['hit_ratio'] or 0)
                metrics['database_size'] = row['size']
            
            # Long running queries
            cursor.execute("""
                SELECT 
                    pid,
                    EXTRACT(EPOCH FROM (now() - query_start))::int as duration_sec,
                    state,
                    LEFT(query, 100) as query_preview
                FROM pg_stat_activity
                WHERE state != 'idle'
                  AND query_start < now() - interval '5 minutes'
                  AND pid != pg_backend_pid()
                ORDER BY duration_sec DESC
                LIMIT 5
            """)
            for row in cursor.fetchall():
                metrics['long_queries'].append({
                    'pid': row['pid'],
                    'duration_sec': row['duration_sec'],
                    'state': row['state'],
                    'query': row['query_preview']
                })
            
            # Replication lag (if replica)
            if self.config.get('read_only', False):
                cursor.execute("""
                    SELECT EXTRACT(EPOCH FROM (now() - pg_last_xact_replay_timestamp()))::int as lag_sec
                """)
                row = cursor.fetchone()
                if row and row['lag_sec'] is not None:
                    metrics['replication']['lag_seconds'] = row['lag_sec']
            
            cursor.close()
            conn.close()
            metrics['status'] = 'SUCCESS'
            
        except Exception as e:
            metrics['status'] = 'ERROR'
            metrics['error'] = str(e)
            logging.error(f"PostgreSQL {self.name}: {e}")
        
        return metrics
    
    def _get_password(self):
        password = self.config.get('password', '')
        if password.startswith('${') and password.endswith('}'):
            env_var = password[2:-1]
            return os.environ.get(env_var, '')
        return password


def load_config(config_file):
    """Load YAML configuration"""
    with open(config_file, 'r') as f:
        return yaml.safe_load(f)


def collect_environment_metrics(env_name, env_config, thresholds):
    """Collect metrics for all databases in an environment"""
    logging.info(f"Collecting metrics for {env_name} environment...")
    
    results = {
        'name': env_config['name'],
        'databases': []
    }
    
    # Use ThreadPoolExecutor for parallel collection
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        
        for db_config in env_config.get('databases', []):
            db_type = db_config['type']
            
            if db_type == 'sqlserver':
                monitor = SQLServerMonitor(db_config, thresholds.get('sqlserver', {}))
            elif db_type == 'snowflake':
                monitor = SnowflakeMonitor(db_config, thresholds.get('snowflake', {}))
            elif db_type == 'postgresql':
                monitor = PostgreSQLMonitor(db_config, thresholds.get('postgresql', {}))
            else:
                logging.warning(f"Unknown database type: {db_type}")
                continue
            
            futures.append(executor.submit(monitor.collect_metrics))
        
        # Collect results
        for future in as_completed(futures):
            try:
                metrics = future.result()
                results['databases'].append(metrics)
            except Exception as e:
                logging.error(f"Error collecting metrics: {e}")
    
    return results


def generate_html_dashboard(all_metrics, config):
    """Generate multi-environment HTML dashboard"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Multi-Environment Monitoring Dashboard</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; }}
        .container {{ max-width: 1600px; margin: 0 auto; }}
        .header {{ background: white; padding: 20px 30px; border-radius: 10px; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
        .header h1 {{ color: #333; margin-bottom: 5px; }}
        .timestamp {{ color: #666; font-size: 14px; }}
        .env-section {{ background: white; border-radius: 10px; padding: 20px; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
        .env-title {{ font-size: 24px; color: #667eea; border-bottom: 2px solid #667eea; padding-bottom: 10px; margin-bottom: 15px; }}
        .db-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 15px; }}
        .db-card {{ background: #f9fafb; border-radius: 8px; padding: 15px; border-left: 4px solid #667eea; }}
        .db-card.error {{ border-left-color: #ef4444; }}
        .db-name {{ font-size: 18px; font-weight: bold; color: #333; margin-bottom: 10px; }}
        .db-type {{ display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: bold; margin-bottom: 10px; }}
        .db-type.sqlserver {{ background: #dbeafe; color: #1e40af; }}
        .db-type.snowflake {{ background: #dbeafe; color: #0369a1; }}
        .db-type.postgresql {{ background: #dbeafe; color: #075985; }}
        .metric {{ display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #e5e7eb; }}
        .metric-label {{ color: #666; font-size: 13px; }}
        .metric-value {{ font-weight: bold; color: #333; }}
        .status-success {{ color: #10b981; }}
        .status-warning {{ color: #f59e0b; }}
        .status-error {{ color: #ef4444; }}
        .badge {{ display: inline-block; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; }}
        .badge-success {{ background: #d1fae5; color: #065f46; }}
        .badge-error {{ background: #fee2e2; color: #991b1b; }}
        .refresh-info {{ text-align: center; color: white; margin-top: 20px; font-size: 14px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🖥️ Multi-Environment Database Monitoring Dashboard</h1>
            <div class="timestamp">Last Updated: {timestamp}</div>
        </div>
"""
    
    # Add each environment
    for env_metrics in all_metrics:
        env_name = env_metrics['name']
        databases = env_metrics['databases']
        
        html += f"""
        <div class="env-section">
            <div class="env-title">🌍 {env_name} Environment ({len(databases)} databases)</div>
            <div class="db-grid">
"""
        
        for db in databases:
            db_name = db.get('name', 'Unknown')
            db_type = db.get('type', 'unknown')
            status = db.get('status', 'UNKNOWN')
            
            card_class = 'db-card error' if status == 'ERROR' else 'db-card'
            
            html += f"""
                <div class="{card_class}">
                    <div class="db-name">{db_name}</div>
                    <span class="db-type {db_type}">{db_type.upper()}</span>
                    <span class="badge badge-{'success' if status == 'SUCCESS' else 'error'}">{status}</span>
"""
            
            if status == 'ERROR':
                html += f"""
                    <div class="metric">
                        <span class="metric-label">Error</span>
                        <span class="metric-value status-error">{db.get('error', 'Unknown error')[:50]}</span>
                    </div>
"""
            else:
                # SQL Server metrics
                if db_type == 'sqlserver' and 'sessions' in db:
                    html += f"""
                    <div class="metric">
                        <span class="metric-label">Sessions</span>
                        <span class="metric-value">{db['sessions'].get('total', 0)}</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Blocked</span>
                        <span class="metric-value {'status-error' if db['sessions'].get('blocked', 0) > 0 else 'status-success'}">{db['sessions'].get('blocked', 0)}</span>
                    </div>
"""
                    if 'storage' in db and db['storage']:
                        html += f"""
                    <div class="metric">
                        <span class="metric-label">Storage Used</span>
                        <span class="metric-value">{db['storage'].get('used_percent', 0)}%</span>
                    </div>
"""
                
                # Snowflake metrics
                elif db_type == 'snowflake':
                    html += f"""
                    <div class="metric">
                        <span class="metric-label">Active Queries</span>
                        <span class="metric-value">{db.get('queries', {}).get('active', 0)}</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Credits (24h)</span>
                        <span class="metric-value">{sum(db.get('credits', {}).values()):.2f}</span>
                    </div>
"""
                    spill = db.get('spill', {})
                    if spill.get('queries_with_spill', 0) > 0:
                        html += f"""
                    <div class="metric">
                        <span class="metric-label">Query Spill</span>
                        <span class="metric-value status-warning">{spill['queries_with_spill']} queries, {spill.get('local_gb', 0)} GB</span>
                    </div>
"""
                
                # PostgreSQL metrics
                elif db_type == 'postgresql' and 'connections' in db:
                    conn = db['connections']
                    html += f"""
                    <div class="metric">
                        <span class="metric-label">Connections</span>
                        <span class="metric-value">{conn.get('current', 0)}/{conn.get('max', 0)} ({conn.get('usage_pct', 0)}%)</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Cache Hit Ratio</span>
                        <span class="metric-value status-success">{db.get('cache_hit_ratio', 0)}%</span>
                    </div>
"""
                    if 'replication' in db and 'lag_seconds' in db['replication']:
                        lag = db['replication']['lag_seconds']
                        html += f"""
                    <div class="metric">
                        <span class="metric-label">Replication Lag</span>
                        <span class="metric-value {'status-success' if lag < 60 else 'status-warning'}">{lag} sec</span>
                    </div>
"""
            
            html += """
                </div>
"""
        
        html += """
            </div>
        </div>
"""
    
    html += f"""
        <div class="refresh-info">
            🔄 Dashboard auto-refreshes every {config.get('dashboard', {}).get('refresh_interval', 300) // 60} minutes
        </div>
    </div>
    
    <script>
        setTimeout(() => location.reload(), {config.get('dashboard', {}).get('refresh_interval', 300)} * 1000);
    </script>
</body>
</html>
"""
    
    return html


def main():
    parser = argparse.ArgumentParser(description='Multi-Environment Database Monitoring Dashboard')
    parser.add_argument('--config', default='monitoring_environments.yaml', help='Config file path')
    parser.add_argument('--env', required=True, help='Environment(s) to monitor (dev,qa,prod or all)')
    parser.add_argument('--no-browser', action='store_true', help='Do not open browser')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    args = parser.parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(f'monitoring_{datetime.now().strftime("%Y%m%d")}.log'),
            logging.StreamHandler()
        ]
    )
    
    # Load configuration
    try:
        config = load_config(args.config)
    except FileNotFoundError:
        logging.error(f"Config file not found: {args.config}")
        sys.exit(1)
    
    # Determine which environments to monitor
    if args.env.lower() == 'all':
        envs_to_monitor = [e for e, c in config['environments'].items() if c.get('enabled', True)]
    else:
        envs_to_monitor = [e.strip() for e in args.env.split(',')]
    
    # Collect metrics
    all_metrics = []
    for env_name in envs_to_monitor:
        if env_name not in config['environments']:
            logging.warning(f"Environment '{env_name}' not found in config")
            continue
        
        env_config = config['environments'][env_name]
        if not env_config.get('enabled', True):
            logging.info(f"Environment '{env_name}' is disabled, skipping")
            continue
        
        metrics = collect_environment_metrics(env_name, env_config, config.get('thresholds', {}))
        all_metrics.append(metrics)
    
    # Generate dashboard
    logging.info("Generating HTML dashboard...")
    html = generate_html_dashboard(all_metrics, config)
    
    output_file = config.get('dashboard', {}).get('output_file', 'monitoring_dashboard.html')
    output_path = Path(output_file).resolve()
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"\n✓ Dashboard generated successfully!")
    print(f"📊 File: {output_path}")
    
    if not args.no_browser and config.get('dashboard', {}).get('open_browser', True):
        print("🌐 Opening in browser...")
        webbrowser.open(f'file://{output_path}')
    
    logging.info("Dashboard generation complete")


if __name__ == '__main__':
    main()
