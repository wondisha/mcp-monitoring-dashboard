#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MCP Database Monitoring - Web Dashboard
Generates an interactive HTML dashboard with charts and graphs
"""

import sys
import io
import pyodbc
import snowflake.connector
from datetime import datetime
import json

# Windows UTF-8 encoding fix
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Database Configurations
SQL_SERVER = 'TECHPC'
SQL_DATABASE = 'AdventureWorksDW2020'

SNOWFLAKE_ACCOUNT = 'EEJRNQB-JM98615'
SNOWFLAKE_USER = 'sfuser'
SNOWFLAKE_PASSWORD = 'Edno@16132023gabi'
SNOWFLAKE_WAREHOUSE = 'COMPUTE_WH'

def collect_sql_server_metrics():
    """Collect metrics from SQL Server"""
    metrics = {
        'sessions': {},
        'storage': {},
        'performance': {},
        'index_health': [],
        'top_queries': []
    }
    
    try:
        conn_str = f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={SQL_SERVER};DATABASE={SQL_DATABASE};Trusted_Connection=yes;'
        conn = pyodbc.connect(conn_str)
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
            'total': row[0],
            'running': row[1],
            'sleeping': row[2],
            'blocked': row[3]
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
        for row in cursor.fetchall():
            metrics['storage'] = {
                'name': row[0],
                'total_mb': round(row[1], 2),
                'used_mb': round(row[2], 2),
                'free_mb': round(row[1] - row[2], 2),
                'used_percent': round((row[2] / row[1]) * 100, 1)
            }
        
        # Performance Counters
        cursor.execute("""
            SELECT 
                counter_name,
                cntr_value
            FROM sys.dm_os_performance_counters
            WHERE object_name LIKE '%SQL Statistics%'
            AND counter_name IN ('Batch Requests/sec', 'SQL Compilations/sec', 'SQL Re-Compilations/sec')
            OR (object_name LIKE '%Buffer Manager%' AND counter_name IN ('Page life expectancy', 'Buffer cache hit ratio'))
        """)
        for row in cursor.fetchall():
            counter_key = row[0].replace(' ', '_').replace('/', '_').lower()
            metrics['performance'][counter_key] = row[1]
        
        # Top 10 Queries by CPU
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
                qs.total_logical_reads,
                qs.total_physical_reads
            FROM sys.dm_exec_query_stats qs
            CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) qt
            WHERE qt.dbid = DB_ID()
            ORDER BY qs.total_worker_time DESC
        """)
        for row in cursor.fetchall():
            metrics['top_queries'].append({
                'query': row[0][:100] + '...' if len(row[0]) > 100 else row[0],
                'executions': row[1],
                'cpu_ms': row[2],
                'elapsed_ms': row[3],
                'logical_reads': row[4],
                'physical_reads': row[5]
            })
        
        # Index Health
        cursor.execute("""
            SELECT TOP 10
                OBJECT_NAME(ips.object_id) as table_name,
                i.name as index_name,
                ips.avg_fragmentation_in_percent,
                ips.page_count
            FROM sys.dm_db_index_physical_stats(DB_ID(), NULL, NULL, NULL, 'LIMITED') ips
            INNER JOIN sys.indexes i ON ips.object_id = i.object_id AND ips.index_id = i.index_id
            WHERE ips.page_count > 100
            AND ips.avg_fragmentation_in_percent > 5
            ORDER BY ips.avg_fragmentation_in_percent DESC
        """)
        for row in cursor.fetchall():
            metrics['index_health'].append({
                'table': row[0],
                'index': row[1],
                'fragmentation': round(row[2], 2),
                'pages': row[3]
            })
        
        cursor.close()
        conn.close()
        metrics['status'] = 'SUCCESS'
        
    except Exception as e:
        metrics['status'] = 'ERROR'
        metrics['error'] = str(e)
    
    return metrics

