# 🧪 Aegis-Chaos: Test Environment Specification (Sandbox)

이 문서는 현재 개발 및 테스트가 진행 중인 AWS EC2/K3s 기반의 샌드박스 환경을 정의합니다. 모든 에이전트 코드는 이 환경에서 즉시 실행 가능해야 합니다.

## 1. Network Topology (Sandbox)
- **VPC 1 (Target):** `10.0.0.0/16` 
  - 역할: 장애 주입 대상 클러스터 (K3s)
  - Private IP: `<VPC1_PRIVATE_IP>` (예: 10.0.11.180)
- **VPC 3 (Hub):** `10.2.0.0/16`
  - 역할: 에이전트 구동 및 통합 관제
  - Private IP: `<VPC3_PRIVATE_IP>` (예: 10.2.6.185)
- **Connectivity:** VPC Peering으로 연결됨 (모든 통신은 Private IP 기반).

## 2. Component Access (Ports)
| Service | Location | Access Port | Protocol |
| :--- | :--- | :--- | :--- |
| **K3s API** | VPC 1 | `6443` | HTTPS |
| **Prometheus** | VPC 1 | `30090` (NodePort) | HTTP |
| **Chaos Mesh** | VPC 1 | `3xxxx` (Dashboard) | HTTP |
| **Redis** | VPC 3 | `6379` | TCP |
| **Grafana** | VPC 3 | `3000` | HTTP |

## 3. Runtime Environment
- **Path:** `~/aegis-agents/`
- **Package Manager:** `uv` (Fast Python resolver)
- **Python Version:** 3.12 (Virtualenv: `.venv/`)
- **Kubeconfig:** `~/.kube/config` (VPC 1의 6443 포트를 가리키도록 설정됨)

## 4. Current Tooling Status
- **Chaos Mesh:** 설치 완료. `NetworkChaos` 등 CRD 사용 가능.
- **Prometheus:** `monitoring` 네임스페이스에 설치됨. `up` 쿼리 확인 완료.
- **Redis:** Docker 컨테이너 (`redis-hub`) 가동 중.

## 5. Development Constraints (Sandbox Mode)
1. **Remote K8s Control:** 에이전트는 VPC 3에서 구동되지만, VPC 1의 K8s 클러스터를 리모트로 제어한다.
2. **Resource Naming:** 모든 테스트 리소스는 `test-` 프리픽스를 사용하거나 명세서에 정의된 이름을 따른다.
3. **IAM:** Bedrock 호출을 위해 인스턴스에 부여된 IAM Role 또는 환경 변수의 Access Key를 사용한다.

## 6. Execution Flow (Test)
1. Local IDE (Vibe Coding) -> Git Push
2. VPC 3 -> `git pull`
3. VPC 3 -> `uv sync` (의존성 동기화)
4. VPC 3 -> `python -m agents.<agent_name>` 실행