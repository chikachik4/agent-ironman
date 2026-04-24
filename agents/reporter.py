import asyncio
import json
from strands import Agent
from strands.models import BedrockModel
from infrastructure.redis_client import redis_client
from core.config import settings


class ReporterAgent:
    """
    Strands Agent 기반으로 카오스 실험 결과를 분석하여
    사용자 친화적인 브리핑 리포트를 생성하는 에이전트.
    """

    SYSTEM_PROMPT = (
        "You are the 'Reporter Agent' of the Aegis-Chaos system. "
        "You are a professional SRE analyst. "
        "Your job is to analyze chaos experiment results and produce a clear, "
        "professional post-mortem briefing in Korean. "
        "Rules: "
        "1. Clearly state which resource was targeted and what kind of chaos was applied. "
        "2. Describe success/failure and suggest any follow-up actions in 1-2 sentences. "
        "3. Write in plain text with light emojis — no markdown. "
        "4. Maintain a confident, professional SRE tone."
    )

    def __init__(self):
        model = BedrockModel(
            model_id=settings.LLM_MODEL_EXPERT,
            region_name=settings.AWS_REGION,
        )
        self.agent = Agent(
            model=model,
            system_prompt=self.SYSTEM_PROMPT,
        )

    async def handle_report_event(self, data: dict):
        print(f"📝 [Reporter Agent] 카오스 결과 데이터 수신: {data.get('action_result', 'N/A')[:100]}")

        await redis_client.publish("agent.outbound", {
            "sender": "Reporter Agent",
            "text": "카오스 실험 결과를 종합하여 리포트를 작성 중입니다..."
        })

        prompt = (
            "다음은 Chaos Orchestrator가 실행한 카오스 실험 결과입니다.\n"
            "이 내용을 바탕으로 인프라 관리자에게 보고할 브리핑을 작성해주세요.\n\n"
            f"[실행 결과]\n{json.dumps(data, ensure_ascii=False, indent=2)}"
        )

        # Strands Agent 동기 호출 → asyncio.to_thread로 비동기 통합
        result = await asyncio.to_thread(self.agent, prompt)
        report_text = str(result)

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