def collect_snowflake_metrics():
    """Collect metrics from Snowflake"""
    metrics = {
        'warehouses': [],
        'credits': {},
        'storage': [],
        'queries': {},
        'spill': {}
    }
    
    try:
        conn = snowflake.connector.connect(
            user=SNOWFLAKE_USER,
            password=SNOWFLAKE_PASSWORD,
            account=SNOWFLAKE_ACCOUNT,
            warehouse=SNOWFLAKE_WAREHOUSE
        )
        cursor = conn.cursor()
        
        # Warehouse Utilization (Last 12 Hours)
        cursor.execute("""
            SELECT 
                warehouse_name,
                COUNT(*) as query_count,
                AVG(execution_time) / 1000 as avg_execution_sec,
                AVG(queued_overload_time) / 1000 as avg_queue_sec
            FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
            WHERE start_time >= DATEADD(HOUR, -12, CURRENT_TIMESTAMP())
            AND warehouse_name IS NOT NULL
            GROUP BY warehouse_name
            ORDER BY query_count DESC
        """)
        for row in cursor.fetchall():
            metrics['warehouses'].append({
                'name': row[0],
                'queries': row[1],
                'avg_exec': round(row[2], 2),
                'avg_queue': round(row[3], 2)
            })
        
        # Credit Consumption (Last 24 Hours)
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
        
        # Storage Usage
        cursor.execute("""
            SELECT 
                database_name,
                AVG(average_database_bytes) / (1024*1024*1024) as db_gb,
                AVG(average_failsafe_bytes) / (1024*1024*1024) as failsafe_gb
            FROM SNOWFLAKE.ACCOUNT_USAGE.DATABASE_STORAGE_USAGE_HISTORY
            WHERE usage_date >= DATEADD(DAY, -1, CURRENT_DATE())
            GROUP BY database_name
            HAVING db_gb > 0
            ORDER BY db_gb DESC
            LIMIT 10
        """)
        for row in cursor.fetchall():
            metrics['storage'].append({
                'database': row[0],
                'size_gb': round(row[1], 2),
                'failsafe_gb': round(row[2], 2)
            })
        
        # Active Queries
        cursor.execute("""
            SELECT COUNT(*) 
            FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
            WHERE start_time >= DATEADD(MINUTE, -5, CURRENT_TIMESTAMP())
            AND execution_status = 'RUNNING'
        """)
        metrics['queries']['active'] = cursor.fetchone()[0]
        
        # Query Spill Metrics (Last 12 Hours)
        cursor.execute("""
            SELECT 
                COUNT(*) as queries_with_spill,
                SUM(BYTES_SPILLED_TO_LOCAL_STORAGE) / (1024*1024*1024) as local_spill_gb,
                SUM(BYTES_SPILLED_TO_REMOTE_STORAGE) / (1024*1024*1024) as remote_spill_gb,
                AVG(BYTES_SCANNED) / (1024*1024*1024) as avg_scan_gb,
                AVG(PARTITIONS_SCANNED) as avg_partitions
            FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
            WHERE start_time >= DATEADD(HOUR, -12, CURRENT_TIMESTAMP())
            AND (BYTES_SPILLED_TO_LOCAL_STORAGE > 0 OR BYTES_SPILLED_TO_REMOTE_STORAGE > 0)
        """)
        row = cursor.fetchone()
        if row and row[0]:
            metrics['spill'] = {
                'queries_with_spill': row[0],
                'local_gb': round(row[1] or 0, 3),
                'remote_gb': round(row[2] or 0, 3),
                'avg_scan_gb': round(row[3] or 0, 3),
                'avg_partitions': round(row[4] or 0, 1)
            }
        else:
            metrics['spill'] = {
                'queries_with_spill': 0,
                'local_gb': 0,
                'remote_gb': 0,
                'avg_scan_gb': 0,
                'avg_partitions': 0
            }
        
        # Get detailed spill queries
        metrics['spill_details'] = []
        cursor.execute("""
            SELECT 
                query_id,
                LEFT(query_text, 100) as query_snippet,
                warehouse_name,
                database_name,
                start_time,
                ROUND(total_elapsed_time/1000, 2) as execution_sec,
                ROUND(bytes_scanned/1024/1024, 2) as mb_scanned,
                ROUND(bytes_spilled_to_local_storage/1024/1024, 2) as local_spill_mb,
                ROUND(bytes_spilled_to_remote_storage/1024/1024, 2) as remote_spill_mb,
                execution_status,
                CASE 
                    WHEN bytes_spilled_to_remote_storage > 0 THEN 'CRITICAL'
                    WHEN bytes_spilled_to_local_storage > 100*1024*1024 THEN 'HIGH'
                    WHEN bytes_spilled_to_local_storage > 10*1024*1024 THEN 'MODERATE'
                    WHEN bytes_spilled_to_local_storage > 0 THEN 'LOW'
                    ELSE 'NONE'
                END AS severity
            FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
            WHERE start_time >= DATEADD(HOUR, -12, CURRENT_TIMESTAMP())
            AND query_type = 'SELECT'
            AND (BYTES_SPILLED_TO_LOCAL_STORAGE > 0 OR BYTES_SPILLED_TO_REMOTE_STORAGE > 0)
            ORDER BY bytes_spilled_to_local_storage DESC, bytes_spilled_to_remote_storage DESC
            LIMIT 20
        """)
        for row in cursor.fetchall():
            metrics['spill_details'].append({
                'query_id': row[0],
                'query_snippet': row[1],
                'warehouse': row[2],
                'database': row[3],
                'start_time': row[4].strftime('%Y-%m-%d %H:%M:%S') if row[4] else '',
                'execution_sec': row[5],
                'mb_scanned': row[6],
                'local_spill_mb': row[7],
                'remote_spill_mb': row[8],
                'status': row[9],
                'severity': row[10]
            })
        
        cursor.close()
        conn.close()
        metrics['status'] = 'SUCCESS'
        
    except Exception as e:
        metrics['status'] = 'ERROR'
        metrics['error'] = str(e)
    
    return metrics

