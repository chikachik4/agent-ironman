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
        self.model_haiku = settings.LLM_MODEL_ROUTING
        self.model_sonnet = settings.LLM_MODEL_EXPERT
        
    def _call_llm(self, prompt: str, use_sonnet: bool = False) -> str:
        """Bedrock Claude 모델을 호출하여 응답을 생성합니다."""
        model_id = self.model_sonnet if use_sonnet else self.model_haiku
        try:
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 512,
                "messages": [{"role": "user", "content": prompt}],
                "system": "You are the 'Interface Agent' of the Aegis-Chaos system. You are a highly professional Site Reliability Engineer (SRE). Answer concisely and clearly in Korean."
            })
            
            response = self.bedrock.invoke_model(
                body=body,
                modelId=model_id,
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
오직 아래 4가지 카테고리 이름 중 하나만 출력해야 해. (다른 말은 절대 금지)

1. "POD_STATUS" : 쿠버네티스 파드의 상태나 목록을 조회하려는 의도.
2. "CHAOS_INJECTION_READY" : 파드 죽이기, 과부하 등 카오스 장애 주입 의도이며, 타겟 대상과 '지속 시간(예: 60초)' 등의 필수 디테일이 구체적으로 명시된 경우.
3. "CHAOS_INJECTION_ASK" : 장애 주입 의도지만, 구체적으로 몇 개의 파드에, '몇 초 동안' 부하를 줄 지 등의 디테일이 명시되지 않아서 사용자에게 구체적인 수치를 되물어봐야 하는 경우.
4. "GENERAL" : 위 세 가지에 해당하지 않는 일반적인 질문이나 대화.

사용자 입력: "{user_text}"
분류 결과:"""
        intent = self._call_llm(prompt).strip()
        # 안전 장치
        if "POD_STATUS" in intent: return "POD_STATUS"
        if "CHAOS_INJECTION_READY" in intent: return "CHAOS_INJECTION_READY"
        if "CHAOS_INJECTION_ASK" in intent: return "CHAOS_INJECTION_ASK"
        if "CHAOS_INJECTION" in intent: return "CHAOS_INJECTION_ASK" # 애매하면 무조건 물어봄
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
                
                # LLM을 통해 이쁘게 요약 (고급 분석이므로 Sonnet 사용)
                prompt = f"다음 Kubernetes 파드 상태 데이터를 바탕으로 현재 클러스터 상태를 사용자에게 3줄 이내로 매우 전문적이고 깔끔하게 브리핑해줘:\n{summary}"
                response_text = self._call_llm(prompt, use_sonnet=True)
                
        # [Skill 2] 장애 주입 스킬 (디테일이 부족한 경우 되묻기)
        elif intent == "CHAOS_INJECTION_ASK":
            # 실제 K8s 클러스터 상태를 읽어와서 컨텍스트로 제공
            namespaces = k8s_client.get_namespaces()
            pods_summary = k8s_client.get_all_pods_summary()
            
            prompt = f"""사용자의 명령 '{user_text}'은 장애 주입을 하려는 의도이지만, 타겟이나 지속 시간 등 디테일이 부족해. 
현재 K8s 클러스터 상태를 참고해서 똑똑하게 되물어봐야 해.

[현재 K8s 클러스터 상태]
네임스페이스 목록: {namespaces}
파드 및 라벨 목록: {pods_summary}

위 상태를 보고, 사용자가 언급한 파드가 실제로 어디에 있는지 파악한 뒤 "현재 OOO 네임스페이스에 XXX 파드가 확인되는데, 이 파드들에 몇 초 동안 부하를 줄까요?" 처럼 아주 구체적이고 정중하게 1~2문장으로 되물어봐줘."""
            response_text = self._call_llm(prompt, use_sonnet=True)

        # [Skill 3] 장애 주입 스킬 (명확한 경우 바로 실행)
        elif intent == "CHAOS_INJECTION_READY":
            # Orchestrator가 구독 중인 채널로 명령을 토스
            await redis_client.publish("agent.chaos", {"text": user_text})
            # Interface Agent는 위임 완료 메시지만 남김
            response_text = "🔥 파라미터가 모두 확인되었습니다. Chaos Orchestrator에게 장애 주입(Chaos Experiment) 명령을 하달했습니다. 설정하신 시간이 경과한 후 최종 리포트가 도착할 예정입니다."
                
        # [Skill 3] 일반 대화 및 기타 도메인 (SRE 챗봇이므로 Sonnet 사용)
        else:
            prompt = f"사용자 명령: '{user_text}'. Aegis-Chaos 시스템의 Interface 에이전트로서 어떻게 조치할지 짧게 대답해줘."
            response_text = self._call_llm(prompt, use_sonnet=True)

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
