# 🏛️ Aegis-Chaos: Production Environment Specification (AWS Managed)

이 문서는 Aegis-Chaos 프로젝트의 최종 배포 환경인 AWS 기반 프로덕션 인프라를 정의합니다. 모든 코드는 이 환경의 가용성과 보안 정책을 준수해야 합니다.

## 1. Hybrid Network Topology (Production)
- **VPC 1 (Production Cloud):** `10.0.0.0/16`
  - 역할: 실제 워크로드 가동 (AWS EKS 클러스터)
  - 연결: VPC 3와 VPC Peering으로 연결됨.
- **VPC 2 (On-prem Simulation):** `10.1.0.0/16`
  - 역할: 온프레미스 환경 시뮬레이션 (Self-managed K8s)
  - 연결: **Tailscale Mesh VPN** 터널링. ECS Task 내 Tailscale Sidecar를 통해 통신.
- **VPC 3 (Shared Management Hub):** `10.2.0.0/16`
  - 역할: 컨트롤 타워 (ECS Fargate, Redis, OpenSearch, ALB)
  - 연결: 모든 제어 로직과 AI 분석이 수행되는 중앙 허브.

## 2. AWS Managed Services (Tech Stack)
| Service | Role | Implementation Detail |
| :--- | :--- | :--- |
| **AWS ECS Fargate** | Agent Compute | `Strands SDK` 기반 에이전트들이 개별 Task로 실행됨. |
| **Amazon EKS** | Target Cluster | VPC 1의 메인 타겟 클러스터. |
| **AWS Bedrock** | AI/LLM | Claude 3.5 Sonnet (분석용) / Haiku (실행용). VPC Endpoint 연결. |
| **ElastiCache Redis** | Message Broker | 에이전트 간 비동기 이벤트 및 상태 공유 (Pub/Sub). |
| **OpenSearch Service** | Unified Data Store | Vector Engine 사용. 실험 로그(Persistence) + RAG 벡터 검색 통합. |
| **Application LB** | External Access | VPC 3의 Grafana 및 관리 도구 외부 노출. |

## 3. Observability & Chaos Engine
- **Prometheus:** 각 타겟 클러스터(VPC 1, 2)에 로컬 설치. 에이전트가 내부망을 통해 `9090` 포트로 직접 쿼리.
- **Chaos Mesh:** 각 타겟 클러스터 내 설치. 에이전트가 `Custom Resource(CRD)`를 통해 장애 주입.
- **Grafana:** VPC 3에서 구동되며, 하이브리드 클러스터의 데이터를 통합 시각화.

## 4. Production Security & Policy
1. **Naming Convention:** 모든 리소스는 `bookjjeok-cloud-` 프리픽스를 사용함.
2. **IAM Roles:** 에이전트는 Access Key 대신 **ECS Task Role**을 통해 Bedrock, OpenSearch, EKS에 접근함.
3. **Lean Architecture:** 데이터 무결성보다 검색/분석 효율을 중시하여 **RDS 없이 OpenSearch로 데이터 계층을 단일화**함.
4. **Security Group:** IP 대역이 아닌 보안 그룹 ID 참조를 통한 최소 권한 원칙 적용.

## 5. Deployment Strategy
- **Containerization:** 모든 에이전트는 `uv`로 의존성이 관리된 Docker 이미지로 빌드됨.
- **Scalability:** 각 에이전트(Interface, Observer, Orchestrator, Analyst)는 부하에 따라 ECS 서비스 단위로 독립적 스케일링 수행.
- **Networking:** VPC 2 통신은 ECS Task 내에 Tailscale 컨테이너를 사이드카로 띄워 투명한 네트워크 경로 확보.

## 6. Key Operational Scenarios (RAG)
1. **Anomaly Detection:** Observer 에이전트가 이상 탐지 시 Redis에 이벤트 발행.
2. **RAG Analysis:** Analyst 에이전트가 OpenSearch에서 과거 유사 장애 사례를 벡터 검색(k-NN)하여 대응 가이드 생성.
3. **Feedback Loop:** 모든 분석 결과와 조치 사항은 다시 OpenSearch에 임베딩되어 저장됨.