def generate_html_dashboard(sql_metrics, sf_metrics):
    """Generate interactive HTML dashboard"""
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Prepare data for charts
    sql_session_data = json.dumps([
        sql_metrics['sessions'].get('running', 0),
        sql_metrics['sessions'].get('sleeping', 0),
        sql_metrics['sessions'].get('blocked', 0)
    ])
    
    warehouse_names = json.dumps([w['name'] for w in sf_metrics['warehouses'][:5]])
    warehouse_queries = json.dumps([w['queries'] for w in sf_metrics['warehouses'][:5]])
    
    credit_names = json.dumps(list(sf_metrics['credits'].keys())[:5])
    credit_values = json.dumps(list(sf_metrics['credits'].values())[:5])
    
    total_credits = sum(sf_metrics['credits'].values())
    monthly_estimate = round(total_credits * 30, 2)
    
    storage_names = json.dumps([s['database'] for s in sf_metrics['storage'][:5]])
    storage_sizes = json.dumps([s['size_gb'] for s in sf_metrics['storage'][:5]])
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MCP Database Monitoring Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            min-height: 100vh;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        .header {{
            background: white;
            padding: 20px 30px;
            border-radius: 10px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .header h1 {{
            color: #333;
            margin-bottom: 5px;
        }}
        .header .timestamp {{
            color: #666;
            font-size: 14px;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }}
        .card {{
            background: white;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .card h2 {{
            color: #333;
            font-size: 18px;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #667eea;
        }}
        .metric {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 0;
            border-bottom: 1px solid #eee;
        }}
        .metric:last-child {{
            border-bottom: none;
        }}
        .metric-label {{
            color: #666;
            font-size: 14px;
        }}
        .metric-value {{
            font-size: 20px;
            font-weight: bold;
            color: #333;
        }}
        .metric-value.success {{
            color: #10b981;
        }}
        .metric-value.warning {{
            color: #f59e0b;
        }}
        .metric-value.danger {{
            color: #ef4444;
        }}
        .status-badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
        }}
        .status-success {{
            background: #d1fae5;
            color: #065f46;
        }}
        .status-error {{
            background: #fee2e2;
            color: #991b1b;
        }}
        .chart-container {{
            position: relative;
            height: 300px;
            margin-top: 20px;
        }}
        .progress-bar {{
            width: 100%;
            height: 20px;
            background: #e5e7eb;
            border-radius: 10px;
            overflow: hidden;
            margin-top: 5px;
        }}
        .progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            transition: width 0.3s ease;
        }}
        .table-container {{
            overflow-x: auto;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }}
        th, td {{
            padding: 10px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }}
        th {{
            background: #f9fafb;
            font-weight: 600;
            color: #374151;
            font-size: 14px;
        }}
        td {{
            color: #6b7280;
            font-size: 14px;
        }}
        tr:hover {{
            background: #f9fafb;
        }}
        .clickable {{
            cursor: pointer;
            transition: all 0.2s;
        }}
        .clickable:hover {{
            background: #eff6ff !important;
            transform: scale(1.01);
        }}
        .spill-metric {{
            cursor: pointer;
            transition: all 0.2s;
        }}
        .spill-metric:hover {{
            background: #f3f4f6;
            border-radius: 5px;
        }}
        .modal {{
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.5);
        }}
        .modal-content {{
            background: white;
            margin: 5% auto;
            padding: 30px;
            border-radius: 10px;
            width: 90%;
            max-width: 1200px;
            max-height: 80vh;
            overflow-y: auto;
        }}
        .modal-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 2px solid #667eea;
        }}
        .modal-header h2 {{
            margin: 0;
            color: #333;
        }}
        .close {{
            font-size: 28px;
            font-weight: bold;
            cursor: pointer;
            color: #999;
        }}
        .close:hover {{
            color: #333;
        }}
        .severity-badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 11px;
            font-weight: bold;
        }}
        .severity-CRITICAL {{
            background: #fee2e2;
            color: #991b1b;
        }}
        .severity-HIGH {{
            background: #fed7aa;
            color: #9a3412;
        }}
        .severity-MODERATE {{
            background: #fef3c7;
            color: #92400e;
        }}
        .severity-LOW {{
            background: #dbeafe;
            color: #1e3a8a;
        }}
        .query-code {{
            background: #f9fafb;
            padding: 10px;
            border-radius: 5px;
            font-family: monospace;
            font-size: 12px;
            overflow-x: auto;
            white-space: pre-wrap;
            word-wrap: break-word;
        }}
        .refresh-info {{
            text-align: center;
            color: white;
            margin-top: 20px;
            font-size: 14px;
        }}
        .auto-refresh {{
            background: rgba(255,255,255,0.2);
            padding: 10px 20px;
            border-radius: 5px;
            display: inline-block;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🖥️ MCP Database Monitoring Dashboard</h1>
            <div class="timestamp">Last Updated: {timestamp}</div>
        </div>
        
        <div class="grid">
            <!-- SQL Server Status -->
            <div class="card">
                <h2>SQL Server - TECHPC</h2>
                <div class="metric">
                    <span class="metric-label">Status</span>
                    <span class="status-badge status-{sql_metrics['status'].lower()}">{sql_metrics['status']}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Total Sessions</span>
                    <span class="metric-value">{sql_metrics['sessions'].get('total', 0)}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Running Sessions</span>
                    <span class="metric-value success">{sql_metrics['sessions'].get('running', 0)}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Blocked Sessions</span>
                    <span class="metric-value {'danger' if sql_metrics['sessions'].get('blocked', 0) > 0 else 'success'}">{sql_metrics['sessions'].get('blocked', 0)}</span>
                </div>
            </div>
            
            <!-- SQL Server Storage -->
            <div class="card">
                <h2>SQL Server Storage</h2>
                <div class="metric">
                    <span class="metric-label">Database</span>
                    <span class="metric-value" style="font-size: 16px;">{sql_metrics['storage'].get('name', 'N/A')}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Total Size</span>
                    <span class="metric-value">{sql_metrics['storage'].get('total_mb', 0)} MB</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Used Space</span>
                    <span class="metric-value">{sql_metrics['storage'].get('used_mb', 0)} MB</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Utilization</span>
                    <span class="metric-value">{sql_metrics['storage'].get('used_percent', 0)}%</span>
                </div>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: {sql_metrics['storage'].get('used_percent', 0)}%"></div>
                </div>
            </div>
            
            <!-- Snowflake Status -->
            <div class="card">
                <h2>Snowflake - JM98615</h2>
                <div class="metric">
                    <span class="metric-label">Status</span>
                    <span class="status-badge status-{sf_metrics['status'].lower()}">{sf_metrics['status']}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Active Queries</span>
                    <span class="metric-value success">{sf_metrics['queries'].get('active', 0)}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Active Warehouses</span>
                    <span class="metric-value">{len(sf_metrics['warehouses'])}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Total Storage</span>
                    <span class="metric-value">{round(sum(s['size_gb'] for s in sf_metrics['storage']), 2)} GB</span>
                </div>
            </div>
            
            <!-- Snowflake Credits -->
            <div class="card">
                <h2>Snowflake Credit Usage (24h)</h2>
                <div class="metric">
                    <span class="metric-label">Total Credits (24h)</span>
                    <span class="metric-value">{round(total_credits, 4)}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Est. Monthly</span>
                    <span class="metric-value {'warning' if monthly_estimate > 50 else 'success'}">{monthly_estimate}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Daily Average</span>
                    <span class="metric-value">{round(total_credits, 2)}</span>
                </div>
            </div>
        </div>
        
        <div class="grid">
            <!-- SQL Server Sessions Chart -->
            <div class="card">
                <h2>SQL Server Session Distribution</h2>
                <div class="chart-container">
                    <canvas id="sqlSessionsChart"></canvas>
                </div>
            </div>
            
            <!-- Warehouse Activity Chart -->
            <div class="card">
                <h2>Snowflake Warehouse Activity (Last 12 Hours)</h2>
                <div class="chart-container">
                    <canvas id="warehouseChart"></canvas>
                </div>
            </div>
            
            <!-- Credit Consumption Chart -->
            <div class="card">
                <h2>Credit Consumption by Warehouse (24h)</h2>
                <div class="chart-container">
                    <canvas id="creditChart"></canvas>
                </div>
            </div>
            
            <!-- Storage Chart -->
            <div class="card">
                <h2>Snowflake Database Storage</h2>
                <div class="chart-container">
                    <canvas id="storageChart"></canvas>
                </div>
            </div>
        </div>
        
        <!-- Performance Metrics Section -->
        <div class="grid">
            <!-- SQL Server Performance -->
            <div class="card">
                <h2>SQL Server Performance Counters</h2>
                {'<div class="metric"><span class="metric-label">Batch Requests/sec</span><span class="metric-value">' + str(sql_metrics['performance'].get('batch_requests_sec', 0)) + '</span></div>' if sql_metrics['performance'] else ''}
                {'<div class="metric"><span class="metric-label">SQL Compilations/sec</span><span class="metric-value">' + str(sql_metrics['performance'].get('sql_compilations_sec', 0)) + '</span></div>' if sql_metrics['performance'] else ''}
                {'<div class="metric"><span class="metric-label">Page Life Expectancy</span><span class="metric-value ' + ('success' if sql_metrics['performance'].get('page_life_expectancy', 0) > 300 else 'warning') + '">' + str(sql_metrics['performance'].get('page_life_expectancy', 0)) + ' sec</span></div>' if sql_metrics['performance'] else ''}
                {'<div class="metric"><span class="metric-label">Buffer Cache Hit Ratio</span><span class="metric-value success">' + str(round(sql_metrics['performance'].get('buffer_cache_hit_ratio', 0), 1)) + '%</span></div>' if sql_metrics['performance'] else ''}
            </div>
            
            <!-- Snowflake Query Spill -->
            <div class="card">
                <h2>Snowflake Query Spill (Last 12 Hours)</h2>
                <div class="metric spill-metric" onclick="showSpillDetails()">
                    <span class="metric-label">Queries with Spill 👁️</span>
                    <span class="metric-value {'warning' if sf_metrics['spill'].get('queries_with_spill', 0) > 0 else 'success'}">{sf_metrics['spill'].get('queries_with_spill', 0)}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Local Spill</span>
                    <span class="metric-value {'warning' if sf_metrics['spill'].get('local_gb', 0) > 1 else 'success'}">{sf_metrics['spill'].get('local_gb', 0)} GB</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Remote Spill</span>
                    <span class="metric-value {'danger' if sf_metrics['spill'].get('remote_gb', 0) > 0.1 else 'success'}">{sf_metrics['spill'].get('remote_gb', 0)} GB</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Avg Scan Size</span>
                    <span class="metric-value">{sf_metrics['spill'].get('avg_scan_gb', 0)} GB</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Avg Partitions Scanned</span>
                    <span class="metric-value">{sf_metrics['spill'].get('avg_partitions', 0)}</span>
                </div>
            </div>
        </div>
        
        <!-- Top Queries Table -->
        {'<div class="card"><h2>SQL Server Top 10 Queries by CPU</h2><div class="table-container"><table><thead><tr><th>Query</th><th>Executions</th><th>CPU (ms)</th><th>Duration (ms)</th><th>Logical Reads</th><th>Physical Reads</th></tr></thead><tbody>' + ''.join([f'<tr><td style="font-family: monospace; font-size: 12px;">{q["query"]}</td><td>{q["executions"]:,}</td><td><span class="metric-value {"danger" if q["cpu_ms"] > 10000 else "warning" if q["cpu_ms"] > 1000 else ""}">{q["cpu_ms"]:,}</span></td><td>{q["elapsed_ms"]:,}</td><td>{q["logical_reads"]:,}</td><td>{q["physical_reads"]:,}</td></tr>' for q in sql_metrics["top_queries"]]) + '</tbody></table></div></div>' if sql_metrics["top_queries"] else ''}
        
        <!-- Index Health Table -->
        {'<div class="card"><h2>SQL Server Index Health</h2><div class="table-container"><table><thead><tr><th>Table</th><th>Index</th><th>Fragmentation</th><th>Pages</th></tr></thead><tbody>' + ''.join([f'<tr><td>{idx["table"]}</td><td>{idx["index"]}</td><td><span class="metric-value {"danger" if idx["fragmentation"] > 30 else "warning" if idx["fragmentation"] > 10 else "success"}">{idx["fragmentation"]}%</span></td><td>{idx["pages"]:,}</td></tr>' for idx in sql_metrics["index_health"]]) + '</tbody></table></div></div>' if sql_metrics["index_health"] else '<div class="card"><h2>SQL Server Index Health</h2><p style="color: #10b981; padding: 20px; text-align: center;">✓ All indexes healthy (&lt;10% fragmentation)</p></div>'}
        
        <div class="refresh-info">
            <div class="auto-refresh">
                🔄 Dashboard auto-refreshes every 5 minutes | Next refresh: <span id="countdown">5:00</span>
            </div>
        </div>
    </div>
    
    <script>
        // SQL Server Sessions Chart
        const sqlCtx = document.getElementById('sqlSessionsChart').getContext('2d');
        new Chart(sqlCtx, {{
            type: 'doughnut',
            data: {{
                labels: ['Running', 'Sleeping', 'Blocked'],
                datasets: [{{
                    data: {sql_session_data},
                    backgroundColor: ['#10b981', '#3b82f6', '#ef4444'],
                    borderWidth: 0
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{
                        position: 'bottom'
                    }}
                }}
            }}
        }});
        
        // Warehouse Activity Chart
        const whCtx = document.getElementById('warehouseChart').getContext('2d');
        new Chart(whCtx, {{
            type: 'bar',
            data: {{
                labels: {warehouse_names},
                datasets: [{{
                    label: 'Query Count',
                    data: {warehouse_queries},
                    backgroundColor: 'rgba(102, 126, 234, 0.8)',
                    borderColor: 'rgba(102, 126, 234, 1)',
                    borderWidth: 1
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    y: {{
                        beginAtZero: true
                    }}
                }},
                plugins: {{
                    legend: {{
                        display: false
                    }}
                }}
            }}
        }});
        
        // Credit Consumption Chart
        const creditCtx = document.getElementById('creditChart').getContext('2d');
        new Chart(creditCtx, {{
            type: 'bar',
            data: {{
                labels: {credit_names},
                datasets: [{{
                    label: 'Credits Used',
                    data: {credit_values},
                    backgroundColor: 'rgba(245, 158, 11, 0.8)',
                    borderColor: 'rgba(245, 158, 11, 1)',
                    borderWidth: 1
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    y: {{
                        beginAtZero: true
                    }}
                }},
                plugins: {{
                    legend: {{
                        display: false
                    }}
                }}
            }}
        }});
        
        // Storage Chart
        const storageCtx = document.getElementById('storageChart').getContext('2d');
        new Chart(storageCtx, {{
            type: 'bar',
            data: {{
                labels: {storage_names},
                datasets: [{{
                    label: 'Storage (GB)',
                    data: {storage_sizes},
                    backgroundColor: 'rgba(16, 185, 129, 0.8)',
                    borderColor: 'rgba(16, 185, 129, 1)',
                    borderWidth: 1
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                indexAxis: 'y',
                scales: {{
                    x: {{
                        beginAtZero: true
                    }}
                }},
                plugins: {{
                    legend: {{
                        display: false
                    }}
                }}
            }}
        }});
        
        // Auto-refresh countdown
        let seconds = 300; // 5 minutes
        setInterval(() => {{
            seconds--;
            if (seconds <= 0) {{
                location.reload();
            }}
            const mins = Math.floor(seconds / 60);
            const secs = seconds % 60;
            document.getElementById('countdown').textContent = `${{mins}}:${{secs.toString().padStart(2, '0')}}`;
        }}, 1000);
        
        // Spill Details Modal
        function showSpillDetails() {{
            document.getElementById('spillModal').style.display = 'block';
        }}
        
        function closeSpillModal() {{
            document.getElementById('spillModal').style.display = 'none';
        }}
        
        // Close modal when clicking outside
        window.onclick = function(event) {{
            const modal = document.getElementById('spillModal');
            if (event.target == modal) {{
                modal.style.display = 'none';
            }}
        }}
    </script>
    
    <!-- Spill Details Modal -->
    <div id="spillModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h2>Query Spillage Details (Last 12 Hours)</h2>
                <span class="close" onclick="closeSpillModal()">&times;</span>
            </div>
            <div class="table-container">
                {'<table><thead><tr><th>Time</th><th>Warehouse</th><th>Database</th><th>Query Snippet</th><th>Execution (s)</th><th>MB Scanned</th><th>Local Spill (MB)</th><th>Remote Spill (MB)</th><th>Severity</th><th>Status</th></tr></thead><tbody>' + ''.join([f'<tr class="clickable"><td>{q["start_time"]}</td><td>{q["warehouse"]}</td><td>{q["database"]}</td><td><div class="query-code">{q["query_snippet"]}</div></td><td>{q["execution_sec"]}</td><td>{q["mb_scanned"]}</td><td><span class="metric-value {"warning" if q["local_spill_mb"] > 100 else ""}">{q["local_spill_mb"]}</span></td><td><span class="metric-value {"danger" if q["remote_spill_mb"] > 0 else ""}">{q["remote_spill_mb"]}</span></td><td><span class="severity-badge severity-{q["severity"]}">{q["severity"]}</span></td><td>{q["status"]}</td></tr>' for q in sf_metrics["spill_details"]]) + '</tbody></table>' if sf_metrics.get("spill_details") else '<p style="text-align: center; color: #10b981; padding: 40px;">✓ No queries with spillage found in the last 12 hours</p>'}
            </div>
        </div>
    </div>
</body>
</html>"""
    
    return html

def main():
    """Main function"""
    print("Collecting metrics from SQL Server...")
    sql_metrics = collect_sql_server_metrics()
    
    print("Collecting metrics from Snowflake...")
    sf_metrics = collect_snowflake_metrics()
    
    print("Generating HTML dashboard...")
    html = generate_html_dashboard(sql_metrics, sf_metrics)
    
    # Save HTML file
    output_file = "D:/Resume/monitoring_dashboard.html"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"\n✓ Dashboard generated successfully!")
    print(f"📊 File: {output_file}")
    print(f"🌐 Opening in browser...")
    
    # Open in default browser
    import webbrowser
    webbrowser.open(f'file:///{output_file}')

if __name__ == "__main__":
    main()
