import httpx
from core.config import settings


class PrometheusClient:
    """
    VPC3 중앙 Prometheus 클라이언트.

    VPC1·VPC2의 로컬 Prometheus는 Remote Write를 통해
    VPC3 중앙 Prometheus로 메트릭을 전송합니다.
    에이전트는 이 클라이언트를 통해 VPC3 단일 엔드포인트만 쿼리합니다.

    PromQL에서 cluster 레이블({cluster="vpc1"} 등)로 VPC를 구분합니다.
    """

    def __init__(self):
        # VPC3 중앙 Prometheus 단일 URL
        self.base_url = settings.CENTRAL_PROMETHEUS_URL

    async def query_metric(self, query: str) -> dict:
        """중앙 Prometheus URL로 PromQL 쿼리를 실행합니다."""
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
            print(f"[Prometheus Error] Query failed ({self.base_url}): {e}")
            # 연결 실패 시 빈 결과 반환 (오탐 방지)
            return {"status": "error", "data": {"resultType": "vector", "result": []}}

    async def query_metric_for_cluster(self, cluster: str, query: str) -> dict:
        """
        특정 cluster 레이블을 PromQL에 삽입하여 쿼리합니다.
        cluster: 'vpc1' | 'vpc2' (Remote Write 시 external_labels로 설정된 값)
        """
        # PromQL selector에 cluster 레이블 필터 주입
        if "{" in query:
            labeled_query = query.replace("{", f'{{cluster="{cluster}",', 1)
        else:
            labeled_query = query + f'{{cluster="{cluster}"}}'
        return await self.query_metric(labeled_query)


prom_client = PrometheusClient()
