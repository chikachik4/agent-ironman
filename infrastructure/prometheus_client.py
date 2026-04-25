import httpx
from core.config import settings

class PrometheusClient:
    def __init__(self):
        # 환경에 따라 모니터링 대상 Prometheus 엔드포인트 목록 구성
        if settings.ENVIRONMENT == "test" and "vpc1" in settings.CLUSTERS:
            self.targets = {
                "vpc1": settings.CLUSTERS["vpc1"].prometheus_url
            }
        else:
            # prod: CLUSTERS에 정의된 모든 활성 클러스터의 Prometheus URL 사용
            self.targets = {
                name: cfg.prometheus_url
                for name, cfg in settings.CLUSTERS.items()
                if cfg.is_active
            }
        # 기본 단일 쿼리용 (Observer Agent 호환)
        self.base_url = next(iter(self.targets.values())) if self.targets else "http://localhost:9090"
            
    async def query_metric(self, query: str) -> dict:
        """기본 Prometheus URL로 PromQL 쿼리 실행."""
        return await self.query_metric_from("vpc1", self.base_url, query)

    async def query_metric_from(self, cluster_id: str, prom_url: str, query: str) -> dict:
        """특정 Prometheus URL로 PromQL을 비동기로 실행하여 지표를 가져옵니다."""
        
        # [동적 노드 IP 할당] localhost로 설정되어 있지만 실제 운영 환경인 경우, K8s 노드의 실제 IP로 치환
        if "localhost" in prom_url and settings.ENVIRONMENT != "test":
            from infrastructure.k8s_client import k8s_client
            node_ip = k8s_client.get_worker_node_ip(cluster_id)
            if node_ip:
                prom_url = prom_url.replace("localhost", node_ip)
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{prom_url}/api/v1/query",
                    params={"query": query},
                    timeout=15.0
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            print(f"[Prometheus Error] Query failed ({prom_url}): {e}")
            # 연결 실패 시 빈 결과 반환 (오탐 방지)
            return {"status": "error", "data": {"resultType": "vector", "result": []}}

prom_client = PrometheusClient()
