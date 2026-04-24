from kubernetes import client, config
from core.config import settings

class MultiClusterK8sClient:
    def __init__(self):
        self._initialize_config()
        self.core_v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
        # Chaos Mesh CRD 제어를 위한 CustomObjectsApi
        self.custom_obj = client.CustomObjectsApi()
        
    def _initialize_config(self):
        """
        환경에 따라 Kubernetes 인증을 설정합니다.
        Sandbox(test): 로컬 ~/.kube/config 파일 사용 (VPC1 K3s 타겟)
        Production(prod): 로컬 kubeconfig 또는 Fargate In-Cluster Config 연동
        """
        try:
            # 우선 로컬 kubeconfig 로딩 시도 (샌드박스/로컬 개발용)
            config.load_kube_config()
            
            # [수정] TEST 환경에서는 로컬 kubeconfig의 현재 컨텍스트(EKS 등)를 무시하고
            # 명세서에 정의된 VPC1 K3s 주소로 강제 오버라이딩합니다.
            if settings.ENVIRONMENT == "test" and "vpc1" in settings.CLUSTERS:
                configuration = client.Configuration.get_default_copy()
                configuration.host = settings.CLUSTERS["vpc1"].api_url
                configuration.verify_ssl = False  # 사설 IP/K3s 통신을 위한 인증서 검증 무시
                client.Configuration.set_default(configuration)
                
            print(f"[SYSTEM] K8s 타겟 설정 완료 (Endpoint: {client.Configuration.get_default_copy().host})")
        except Exception as e:
            print(f"[SYSTEM] kubeconfig 로딩 실패: {e}. In-cluster config를 시도합니다.")
            try:
                # AWS ECS Fargate 등 컨테이너 내부 환경인 경우
                config.load_incluster_config()
                print("[SYSTEM] K8s In-cluster config 로딩 완료.")
            except Exception as inner_e:
                print(f"[ERROR] K8s 인증 정보를 찾을 수 없습니다: {inner_e}")

    def get_pods(self, namespace: str = "default") -> list:
        """지정된 네임스페이스의 파드 상태를 조회합니다."""
        try:
            pods = self.core_v1.list_namespaced_pod(namespace)
            return [
                {
                    "name": pod.metadata.name,
                    "status": pod.status.phase,
                    "ip": pod.status.pod_ip,
                    "node": pod.spec.node_name,
                    "restarts": pod.status.container_statuses[0].restart_count if pod.status.container_statuses else 0
                }
                for pod in pods.items
            ]
        except Exception as e:
            print(f"[K8s Error] get_pods: {e}")
            print("⚠️ [SYSTEM] K8s 접근 실패. 테스트용 가상(Mock) 데이터를 반환합니다.")
            # 로컬 네트워크 문제 시 LLM 동작을 확인하기 위한 가상 데이터
            return [
                {"name": "frontend-web-7f8a9c-2z8v", "status": "Running", "restarts": 0},
                {"name": "payment-backend-5897-xq2k", "status": "Running", "restarts": 1},
                {"name": "database-statefulset-0", "status": "Pending", "restarts": 0},
            ]

    def get_deployments(self, namespace: str = "default") -> list:
        """지정된 네임스페이스의 디플로이먼트 상태를 조회합니다."""
        try:
            deps = self.apps_v1.list_namespaced_deployment(namespace)
            return [
                {
                    "name": dep.metadata.name,
                    "replicas": dep.status.replicas,
                    "available": dep.status.available_replicas,
                    "unavailable": dep.status.unavailable_replicas
                }
                for dep in deps.items
            ]
        except Exception as e:
            print(f"[K8s Error] get_deployments: {e}")
            return []

# 싱글톤 인스턴스 (에이전트들이 공통으로 사용)
k8s_client = MultiClusterK8sClient()
