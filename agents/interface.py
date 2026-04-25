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
def get_pod_status(namespace: str = "default", cluster_id: str = "vpc1") -> str:
    """
    쿠버네티스 파드 상태를 조회합니다.
    사용자가 파드 목록, 상태 확인, 클러스터 상태 등을 요청할 때 사용합니다.

    Args:
        namespace: 조회할 네임스페이스 (기본값: "default")
        cluster_id: 타겟 클러스터 식별자 (예: "vpc1", "vpc2")

    Returns:
        파드 목록 및 상태 JSON 문자열
    """
    # TODO: k8s_client에 cluster_id를 전달하는 로직 추가 필요 (현재는 기본 컨텍스트 사용)
    pods = k8s_client.get_pods(cluster_id=cluster_id, namespace=namespace)
    return json.dumps(pods, ensure_ascii=False, indent=2)


@tool
def get_cluster_context(cluster_id: str = "vpc1") -> str:
    """
    특정 K8s 클러스터의 네임스페이스 목록과 전체 파드 요약 정보를 반환합니다.
    카오스 실험 타겟 선정이나 클러스터 전반의 상태 파악이 필요할 때 사용합니다.
    
    Args:
        cluster_id: 타겟 클러스터 식별자 (예: "vpc1", "vpc2")

    Returns:
        네임스페이스 목록 및 파드+라벨 요약 JSON 문자열
    """
    # TODO: k8s_client에 cluster_id를 전달하는 로직 추가 필요
    namespaces = k8s_client.get_namespaces(cluster_id=cluster_id)
    pods_summary = k8s_client.get_all_pods_summary(cluster_id=cluster_id)
    
    cluster_name = settings.CLUSTERS[cluster_id].name if cluster_id in settings.CLUSTERS else "Unknown Cluster"
    
    return json.dumps({
        "cluster_id": cluster_id,
        "cluster_name": cluster_name,
        "namespaces": namespaces,
        "pods": pods_summary
    }, ensure_ascii=False, indent=2)


@tool
def delegate_chaos_injection(chaos_command: str, cluster_id: str = "vpc1") -> str:
    """
    카오스 장애 주입 명령을 Chaos Orchestrator 에이전트에게 위임합니다.
    사용자가 파드 CPU 스트레스, 파드 킬(kill) 등의 장애 주입을 요청하고
    타겟(대상 파드/서비스)과 지속 시간(몇 초)이 모두 명확히 확인된 경우에만 호출합니다.

    Args:
        chaos_command: 타겟과 지속 시간이 포함된 완전한 카오스 명령어 (예: "nginx 파드 4개에 120초 CPU 스트레스")
        cluster_id: 장애를 주입할 대상 클러스터 (예: "vpc1", "vpc2")

    Returns:
        위임 완료 확인 메시지
    """
    return f"__CHAOS_DELEGATE__:{cluster_id}:{chaos_command}"


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
        cluster_id = data.get("cluster_id", "vpc1")
        print(f"📥 [Interface Agent] 명령 수신 ({cluster_id}): {user_text}")

        await redis_client.publish("agent.outbound", {
            "sender": "Interface Agent",
            "text": "명령을 분석 중입니다...",
            "cluster_id": cluster_id
        })

        # LLM에게 현재 유저가 보고 있는 클러스터의 Context를 주입
        cluster_name = settings.CLUSTERS[cluster_id].name if cluster_id in settings.CLUSTERS else "Unknown Cluster"
        context_injected_prompt = f"[User is currently viewing cluster: {cluster_id} (Actual Name: {cluster_name})] {user_text}"

        # Strands Agent는 동기(sync) 호출 — asyncio.to_thread로 비동기 루프에서 안전하게 실행
        result = await asyncio.to_thread(self.agent, context_injected_prompt)
        response_text = str(result)

        # delegate_chaos_injection Tool이 호출된 경우 → Orchestrator로 전달
        chaos_flag = "__CHAOS_DELEGATE__:"
        if chaos_flag in response_text:
            parts = response_text.split(chaos_flag, 1)
            user_facing = parts[0].strip()
            # 포맷: cluster_id:command
            delegate_data = parts[1].strip()
            del_cluster_id, chaos_cmd = delegate_data.split(":", 1)
            
            if not user_facing:
                user_facing = f"🔥 [{del_cluster_id}] 파라미터 확인 완료. Chaos Orchestrator에게 장애 주입 명령을 하달했습니다."

            await redis_client.publish("agent.chaos", {"text": chaos_cmd, "cluster_id": del_cluster_id})
            await redis_client.publish("agent.outbound", {
                "sender": "Interface Agent",
                "text": user_facing,
                "cluster_id": del_cluster_id
            })
        else:
            await redis_client.publish("agent.outbound", {
                "sender": "Interface Agent",
                "text": response_text,
                "cluster_id": cluster_id
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
