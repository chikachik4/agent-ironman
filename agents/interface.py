import asyncio
import json
from strands import Agent, tool
from strands.models import BedrockModel
from infrastructure.redis_client import redis_client
from infrastructure.k8s_client import k8s_client
from core.config import settings

# ─────────────────────────────────────────────
# Tool 정의: LLM이 필요에 따라 자동으로 선택·호출
# ─────────────────────────────────────────────

@tool
def get_pod_status(namespace: str = "default") -> str:
    """
    쿠버네티스 파드 상태를 조회합니다.
    사용자가 파드 목록, 상태 확인, 클러스터 상태 등을 요청할 때 사용합니다.

    Args:
        namespace: 조회할 네임스페이스 (기본값: "default")

    Returns:
        파드 목록 및 상태 JSON 문자열
    """
    pods = k8s_client.get_pods(namespace)
    return json.dumps(pods, ensure_ascii=False, indent=2)


@tool
def get_cluster_context() -> str:
    """
    현재 K8s 클러스터의 네임스페이스 목록과 전체 파드 요약 정보를 반환합니다.
    카오스 실험 타겟 선정이나 클러스터 전반의 상태 파악이 필요할 때 사용합니다.

    Returns:
        네임스페이스 목록 및 파드+라벨 요약 JSON 문자열
    """
    namespaces = k8s_client.get_namespaces()
    pods_summary = k8s_client.get_all_pods_summary()
    return json.dumps({
        "namespaces": namespaces,
        "pods": pods_summary
    }, ensure_ascii=False, indent=2)


@tool
def delegate_chaos_injection(chaos_command: str) -> str:
    """
    카오스 장애 주입 명령을 Chaos Orchestrator 에이전트에게 위임합니다.
    사용자가 파드 CPU 스트레스, 파드 킬(kill) 등의 장애 주입을 요청하고
    타겟(대상 파드/서비스)과 지속 시간(몇 초)이 모두 명확히 확인된 경우에만 호출합니다.
    파라미터가 불분명하면 이 Tool을 호출하지 말고 사용자에게 먼저 되물어보세요.

    Args:
        chaos_command: 타겟과 지속 시간이 포함된 완전한 카오스 명령어 (예: "nginx 파드 4개에 120초 CPU 스트레스")

    Returns:
        위임 완료 확인 메시지
    """
    # 이 함수의 실제 Redis publish는 async이므로 결과를 큐에 담아 handle_message에서 처리
    # 여기서는 플래그 역할만 함 — 실제 발행은 InterfaceAgent.handle_message에서 수행
    return f"__CHAOS_DELEGATE__:{chaos_command}"


# ─────────────────────────────────────────────
# Interface Agent 클래스
# ─────────────────────────────────────────────

class InterfaceAgent:
    """
    사용자의 자연어 명령을 해석하고, Strands Agent의 Tool Use 기반으로
    적절한 K8s 조회 또는 카오스 주입을 수행하는 진입점 에이전트.
    """
    def __init__(self):
        model = BedrockModel(
            model_id=settings.LLM_MODEL_EXPERT,
            region_name=settings.AWS_REGION,
        )
        self.agent = Agent(
            model=model,
            tools=[get_pod_status, get_cluster_context, delegate_chaos_injection],
            system_prompt=(
                "You are the 'Interface Agent' of the Aegis-Chaos system — "
                "a highly professional Site Reliability Engineer (SRE). "
                "Answer concisely and clearly in Korean. "
                "Use the available tools to fulfill user requests accurately. "
                "When chaos injection is requested but target or duration is unclear, "
                "use get_cluster_context to check the cluster state, then ask the user "
                "for the missing details. Do NOT call delegate_chaos_injection without "
                "confirmed target and duration."
            ),
        )

    async def handle_message(self, data: dict):
        """Redis 채널에서 수신한 메시지를 처리합니다."""
        user_text = data.get("text", "")
        print(f"📥 [Interface Agent] 명령 수신: {user_text}")

        await redis_client.publish("agent.outbound", {
            "sender": "Interface Agent",
            "text": "명령을 분석 중입니다..."
        })

        # Strands Agent는 동기(sync) 호출 — asyncio.to_thread로 비동기 루프에서 안전하게 실행
        result = await asyncio.to_thread(self.agent, user_text)
        response_text = str(result)

        # delegate_chaos_injection Tool이 호출된 경우 → Orchestrator로 전달
        chaos_flag = "__CHAOS_DELEGATE__:"
        if chaos_flag in response_text:
            # Tool 반환값에서 실제 명령어 추출
            chaos_cmd = response_text.split(chaos_flag, 1)[-1].strip()
            # LLM 응답 중 Tool 결과 이후의 텍스트(사용자에게 보여줄 메시지)를 분리
            user_facing = response_text.split(chaos_flag)[0].strip()
            if not user_facing:
                user_facing = "🔥 파라미터가 모두 확인되었습니다. Chaos Orchestrator에게 장애 주입 명령을 하달했습니다. 설정하신 시간이 경과한 후 최종 리포트가 도착할 예정입니다."

            await redis_client.publish("agent.chaos", {"text": chaos_cmd})
            await redis_client.publish("agent.outbound", {
                "sender": "Interface Agent",
                "text": user_facing
            })
        else:
            await redis_client.publish("agent.outbound", {
                "sender": "Interface Agent",
                "text": response_text
            })

        print(f"✅ [Interface Agent] 응답 완료")

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
