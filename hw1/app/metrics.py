import os
import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

# Чтение переменных окружения для обогащения метрик
POD_NUMBER = os.getenv("POD_NUMBER", "unknown")
DATACENTER = os.getenv("DATACENTER", "unknown")
SERVICE_NAME = os.getenv("SERVICE_NAME", "unknown")

COMMON_LABELS = ["pod_number", "datacenter", "service_name", "endpoint", "method"]

# Latency с перцентилями (VictoriaMetrics сам посчитает перцентили через histogram_quantile из бакетов)
LATENCY_HISTOGRAM = Histogram(
    "http_request_duration_seconds",
    "Request latency in seconds",
    labelnames=COMMON_LABELS
)

# Throughput (RPS) и Error rate (можно считать через одну метрику, группируя по status_code)
REQUESTS_COUNTER = Counter(
    "http_requests_total",
    "Total number of HTTP requests",
    labelnames=COMMON_LABELS + ["status_code"]
)

class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Не собираем метрики для самой ручки /metrics
        if request.url.path == "/metrics":
            return await call_next(request)

        method = request.method
        endpoint = request.url.path # fallback
        start_time = time.time()
        
        status_code = "500"
        try:
            response = await call_next(request)
            status_code = str(response.status_code)
            
            # Получаем шаблон пути (например, /items/{item_id} вместо /items/1)
            route = request.scope.get("route")
            if route:
                endpoint = route.path
        except Exception as e:
            raise e
        finally:
            process_time = time.time() - start_time
            
            labels = {
                "pod_number": POD_NUMBER,
                "datacenter": DATACENTER,
                "service_name": SERVICE_NAME,
                "endpoint": endpoint,
                "method": method
            }
            
            LATENCY_HISTOGRAM.labels(**labels).observe(process_time)
            REQUESTS_COUNTER.labels(**labels, status_code=status_code).inc()

        return response
