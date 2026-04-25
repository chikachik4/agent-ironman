import asyncio
import json
from infrastructure.redis_client import redis_client
from infrastructure.prometheus_client import prom_client
from core.llm import BedrockLLMClient
from core.config import settings

class ObserverAgent:
    """
    주기적으로 인프라 지표(Prometheus)를 감시하고, 이상 징후 발생 시 
    LLM을 통해 원인을 1차 분석하여 대시보드에 선제적으로 경고 알림을 보냅니다.
    """
    def __init__(self):
        self.llm = BedrockLLMClient(use_sonnet=False)

    def _call_llm(self, prompt: str) -> str:
        """AWS Bedrock Claude 모델 호출"""
        try:
            system_prompt = "You are the 'Observer Agent' of Aegis-Chaos. You are a vigilant monitoring system. Alert anomalies strictly but professionally in Korean. Keep it under 3 sentences."
            return self.llm.generate(prompt, system_prompt=system_prompt, max_tokens=300)
        except Exception as e:
            return f"오류 발생 (Observer LLM): {str(e)}"

    async def check_metrics_loop(self):
        """15초마다 메트릭을 확인하는 백그라운드 루프 (실무에서는 1분~5분)"""
        while True:
            await asyncio.sleep(15)
            print("👁️ [Observer Agent] Prometheus 메트릭 스캐닝 중...")

            for cluster_name, prom_url in prom_client.targets.items():
                query = 'sum(rate(container_cpu_usage_seconds_total{id="/"}[2m]))'
                data = await prom_client.query_metric_from(cluster_name, prom_url, query)

                results = data.get("data", {}).get("result", [])

                node_cpu_cores = 0.0
                if results:
                    node_cpu_cores = float(results[0]['value'][1])
                    print(f"   ↳ [{cluster_name}] CPU: {node_cpu_cores:.2f} 코어")
                else:
                    print(f"   ↳ [{cluster_name}] 수집된 데이터 없음")

                # [Metrics Broadcast]
                await redis_client.publish("agent.outbound", {
                    "type": "metric",
                    "cluster": cluster_name,
                    "cpu": f"{(node_cpu_cores * 100):.1f}%" if results else "0.0%",
                    "memory": "6.8 GB"
                })

                if node_cpu_cores > 0.5:
                    print(f"👁️ [Observer Agent] 이상 징후 탐지! [{cluster_name}] LLM 분석 요청 중...")
                    prompt = (
                        f"[{cluster_name}] 클러스터의 전체 CPU 사용량이 {node_cpu_cores:.2f} 코어로 비정상적으로 높게 감지되었어. "
                        f"대시보드를 보고 있는 관리자에게 선제적으로 위험을 경고하는 2문장의 알림 메시지를 작성해줘."
                    )
                    alert_msg = self._call_llm(prompt)
                    await redis_client.publish("agent.outbound", {
                        "sender": "Observer Agent",
                        "text": f"🚨 [{cluster_name}] 이상 탐지 {alert_msg}"
                    })
                    await asyncio.sleep(60)

    async def start(self):
        print("👁️ [Observer Agent] 구동 시작 (Monitoring Prometheus...)")
        self.task = asyncio.create_task(self.check_metrics_loop())
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            self.task.cancel()
