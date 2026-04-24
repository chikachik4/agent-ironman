import asyncio
import json
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
        self.model_id = settings.LLM_MODEL_EXECUTION

    def _call_llm(self, prompt: str) -> str:
        try:
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}],
                "system": "You are the 'Chaos Orchestrator' of Aegis-Chaos. You execute Chaos Engineering tests. Speak confidently and professionally in Korean, like a senior Chaos Engineer."
            })
            response = self.bedrock.invoke_model(
                body=body,
                modelId=self.model_id,
                accept="application/json",
                contentType="application/json"
            )
            return json.loads(response.get('body').read())['content'][0]['text']
        except Exception as e:
            return f"[Chaos LLM 오류]: {str(e)}"

    async def handle_chaos_command(self, data: dict):
        user_text = data.get("text", "")
        print(f"🔥 [Chaos Orchestrator] 장애 주입 명령 수신: {user_text}")
        
        # 1. 사용자의 명령어(의도)에 따라 주입할 카오스 종류 결정
        if "cpu" in user_text.lower() or "과부하" in user_text or "스트레스" in user_text:
            chaos_type = "StressChaos"
            chaos_name = "aegis-demo-cpu-stress"
            manifest = {
                "apiVersion": "chaos-mesh.org/v1alpha1",
                "kind": "StressChaos",
                "metadata": {"name": chaos_name, "namespace": "default"},
                "spec": {
                    "mode": "one",
                    "selector": {"namespaces": ["default"]},
                    "stressors": {"cpu": {"workers": 1, "load": 100}},
                    "duration": "60s"
                }
            }
        else:
            chaos_type = "PodChaos"
            chaos_name = "aegis-demo-pod-kill"
            manifest = {
                "apiVersion": "chaos-mesh.org/v1alpha1",
                "kind": "PodChaos",
                "metadata": {"name": chaos_name, "namespace": "default"},
                "spec": {
                    "action": "pod-kill",
                    "mode": "one",
                    "selector": {"namespaces": ["default"]}
                }
            }
        
        # 2. 클러스터에 장애 객체 생성
        action_result = "성공"
        try:
            # 먼저 이전 데모 객체가 있다면 삭제 시도
            try:
                k8s_client.custom_obj.delete_namespaced_custom_object(
                    group="chaos-mesh.org",
                    version="v1alpha1",
                    namespace="default",
                    plural=chaos_type.lower(),
                    name=chaos_name
                )
            except:
                pass # 없으면 패스
            
            # 장애 객체 생성
            k8s_client.custom_obj.create_namespaced_custom_object(
                group="chaos-mesh.org",
                version="v1alpha1",
                namespace="default",
                plural=chaos_type.lower(),
                body=manifest
            )
        except Exception as e:
            action_result = f"실패 (사유: {str(e)})"
            print(f"[Chaos Error] CRD 생성 실패: {e}")
            
            # 테스트 환경에서 권한/CRD 부재 시 데모(Mock) 동작 처리
            if "Not Found" in str(e) or "Forbidden" in str(e):
                print("🔥 [SYSTEM] Chaos Mesh CRD가 설치되지 않았거나 권한이 없습니다. 가상 장애 주입으로 시뮬레이션합니다.")
                action_result = "성공 (Mock 시뮬레이션)"

        # 3. LLM을 통한 결과 브리핑 작성
        prompt = f"사용자의 명령 '{user_text}'에 따라 '{chaos_type}' 카오스 실험을 실행했어. 실행 결과는 '{action_result}'야. 이 상황을 대시보드 관리자에게 멋지게 브리핑해줘."
        response_text = self._call_llm(prompt)
        
        # 4. 프론트엔드로 브리핑 발송
        await redis_client.publish("agent.outbound", {
            "sender": "Chaos Orchestrator",
            "text": response_text
        })

    async def start(self):
        print("🔥 [Chaos Orchestrator] 구동 시작 (Listening to 'agent.chaos'...)")
        self.task = await redis_client.subscribe("agent.chaos", self.handle_chaos_command)
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
