import asyncio
import json
import boto3
from infrastructure.redis_client import redis_client
from core.config import settings

class ReporterAgent:
    """
    카오스 실험의 결과를 구독하고 분석하여 사용자 친화적인 브리핑 리포트를 생성하는 에이전트.
    """
    def __init__(self):
        self.bedrock = boto3.client(
            service_name='bedrock-runtime',
            region_name=settings.AWS_REGION
        )
        # 리포팅은 전문성이 필요하므로 Sonnet 3.5 모델 사용
        self.model_sonnet = settings.LLM_MODEL_EXPERT

    def _generate_report(self, raw_data: dict) -> str:
        prompt = f"""
다음은 Chaos Orchestrator가 쿠버네티스에 장애를 주입한 결과 데이터입니다.
이 데이터를 분석하여 대시보드를 보고 있는 인프라 관리자에게 보고할 매우 전문적이고 깔끔한 브리핑 텍스트를 작성해주세요.

[실행 결과 데이터]
{json.dumps(raw_data, ensure_ascii=False, indent=2)}

규칙:
1. 어떤 파드(또는 리소스)에 어떤 종류의 카오스 공격이 들어갔는지 명확히 명시할 것.
2. 성공/실패 여부를 판단하고 후속 조치나 상황을 1~2문장으로 덧붙일 것.
3. 마크다운 없이 평문(또는 가벼운 이모지)으로 작성할 것.
4. SRE 전문가처럼 정중하고 확신에 찬 한국어 톤을 유지할 것.
"""
        try:
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 500,
                "messages": [{"role": "user", "content": prompt}],
            })
            response = self.bedrock.invoke_model(
                body=body,
                modelId=self.model_sonnet,
                accept="application/json",
                contentType="application/json"
            )
            return json.loads(response.get('body').read())['content'][0]['text']
        except Exception as e:
            return f"❌ [리포팅 오류] 결과를 생성하는 중 문제가 발생했습니다: {str(e)}"

    async def handle_report_event(self, data: dict):
        print(f"📝 [Reporter Agent] 카오스 결과 데이터 수신: {data.get('action_result', 'N/A')}")
        
        # 진행 상태 알림
        await redis_client.publish("agent.outbound", {
            "sender": "Reporter Agent",
            "text": "카오스 실험 결과를 종합하여 리포트를 작성 중입니다..."
        })
        
        # LLM을 활용한 리포트 생성
        report_text = self._generate_report(data)
        
        # 최종 리포트 발송
        await redis_client.publish("agent.outbound", {
            "sender": "Reporter Agent",
            "text": report_text
        })

    async def start(self):
        print("📝 [Reporter Agent] 구동 시작 (Listening to 'agent.report'...)")
        self.task = await redis_client.subscribe("agent.report", self.handle_report_event)
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
