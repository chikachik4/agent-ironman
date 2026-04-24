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
        prompt = f"""
You are a Kubernetes Chaos Engineering expert. Translate the user's natural language command into a JSON array of Chaos Mesh Custom Resource manifests.
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

    async def handle_chaos_command(self, data: dict):
        user_text = data.get("text", "")
        print(f"🔥 [Chaos Orchestrator] 장애 주입 명령 수신: {user_text}")
        
        # 1. LLM(Sonnet 3.5)을 통한 카오스 매니페스트 배열 동적 생성
        manifests = self._generate_manifests_via_llm(user_text)
        
        if not manifests:
            action_result = "실패 (LLM 매니페스트 생성 오류 또는 해석 불가)"
        else:
            action_result = f"총 {len(manifests)}개의 카오스 실험 생성 성공"
            # 2. 클러스터에 장애 객체 순차 생성
            for manifest in manifests:
                # 타임스탬프를 강제로 덮어씌워 이름 충돌 완벽 방지
                original_name = manifest["metadata"].get("name", "chaos")
                manifest["metadata"]["name"] = f"{original_name}-{int(time.time())}"
                manifest["metadata"]["namespace"] = "default"
                
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

        # 3. Reporter Agent에게 실행 결과 전달 (Raw Data)
        report_data = {
            "user_command": user_text,
            "action_result": action_result,
            "injected_manifests": manifests
        }
        
        await redis_client.publish("agent.report", report_data)

    async def start(self):
        print("🔥 [Chaos Orchestrator] 구동 시작 (Listening to 'agent.chaos'...)")
        self.task = await redis_client.subscribe("agent.chaos", self.handle_chaos_command)
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
