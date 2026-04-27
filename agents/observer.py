import asyncio
import json
from infrastructure.redis_client import redis_client
from infrastructure.prometheus_client import prom_client
from core.llm import BedrockLLMClient
from core.config import settings


class ObserverAgent:
    """
    주기적으로 인프라 지표(VPC3 중앙 Prometheus)를 감시하고, 이상 징후 발생 시
    LLM을 통해 원인을 1차 분석하여 대시보드에 선제적으로 경고 알림을 보냅니다.

    VPC1·VPC2의 Prometheus는 Remote Write로 VPC3에 메트릭을 전송하므로,
    에이전트는 VPC3 단일 엔드포인트에만 쿼리합니다.
    cluster 레이블({cluster="vpc1"}, {cluster="vpc2"})로 VPC를 구분합니다.
    """

    # 모니터링할 클러스터 레이블 목록 (Remote Write external_labels와 일치해야 함)
    MONITORED_CLUSTERS = ["vpc1", "vpc2"]

    def __init__(self):
        self.llm = BedrockLLMClient(use_sonnet=False)

    def _call_llm(self, prompt: str) -> str:
        """AWS Bedrock Claude 모델 호출"""
        try:
            system_prompt = (
                "You are the 'Observer Agent' of Aegis-Chaos. "
                "You are a vigilant monitoring system. "
                "Alert anomalies strictly but professionally in Korean. "
                "Keep it under 3 sentences."
            )
            return self.llm.generate(prompt, system_prompt=system_prompt, max_tokens=300)
        except Exception as e:
            return f"오류 발생 (Observer LLM): {str(e)}"

    async def check_metrics_loop(self):
        """15초마다 VPC3 중앙 Prometheus를 쿼리하는 백그라운드 루프"""
        while True:
            await asyncio.sleep(15)
            print("👁️ [Observer Agent] VPC3 중앙 Prometheus 메트릭 스캐닝 중...")

            for cluster in self.MONITORED_CLUSTERS:
                # cluster 레이블 필터 포함 PromQL — VPC3에 집계된 해당 클러스터 메트릭만 조회
                query = (
                    f'sum(rate(container_cpu_usage_seconds_total'
                    f'{{id="/",cluster="{cluster}"}}[2m]))'
                )
                data = await prom_client.query_metric(query)
                results = data.get("data", {}).get("result", [])

                node_cpu_cores = 0.0
                if results:
                    node_cpu_cores = float(results[0]["value"][1])
                    print(f"   ↳ [{cluster}] CPU: {node_cpu_cores:.2f} 코어")
                else:
                    print(f"   ↳ [{cluster}] 수집된 데이터 없음 (Remote Write 미연결 가능성)")

                # [Metrics Broadcast] — 대시보드로 메트릭 전달
                await redis_client.publish("agent.outbound", {
                    "type": "metric",
                    "cluster": cluster,
                    "cpu": f"{(node_cpu_cores * 100):.1f}%" if results else "0.0%",
                    "memory": "6.8 GB"
                })

                if node_cpu_cores > 0.5:
                    print(f"👁️ [Observer Agent] 이상 징후 탐지! [{cluster}] LLM 분석 요청 중...")
                    prompt = (
                        f"[{cluster}] 클러스터의 전체 CPU 사용량이 {node_cpu_cores:.2f} 코어로 "
                        f"비정상적으로 높게 감지되었어. "
                        f"대시보드를 보고 있는 관리자에게 선제적으로 위험을 경고하는 "
                        f"2문장의 알림 메시지를 작성해줘."
                    )
                    alert_msg = self._call_llm(prompt)
                    await redis_client.publish("agent.outbound", {
                        "sender": "Observer Agent",
                        "text": f"🚨 [{cluster}] 이상 탐지 {alert_msg}"
                    })
                    await asyncio.sleep(60)

    async def start(self):
        print("👁️ [Observer Agent] 구동 시작 (Monitoring VPC3 Central Prometheus...)")
        self.task = asyncio.create_task(self.check_metrics_loop())
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            self.task.cancel()
