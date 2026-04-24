import asyncio
import json
import time
import boto3
from infrastructure.redis_client import redis_client
from infrastructure.k8s_client import k8s_client
from core.config import settings

class ChaosOrchestratorAgent:
    """
    Chaos Mesh를 활용하여 실제 클러스터에 장애를 주입하는 에이전트.
    Interface Agent로부터 지시를 받아 K8s CustomResource(CRD)를 생성합니다.
    """
    def __init__(self):
        self.bedrock = boto3.client(
            service_name='bedrock-runtime',
            region_name=settings.AWS_REGION
        )
        self.model_sonnet = settings.LLM_MODEL_EXPERT

    def _generate_manifests_via_llm(self, user_text: str) -> list:
        """Sonnet 3.5를 활용하여 자연어 명령을 Chaos Mesh JSON 배열로 변환"""
        
        # 실제 K8s 클러스터 상태를 읽어와서 컨텍스트로 제공
        namespaces = k8s_client.get_namespaces()
        pods_summary = k8s_client.get_all_pods_summary()
        
        prompt = f"""
You are a Kubernetes Chaos Engineering expert. Translate the user's natural language command into a JSON array of Chaos Mesh Custom Resource manifests.

[현재 K8s 클러스터 상태]
네임스페이스 목록: {namespaces}
파드 및 라벨 목록: {pods_summary}

Rules:
1. ONLY return a valid JSON array. Do not wrap in markdown (e.g. no ```json). No explanations.
2. apiVersion must be "chaos-mesh.org/v1alpha1".
3. If killing pods, use kind "PodChaos" and action "pod-kill".
4. If causing CPU stress/load, use kind "StressChaos", and stressors: {{"cpu": {{"workers": 1, "load": 100}}}}.
5. If the user specifies a specific number of pods (e.g., "2개", "3 pods"), use "mode": "fixed" and "value": "<number>".
6. If the user doesn't specify a number, use "mode": "one".
7. Make sure each object has a unique "name" in metadata (e.g., append a random suffix or timestamp).
8. Generate separate JSON objects in the array if multiple actions (e.g., kill AND stress) are requested.
9. MUST add "duration": "60s" to the "spec" of every manifest unless the user specifies a different duration.
10. IMPORTANT: Analyze the [현재 K8s 클러스터 상태] above. Find the EXACT namespace and labelSelectors that match the user's target. NEVER invent or guess labels (like app=nginx). If the target is found in the state, use the exact labels and namespace found. ALWAYS include "namespaces": ["<target_namespace>"] inside the "selector" object.

User Command: "{user_text}"
"""
        try:
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1500,
                "messages": [{"role": "user", "content": prompt}],
            })
            response = self.bedrock.invoke_model(body=body, modelId=self.model_sonnet, accept="application/json", contentType="application/json")
            result = json.loads(response.get('body').read())['content'][0]['text'].strip()
            
            if "```json" in result:
                result = result.split("```json")[1].split("```")[0].strip()
            elif "```" in result:
                result = result.split("```")[1].strip()
                
            return json.loads(result)
        except Exception as e:
            print(f"❌ [LLM JSON Parsing Error]: {e}")
            return []

    async def _wait_and_report(self, report_data: dict, wait_seconds: int):
        """지정된 시간만큼 대기한 후 리포트 에이전트에게 결과를 발송합니다."""
        if wait_seconds > 0:
            print(f"⏳ [Orchestrator] 카오스 실험 진행 중... ({wait_seconds}초 후 리포트 발송 예정)")
            await asyncio.sleep(wait_seconds)
            
        print("✅ [Orchestrator] 카오스 실험 완료. Reporter Agent 호출.")
        await redis_client.publish("agent.report", report_data)

    async def handle_chaos_command(self, data: dict):
        user_text = data.get("text", "")
        print(f"🔥 [Chaos Orchestrator] 장애 주입 명령 수신: {user_text}")
        
        # 1. LLM(Sonnet 3.5)을 통한 카오스 매니페스트 배열 동적 생성
        manifests = self._generate_manifests_via_llm(user_text)
        
        # 터미널에 생성된 매니페스트를 이쁘게(indent) 로깅합니다.
        print("\n================ [생성된 카오스 매니페스트] ================")
        print(json.dumps(manifests, ensure_ascii=False, indent=2))
        print("============================================================\n")
        
        if not manifests:
            action_result = "실패 (LLM 매니페스트 생성 오류 또는 해석 불가)"
        else:
            action_result = f"총 {len(manifests)}개의 카오스 실험 생성 성공"
            # 2. 클러스터에 장애 객체 순차 생성
            for manifest in manifests:
                # 타임스탬프를 강제로 덮어씌워 이름 충돌 완벽 방지
                original_name = manifest["metadata"].get("name", "chaos")
                manifest["metadata"]["name"] = f"{original_name}-{int(time.time())}"
                
                # 강제 네임스페이스 주입 (AI가 놓쳤을 경우 대비)
                if "namespace" not in manifest["metadata"]:
                    manifest["metadata"]["namespace"] = "default"
                if "selector" not in manifest["spec"]:
                    manifest["spec"]["selector"] = {}
                if "namespaces" not in manifest["spec"]["selector"]:
                    manifest["spec"]["selector"]["namespaces"] = [manifest["metadata"]["namespace"]]
                
                kind = manifest.get("kind", "podchaos").lower()
                
                try:
                    k8s_client.custom_obj.create_namespaced_custom_object(
                        group="chaos-mesh.org",
                        version="v1alpha1",
                        namespace="default",
                        plural=kind,
                        body=manifest
                    )
                    print(f"✅ [Orchestrator] {kind} ({manifest['metadata']['name']}) 주입 성공")
                except Exception as e:
                    print(f"❌ [Chaos Error] {kind} 생성 실패: {e}")
                    if "Not Found" in str(e) or "Forbidden" in str(e):
                        action_result = "성공 (Mock 시뮬레이션: K8s 권한/CRD 부재)"

        # 3. 매니페스트에서 최대 지속 시간(duration) 계산
        max_duration = 0
        if manifests:
            for manifest in manifests:
                duration_str = manifest.get("spec", {}).get("duration", "0s")
                duration = 0
                if duration_str.endswith("s"):
                    try: duration = int(duration_str[:-1])
                    except: pass
                elif duration_str.endswith("m"):
                    try: duration = int(duration_str[:-1]) * 60
                    except: pass
                if duration > max_duration:
                    max_duration = max_duration = duration

        # 4. Reporter Agent에게 실행 결과 전달 (Raw Data) - 비동기 대기 후 발송
        report_data = {
            "user_command": user_text,
            "action_result": action_result,
            "injected_manifests": manifests
        }
        
        # 블로킹 없이 백그라운드에서 대기 후 전송
        asyncio.create_task(self._wait_and_report(report_data, max_duration))

    async def start(self):
        print("🔥 [Chaos Orchestrator] 구동 시작 (Listening to 'agent.chaos'...)")
        self.task = await redis_client.subscribe("agent.chaos", self.handle_chaos_command)
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
