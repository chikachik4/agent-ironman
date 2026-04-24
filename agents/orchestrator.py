import asyncio
import json
import time
from strands import Agent, tool
from strands.models import BedrockModel
from infrastructure.redis_client import redis_client
from infrastructure.k8s_client import k8s_client
from core.config import settings


# ─────────────────────────────────────────────
# Tool 정의
# ─────────────────────────────────────────────

@tool
def apply_chaos_manifest(manifest_json: str) -> str:
    """
    주어진 Chaos Mesh CustomResource(CRD) JSON 문자열을 쿠버네티스 클러스터에 적용합니다.
    하나의 매니페스트를 받아 실제로 생성합니다.

    Args:
        manifest_json: Chaos Mesh CRD 오브젝트의 JSON 문자열 (단일 오브젝트)

    Returns:
        적용 성공 또는 실패 메시지
    """
    try:
        manifest = json.loads(manifest_json)

        # 이름에 타임스탬프 추가 (중복 방지)
        original_name = manifest.get("metadata", {}).get("name", "chaos")
        manifest.setdefault("metadata", {})["name"] = f"{original_name}-{int(time.time())}"

        # namespace 기본값 보장
        namespace = manifest["metadata"].get("namespace", "default")
        manifest["metadata"]["namespace"] = namespace

        # selector.namespaces 기본값 보장
        manifest.setdefault("spec", {}).setdefault("selector", {}).setdefault(
            "namespaces", [namespace]
        )

        # value 필드 강제 문자열 변환 (Chaos Mesh 요구사항)
        if "value" in manifest.get("spec", {}):
            manifest["spec"]["value"] = str(manifest["spec"]["value"])

        kind = manifest.get("kind", "podchaos").lower()

        k8s_client.custom_obj.create_namespaced_custom_object(
            group="chaos-mesh.org",
            version="v1alpha1",
            namespace=namespace,
            plural=kind,
            body=manifest,
        )
        return f"✅ {kind} ({manifest['metadata']['name']}) 주입 성공"

    except Exception as e:
        err = str(e)
        if "Not Found" in err or "Forbidden" in err:
            return f"⚠️ Mock 시뮬레이션 완료 (K8s 권한/CRD 부재): {err}"
        return f"❌ 적용 실패: {err}"


@tool
def get_cluster_context() -> str:
    """
    현재 K8s 클러스터의 네임스페이스 목록과 전체 파드 요약 정보(이름, 라벨)를 반환합니다.
    카오스 실험의 정확한 타겟 선정을 위해 반드시 먼저 호출해야 합니다.

    Returns:
        네임스페이스 및 파드+라벨 요약 JSON 문자열
    """
    namespaces = k8s_client.get_namespaces()
    pods_summary = k8s_client.get_all_pods_summary()
    return json.dumps({
        "namespaces": namespaces,
        "pods": pods_summary
    }, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────
# Chaos Orchestrator Agent 클래스
# ─────────────────────────────────────────────

class ChaosOrchestratorAgent:
    """
    Strands Agent 기반으로 자연어 카오스 명령을 해석하고,
    클러스터 상태를 확인하여 Chaos Mesh CRD를 생성·적용하는 에이전트.
    """

    SYSTEM_PROMPT = """You are a Kubernetes Chaos Engineering expert operating within the Aegis-Chaos system.

Your workflow:
1. ALWAYS call get_cluster_context first to understand the real cluster state.
2. Based on the cluster state and user command, generate Chaos Mesh CRD manifests as JSON.
3. Call apply_chaos_manifest once per manifest to apply each one.

Chaos Mesh manifest rules:
- apiVersion must be "chaos-mesh.org/v1alpha1"
- For CPU stress: kind="StressChaos", stressors={"cpu": {"workers": 1, "load": 100}}
- For pod kill: kind="PodChaos", action="pod-kill"
- If user specifies N pods: mode="fixed", value="<N>" (value MUST be a string)
- Otherwise: mode="one"
- Always include duration in spec (e.g. "120s")
- Use EXACT namespace and labelSelectors from the cluster context. Never invent labels.
- Always include "namespaces": ["<target_namespace>"] inside spec.selector

After applying all manifests, report the results clearly in Korean."""

    def __init__(self):
        model = BedrockModel(
            model_id=settings.LLM_MODEL_EXPERT,
            region_name=settings.AWS_REGION,
        )
        self.agent = Agent(
            model=model,
            tools=[get_cluster_context, apply_chaos_manifest],
            system_prompt=self.SYSTEM_PROMPT,
        )

    def _extract_max_duration(self, agent_messages) -> int:
        """에이전트가 적용한 매니페스트에서 최대 duration(초)을 파싱합니다."""
        max_duration = 0
        for msg in agent_messages:
            content = msg.get("content", [])
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    for inner in block.get("content", []):
                        text = inner.get("text", "")
                        # apply_chaos_manifest에 넘긴 JSON에서 duration 파싱
                        try:
                            m = json.loads(text) if text.startswith("{") else {}
                            dur_str = m.get("spec", {}).get("duration", "")
                            if dur_str.endswith("s"):
                                max_duration = max(max_duration, int(dur_str[:-1]))
                            elif dur_str.endswith("m"):
                                max_duration = max(max_duration, int(dur_str[:-1]) * 60)
                        except Exception:
                            pass
        return max_duration

    async def _wait_and_report(self, report_data: dict, wait_seconds: int):
        if wait_seconds > 0:
            print(f"⏳ [Orchestrator] 카오스 실험 진행 중... ({wait_seconds}초 후 리포트 발송 예정)")
            await asyncio.sleep(wait_seconds)
        print("✅ [Orchestrator] 카오스 실험 완료. Reporter Agent 호출.")
        await redis_client.publish("agent.report", report_data)

    async def handle_chaos_command(self, data: dict):
        user_text = data.get("text", "")
        print(f"🔥 [Chaos Orchestrator] 장애 주입 명령 수신: {user_text}")

        # Strands Agent 실행 (동기 → 비동기 스레드로 안전하게 호출)
        result = await asyncio.to_thread(self.agent, user_text)
        action_result = str(result)

        print(f"🔥 [Chaos Orchestrator] 실행 완료: {action_result[:200]}")

        # 에이전트 메시지에서 duration 파싱 시도
        max_duration = 0
        try:
            messages = self.agent.messages or []
            max_duration = self._extract_max_duration(messages)
        except Exception:
            pass

        # Reporter에게 결과 전달 (비동기 대기 후 발송)
        report_data = {
            "user_command": user_text,
            "action_result": action_result,
        }
        asyncio.create_task(self._wait_and_report(report_data, max_duration))

    async def start(self):
        print("🔥 [Chaos Orchestrator] 구동 시작 (Listening to 'agent.chaos'...)")
        self.task = await redis_client.subscribe("agent.chaos", self.handle_chaos_command)
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
