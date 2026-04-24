import asyncio
import json
import boto3
from infrastructure.redis_client import redis_client
from infrastructure.k8s_client import k8s_client
from core.config import settings

class InterfaceAgent:
    """
    사용자의 자연어 명령을 해석하고, Action Plan을 수립하는 진입점 에이전트.
    (Strands SDK의 기반이 되는 Bedrock Claude 모델과 K8s Tool 호출을 담당합니다)
    """
    def __init__(self):
        # AWS Bedrock Runtime 클라이언트 초기화
        self.bedrock = boto3.client(
            service_name='bedrock-runtime',
            region_name=settings.AWS_REGION
        )
        # Interface Agent는 빠른 응답성을 위해 Claude 3.5 Haiku 사용
        self.model_id = settings.LLM_MODEL_EXECUTION 
        
    def _call_llm(self, prompt: str) -> str:
        """Bedrock Claude 모델을 호출하여 응답을 생성합니다."""
        try:
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 512,
                "messages": [{"role": "user", "content": prompt}],
                "system": "You are the 'Interface Agent' of the Aegis-Chaos system. You are a highly professional Site Reliability Engineer (SRE). Answer concisely and clearly in Korean."
            })
            
            response = self.bedrock.invoke_model(
                body=body,
                modelId=self.model_id,
                accept="application/json",
                contentType="application/json"
            )
            response_body = json.loads(response.get('body').read())
            return response_body['content'][0]['text']
        except Exception as e:
            return f"❌ [LLM 연동 오류] AWS Bedrock 호출에 실패했습니다: {str(e)}"

    def _classify_intent(self, user_text: str) -> str:
        """
        Claude 3 Haiku(경량 모델)를 사용하여 사용자의 의도를 3가지 중 하나로 정확히 분류합니다.
        """
        prompt = f"""
다음 사용자의 입력을 분석하여 의도(Intent)를 분류해.
오직 아래 3가지 카테고리 이름 중 하나만 출력해야 해. (다른 말은 절대 금지)

1. "POD_STATUS" : 쿠버네티스 파드의 상태나 목록을 조회하려는 의도.
2. "CHAOS_INJECTION" : 파드를 죽이거나, 삭제하거나, CPU 과부하, 스트레스, 카오스 장애를 주입하려는 의도.
3. "GENERAL" : 위 두 가지에 해당하지 않는 일반적인 질문이나 대화.

사용자 입력: "{user_text}"
분류 결과:"""
        intent = self._call_llm(prompt).strip()
        # 안전 장치: LLM이 이상하게 대답했을 경우 파싱
        if "POD_STATUS" in intent: return "POD_STATUS"
        if "CHAOS_INJECTION" in intent: return "CHAOS_INJECTION"
        return "GENERAL"

    async def handle_message(self, data: dict):
        """Redis 채널에서 수신한 메시지를 처리합니다."""
        user_text = data.get("text", "").lower()
        print(f"📥 [Interface Agent] 명령 수신: {user_text}")
        
        # 진행 상태 알림 (웹소켓 클라이언트로 전송)
        await redis_client.publish("agent.outbound", {
            "sender": "Interface Agent",
            "text": "명령을 분석 중입니다..."
        })
        
        # [의도 분석] 하이쿠(Haiku) 모델을 통한 Semantic Routing
        intent = self._classify_intent(user_text)
        print(f"🧠 [Interface Agent] 의도 분석 결과: {intent}")
        
        # [Skill 1] 파드 상태 조회 스킬 (Observer Agent 역할 일부 위임)
        if intent == "POD_STATUS":
            pods = k8s_client.get_pods("default")
            
            if not pods:
                response_text = "현재 클러스터(default 네임스페이스)에 파드가 없거나 통신에 실패했습니다."
            else:
                summary = f"현재 default 네임스페이스 파드 목록 ({len(pods)}개):\n"
                for p in pods:
                    summary += f"- {p['name']} (상태: {p['status']}, 재시작: {p['restarts']})\n"
                
                # LLM을 통해 이쁘게 요약
                prompt = f"다음 Kubernetes 파드 상태 데이터를 바탕으로 현재 클러스터 상태를 사용자에게 3줄 이내로 매우 전문적이고 깔끔하게 브리핑해줘:\n{summary}"
                response_text = self._call_llm(prompt)
                
        # [Skill 2] 장애 주입 스킬 (Chaos Orchestrator에게 역할 위임)
        elif intent == "CHAOS_INJECTION":
            # Orchestrator가 구독 중인 채널로 명령을 토스
            await redis_client.publish("agent.chaos", {"text": user_text})
            # Interface Agent는 위임 완료 메시지만 남김
            response_text = "🔥 Chaos Orchestrator 에이전트에게 장애 주입(Chaos Experiment) 명령을 하달했습니다. 오케스트레이터의 실행 결과를 기다려주세요."
                
        # [Skill 3] 일반 대화 및 기타 도메인
        else:
            prompt = f"사용자 명령: '{user_text}'. Aegis-Chaos 시스템의 Interface 에이전트로서 어떻게 조치할지 짧게 대답해줘."
            response_text = self._call_llm(prompt)

        # 최종 분석 결과 발송
        await redis_client.publish("agent.outbound", {
            "sender": "Interface Agent",
            "text": response_text
        })

    async def start(self):
        print("🤖 [Interface Agent] 구동 시작 (Listening to 'agent.inbound'...)")
        self.task = await redis_client.subscribe("agent.inbound", self.handle_message)
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass

if __name__ == "__main__":
    agent = InterfaceAgent()
    asyncio.run(agent.start())
