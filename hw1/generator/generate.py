import os
import time
import requests
import json

APP_URL = os.getenv("APP_URL", "http://app:8000")
GRAFANA_URL = os.getenv("GRAFANA_URL", "http://grafana:3000")
GRAFANA_USER = os.getenv("GRAFANA_USER", "admin")
GRAFANA_PASSWORD = os.getenv("GRAFANA_PASSWORD", "admin")

def wait_for_services():
    print("Waiting for app and Grafana to be ready...")
    # Health probe для приложения
    while True:
        try:
            r = requests.get(f"{APP_URL}/health", timeout=2)
            if r.status_code == 200:
                break
        except requests.exceptions.RequestException:
            pass
        time.sleep(2)

    # Health probe для Grafana
    while True:
        try:
            r = requests.get(f"{GRAFANA_URL}/api/health", timeout=2)
            if r.status_code == 200:
                break
        except requests.exceptions.RequestException:
            pass
        time.sleep(2)
    print("Services are ready.")

def create_service_account_and_token():
    """
    Создает Service Account в Grafana и генерирует токен.
    Скрипт использует Basic Auth админа для этой первоначальной операции.
    """
    auth = (GRAFANA_USER, GRAFANA_PASSWORD)
    sa_data = {"name": "dashboard-generator-sa", "role": "Admin"}
    
    # Проверяем, есть ли уже такой SA
    sa_id = None
    r = requests.get(f"{GRAFANA_URL}/api/serviceaccounts/search", auth=auth)
    if r.status_code == 200:
        for sa in r.json().get("serviceAccounts", []):
            if sa["name"] == sa_data["name"]:
                sa_id = sa["id"]
                break
    
    if not sa_id:
        r = requests.post(f"{GRAFANA_URL}/api/serviceaccounts", json=sa_data, auth=auth)
        r.raise_for_status()
        sa_id = r.json()["id"]

    # Создаем токен
    token_data = {"name": "gen-token-" + str(int(time.time()))}
    r = requests.post(f"{GRAFANA_URL}/api/serviceaccounts/{sa_id}/tokens", json=token_data, auth=auth)
    r.raise_for_status()
    return r.json()["key"]

def get_app_endpoints():
    """
    Получает список ручек от запущенного приложения в рантайме.
    """
    r = requests.get(f"{APP_URL}/endpoints")
    r.raise_for_status()
    return r.json()

def generate_dashboard_json(endpoints):
    """
    Программно генерирует модель дашборда для Grafana.
    """
    panels = []
    
    # Селекторы (Variables)
    templating = {
        "list": [
            {
                "name": "datacenter",
                "type": "query",
                "datasource": "VictoriaMetrics",
                "query": "label_values(http_requests_total, datacenter)",
                "includeAll": True,
                "multi": True
            },
            {
                "name": "pod_number",
                "type": "query",
                "datasource": "VictoriaMetrics",
                "query": "label_values(http_requests_total, pod_number)",
                "includeAll": True,
                "multi": True
            }
        ]
    }

    # Генерация панелей для каждой ручки
    grid_y = 0
    for idx, endpoint in enumerate(endpoints):
        # 1. Latency Panel с перцентилями (используем histogram_quantile и sum(rate) по бакетам)
        latency_panel = {
            "type": "timeseries",
            "title": f"Latency (p50, 75, 90, 95, 99) - {endpoint}",
            "gridPos": {"x": 0, "y": grid_y, "w": 8, "h": 8},
            "datasource": "VictoriaMetrics",
            "targets": []
        }
        for name, quantile in [("p50", 0.50), ("p75", 0.75), ("p90", 0.90), ("p95", 0.95), ("p99", 0.99)]:
            expr = f'histogram_quantile({quantile}, sum(rate(http_request_duration_seconds_bucket{{endpoint="{endpoint}", datacenter=~"$datacenter", pod_number=~"$pod_number"}}[1m])) by (le))'
            latency_panel["targets"].append({
                "expr": expr,
                "legendFormat": name
            })
            
        # 2. RPS Panel
        rps_panel = {
            "type": "timeseries",
            "title": f"Throughput (RPS) - {endpoint}",
            "gridPos": {"x": 8, "y": grid_y, "w": 8, "h": 8},
            "datasource": "VictoriaMetrics",
            "targets": [{
                "expr": f'sum(rate(http_requests_total{{endpoint="{endpoint}", datacenter=~"$datacenter", pod_number=~"$pod_number"}}[1m]))',
                "legendFormat": "RPS"
            }]
        }
        
        # 3. Errors Panel
        errors_panel = {
            "type": "timeseries",
            "title": f"Errors Rate - {endpoint}",
            "gridPos": {"x": 16, "y": grid_y, "w": 8, "h": 8},
            "datasource": "VictoriaMetrics",
            "targets": [{
                "expr": f'sum(rate(http_requests_total{{endpoint="{endpoint}", status_code=~"4..|5..", datacenter=~"$datacenter", pod_number=~"$pod_number"}}[1m])) by (status_code)',
                "legendFormat": "HTTP {{status_code}}"
            }]
        }

        panels.extend([latency_panel, rps_panel, errors_panel])
        grid_y += 8

    dashboard = {
        "dashboard": {
            "id": None,
            "uid": "auto-generated-dash",
            "title": "Service Metrics (Auto Generated)",
            "tags": ["hw1"],
            "timezone": "browser",
            "schemaVersion": 16,
            "version": 0,
            "refresh": "5s",
            "editable": False,  # Требование: Дашборд должно быть нельзя редактировать (non-editable).
            "templating": templating,
            "panels": panels
        },
        "overwrite": True
    }
    return dashboard

def upload_dashboard(token, dashboard_json):
    """
    Загружает дашборд в Grafana, используя Service Account Token
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    r = requests.post(f"{GRAFANA_URL}/api/dashboards/db", json=dashboard_json, headers=headers)
    r.raise_for_status()
    print("Dashboard uploaded successfully.")

if __name__ == "__main__":
    wait_for_services()
    token = create_service_account_and_token()
    print("Service account token successfully created/retrieved.")
    
    endpoints = get_app_endpoints()
    print(f"Discovered endpoints in runtime: {endpoints}")
    
    dash_json = generate_dashboard_json(endpoints)
    upload_dashboard(token, dash_json)
    print("Dashboard generation completed.")
