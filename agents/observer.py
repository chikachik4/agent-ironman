import asyncio
import json
import boto3
from infrastructure.redis_client import redis_client
from infrastructure.prometheus_client import prom_client
from core.config import settings

class ObserverAgent:
    """
    주기적으로 인프라 지표(Prometheus)를 감시하고, 이상 징후 발생 시 
    LLM을 통해 원인을 1차 분석하여 대시보드에 선제적으로 경고 알림을 보냅니다.
    """
    def __init__(self):
        self.bedrock = boto3.client(
            service_name='bedrock-runtime',
            region_name=settings.AWS_REGION
        )
        self.model_id = settings.LLM_MODEL_ROUTING 

    def _call_llm(self, prompt: str) -> str:
        """AWS Bedrock Claude 모델 호출"""
        try:
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}],
                "system": "You are the 'Observer Agent' of Aegis-Chaos. You are a vigilant monitoring system. Alert anomalies strictly but professionally in Korean. Keep it under 3 sentences."
            })
            response = self.bedrock.invoke_model(
                body=body,
                modelId=self.model_id,
                accept="application/json",
                contentType="application/json"
            )
            return json.loads(response.get('body').read())['content'][0]['text']
        except Exception as e:
            return f"오류 발생 (Observer LLM): {str(e)}"

    async def check_metrics_loop(self):
        """15초마다 메트릭을 확인하는 백그라운드 루프 (실무에서는 1분~5분)"""
        while True:
            await asyncio.sleep(15)  # 빠른 테스트를 위해 15초로 설정
            print("👁️ [Observer Agent] Prometheus 메트릭 스캐닝 중...")
            
            # PromQL: 조금 전 터미널에서 존재가 완벽히 증명된 cAdvisor의 노드 전체 CPU 메트릭(id="/") 사용
            query = 'sum(rate(container_cpu_usage_seconds_total{id="/"}[1m]))'
            data = await prom_client.query_metric(query)
            
            results = data.get("data", {}).get("result", [])
            
            # 터미널에 간략한 지표 출력
            node_cpu_cores = 0.0
            if results:
                node_cpu_cores = float(results[0]['value'][1])
                print(f"   ↳ [현재 서버 전체 CPU 사용량] {node_cpu_cores:.2f} 코어")
            else:
                print("   ↳ [현재 서버 CPU] 수집된 데이터 없음 (프로메테우스 확인 필요)")

            # 파이썬 레벨에서 서버 CPU가 0.5 코어 이상 사용될 경우 알림 트리거
            if node_cpu_cores > 0.5:
                print("👁️ [Observer Agent] 이상 징후 탐지! LLM 분석 요청 중...")
                prompt = f"서버의 전체 CPU 사용량이 {node_cpu_cores:.2f} 코어로 비정상적으로 높게 감지되었어. 대시보드를 보고 있는 관리자에게 선제적으로 위험을 경고하는 2문장의 알림 메시지를 작성해줘."
                
                alert_msg = self._call_llm(prompt)
                
                # 웹소켓(Redis)을 통해 클라이언트에 푸시 알림 전송
                await redis_client.publish("agent.outbound", {
                    "sender": "Observer Agent",
                    "text": f"🚨 [이상 탐지] {alert_msg}"
                })
                
                # 경고 발송 후 무한 알림 방지를 위해 60초 대기
                await asyncio.sleep(60)

    async def start(self):
        print("👁️ [Observer Agent] 구동 시작 (Monitoring Prometheus...)")
        self.task = asyncio.create_task(self.check_metrics_loop())
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            self.task.cancel()
