import httpx
from core.config import settings

class PrometheusClient:
    def __init__(self):
        # 환경(Test vs Prod)에 따라 Prometheus URL 자동 세팅
        if settings.ENVIRONMENT == "test" and "vpc1" in settings.CLUSTERS:
            self.base_url = settings.CLUSTERS["vpc1"].prometheus_url
        else:
            self.base_url = "http://localhost:9090"
            
    async def query_metric(self, query: str) -> dict:
        """PromQL을 비동기로 실행하여 지표를 가져옵니다."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/query",
                    params={"query": query},
                    timeout=15.0
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            print(f"[Prometheus Error] Query failed: {e}")
            # 데모/테스트 환경에서 프로메테우스가 안 뜰 경우 가상 데이터 반환
            return {
                "status": "error", 
                "error": str(e),
                "mock_data": [
                    {"metric": {"pod": "payment-api-7f8a"}, "value": [1616161616, "0.85"]},
                    {"metric": {"pod": "database-statefulset-0"}, "value": [1616161616, "0.92"]}
                ]
            }

prom_client = PrometheusClient()
