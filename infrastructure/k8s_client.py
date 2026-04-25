from kubernetes import client, config
from core.config import settings

class MultiClusterK8sClient:
    def __init__(self):
        self.clients = {}  # { cluster_id: {"core": CoreV1Api, "apps": AppsV1Api, "custom": CustomObjectsApi} }
        self._initialize_config()
        
    def _initialize_config(self):
        """
        환경에 따라 Kubernetes 인증을 설정하고 각 클러스터별 API 클라이언트를 생성합니다.
        """
        import subprocess
        
        try:
            if settings.ENVIRONMENT != "test":
                eks_name = os.getenv("EKS_CLUSTER_NAME", "bookjjeok-test-eks-cluster")
                aws_region = settings.AWS_REGION
                
                print(f"[SYSTEM] EKS 클러스터({eks_name}) Kubeconfig 연동을 시도합니다...")
                try:
                    # EKS kubeconfig 업데이트 (자동으로 현재 컨텍스트를 EKS로 변경함)
                    result = subprocess.run(
                        ["aws", "eks", "update-kubeconfig", "--name", eks_name, "--region", aws_region],
                        check=True,
                        capture_output=True,
                        text=True
                    )
                    print(f"✅ [SYSTEM] Kubeconfig 갱신 성공: {result.stdout.strip()}")
                except subprocess.CalledProcessError as e:
                    print(f"❌ [ERROR] Kubeconfig 갱신 실패: {e.stderr}")
                except FileNotFoundError:
                    print("❌ [ERROR] AWS CLI가 설치되어 있지 않습니다.")

            # 우선 로컬 kubeconfig를 로딩 (AWS EKS 갱신 내역 포함)
            config.load_kube_config()
            
            # 클러스터별 클라이언트 객체 분리 생성
            for cid, cluster_cfg in settings.CLUSTERS.items():
                if not cluster_cfg.is_active:
                    continue
                    
                cfg = client.Configuration.get_default_copy()
                
                # VPC1 (EKS)의 경우 위에서 load_kube_config로 설정된 현재 컨텍스트를 그대로 사용
                # 추후 VPC2 (On-Prem)의 경우 API URL과 토큰을 직접 덮어씌우는 방식으로 확장 가능
                if cid == "vpc2":
                    cfg.host = cluster_cfg.api_url
                    cfg.verify_ssl = False  # 임시로 사설망 통신 시 검증 무시
                    # TODO: VPC2 접근을 위한 ServiceAccount Token 연동 추가 필요
                elif settings.ENVIRONMENT == "test" and cid == "vpc1":
                    # 테스트 샌드박스의 K3s 오버라이딩
                    cfg.host = cluster_cfg.api_url
                    cfg.verify_ssl = False
                
                api_client = client.ApiClient(configuration=cfg)
                self.clients[cid] = {
                    "core": client.CoreV1Api(api_client=api_client),
                    "apps": client.AppsV1Api(api_client=api_client),
                    "custom": client.CustomObjectsApi(api_client=api_client)
                }
                print(f"[SYSTEM] K8s 클라이언트 초기화 완료 ({cid} -> {cfg.host})")
                
        except Exception as e:
            print(f"[SYSTEM] Kubeconfig 로딩 실패: {e}. In-cluster config를 시도합니다.")
            try:
                # AWS ECS Fargate 등 컨테이너 내부 환경인 경우
                config.load_incluster_config()
                print("[SYSTEM] K8s In-cluster config 로딩 완료.")
            except Exception as inner_e:
                print(f"[ERROR] K8s 인증 정보를 찾을 수 없습니다: {inner_e}")

    def get_pods(self, cluster_id: str = "vpc1", namespace: str = "default") -> list:
        """지정된 클러스터와 네임스페이스의 파드 상태를 조회합니다."""
        if cluster_id not in self.clients:
            return []
            
        try:
            core_api = self.clients[cluster_id]["core"]
            pods = core_api.list_namespaced_pod(namespace)
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

    def get_namespaces(self, cluster_id: str = "vpc1") -> list:
        """클러스터의 모든 네임스페이스를 반환합니다."""
        if cluster_id not in self.clients:
            return ["default"]
            
        try:
            core_api = self.clients[cluster_id]["core"]
            ns_list = core_api.list_namespace()
            return [ns.metadata.name for ns in ns_list.items]
        except Exception as e:
            print(f"[K8s Error] get_namespaces: {e}")
            return ["default"]

    def get_all_pods_summary(self, cluster_id: str = "vpc1") -> list:
        """AI 컨텍스트 제공을 위해 클러스터 내 핵심 파드 정보를 반환합니다."""
        if cluster_id not in self.clients:
            return []
            
        try:
            core_api = self.clients[cluster_id]["core"]
            pods = core_api.list_pod_for_all_namespaces()
            summary = []
            for pod in pods.items:
                # kube-system 등 시스템 파드는 너무 많으므로 제외 가능 (여기서는 단순화를 위해 모두 포함)
                if pod.metadata.namespace not in ["kube-system", "chaos-mesh"]:
                    summary.append({
                        "namespace": pod.metadata.namespace,
                        "name": pod.metadata.name,
                        "labels": pod.metadata.labels or {}
                    })
            return summary
        except Exception as e:
            print(f"[K8s Error] get_all_pods_summary: {e}")
            return [{"namespace": "default", "name": "mock-pod", "labels": {"app": "mock"}}]

    def get_deployments(self, cluster_id: str = "vpc1", namespace: str = "default") -> list:
        """지정된 네임스페이스의 디플로이먼트 상태를 조회합니다."""
        if cluster_id not in self.clients:
            return []
            
        try:
            apps_api = self.clients[cluster_id]["apps"]
            deps = apps_api.list_namespaced_deployment(namespace)
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

    def get_topology(self, cluster_id: str = "vpc1", namespace: str = "default") -> dict:
        """클러스터의 Service와 Pod를 조회하여 토폴로지(React Flow 형식)를 생성합니다."""
        nodes = []
        edges = []
        
        if cluster_id not in self.clients:
            return {"nodes": nodes, "edges": edges}
            
        try:
            core_api = self.clients[cluster_id]["core"]
            services = core_api.list_namespaced_service(namespace)
            pods = core_api.list_namespaced_pod(namespace)
            
            # Y 좌표 계산을 위한 층별 배치 (단순화)
            svc_y = 50
            pod_y = 200
            svc_x_offset = 100
            pod_x_offset = 50

            # 1. Service 노드 생성
            for idx, svc in enumerate(services.items):
                svc_name = svc.metadata.name
                node_id = f"svc-{svc_name}"
                nodes.append({
                    "id": node_id,
                    "type": "input",
                    "position": {"x": svc_x_offset + (idx * 250), "y": svc_y},
                    "data": {"label": f"{svc_name}\n(Service)"},
                    "style": {
                        "background": "#1e293b",
                        "color": "#fff",
                        "border": "2px solid #3b82f6",
                        "borderRadius": "8px",
                        "padding": "10px"
                    }
                })

            # 2. Pod 노드 및 Edge 생성
            for p_idx, pod in enumerate(pods.items):
                pod_name = pod.metadata.name
                pod_id = f"pod-{pod_name}"
                pod_labels = pod.metadata.labels or {}
                
                # 상태에 따른 색상 결정
                status = pod.status.phase
                border_color = "#10b981" # Green (Running)
                if status == "Pending":
                    border_color = "#f59e0b" # Yellow
                elif status in ["Failed", "Unknown"]:
                    border_color = "#ef4444" # Red
                
                nodes.append({
                    "id": pod_id,
                    "type": "output",
                    "position": {"x": pod_x_offset + (p_idx * 200), "y": pod_y},
                    "data": {"label": f"{pod_name}\n({status})"},
                    "style": {
                        "background": "#1e293b",
                        "color": "#fff",
                        "border": f"1px solid {border_color}",
                        "borderRadius": "8px",
                        "padding": "8px"
                    }
                })

                # 매칭되는 Service 찾기 (selector 기준)
                for svc in services.items:
                    selector = svc.spec.selector
                    if not selector:
                        continue
                    
                    # Service의 selector의 모든 key-value가 Pod의 라벨에 포함되어 있는지 확인
                    is_match = all(pod_labels.get(k) == v for k, v in selector.items())
                    if is_match:
                        svc_node_id = f"svc-{svc.metadata.name}"
                        edges.append({
                            "id": f"e-{svc_node_id}-{pod_id}",
                            "source": svc_node_id,
                            "target": pod_id,
                            "animated": True,
                            "style": {"stroke": border_color}
                        })
                        
        except Exception as e:
            print(f"[K8s Error] get_topology: {e}")
            
        return {"nodes": nodes, "edges": edges}

    def get_worker_node_ip(self, cluster_id: str = "vpc1") -> str:
        """클러스터의 활성 상태인 워커 노드의 InternalIP(또는 ExternalIP)를 반환합니다. (NodePort 접근용)"""
        if cluster_id not in self.clients:
            return None
            
        try:
            core_api = self.clients[cluster_id]["core"]
            nodes = core_api.list_node()
            for node in nodes.items:
                # 노드가 Ready 상태인지 확인
                is_ready = any(cond.type == "Ready" and cond.status == "True" for cond in node.status.conditions)
                if is_ready:
                    for addr in node.status.addresses:
                        # InternalIP를 우선적으로 반환
                        if addr.type == "InternalIP":
                            return addr.address
        except Exception as e:
            print(f"[K8s Error] get_worker_node_ip: {e}")
            
        return None

# 싱글톤 인스턴스 (에이전트들이 공통으로 사용)
k8s_client = MultiClusterK8sClient()
