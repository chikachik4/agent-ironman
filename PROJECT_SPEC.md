# 🛡️ Aegis-Chaos: Hybrid AIOps Multi-Agent System Specification

## 1. Project Vision
- **Goal:** AWS EKS와 온프레미스(K8s) 하이브리드 환경 자동화 및 AI 기반 장애 분석.
- **Core Value:** 하이브리드 네트워크 통합, 에이전트 비종속 협업, RAG 기반 지능형 관제.

## 2. Hybrid Architecture
- **VPC 1 (Prod):** 10.0.0.0/16 (AWS EKS) -> VPC Peering 연결.
- **VPC 2 (On-prem):** 10.1.0.0/16 (k8s) -> VPC Peering으로 연결.
- **VPC 3 (Hub):** 10.2.0.0/16 (Management Hub) -> k3s (ArgoCD 인스턴스), Redis, OpenSearch.

## 3. Technology Stack (Actual)
- **Compute:**
  - **VPC 1:** AWS EKS (Production) - ArgoCD GitOps로 관리.
  - **VPC 2:** k8s (Production On-prem) - ArgoCD GitOps로 관리.
  - **VPC 3:** k3s (Test/Management) - ArgoCD 인스턴스, t3.medium.
- **Agent Framework:** **Strands SDK**
- **AI/LLM:** AWS Bedrock (Claude 3.5 Sonnet/Haiku)
- **Message Broker:** **Redis** (ElastiCache Redis, Async Event/Pub-Sub)
- **Data Store:** **AWS OpenSearch Service (Vector Engine)**
  - *Architecture:* RDS 없이 OpenSearch로 로그(Persistence)와 벡터 검색(RAG) 통합 (Lean Architecture).
- **Chaos Engine:** **Chaos Mesh** (VPC 1, 2 내 개별 설치)
- **Observability:** **Prometheus** (Target별 9090 직접 쿼리) + Grafana (VPC 3 통합 시각화)

## 4. Multi-Agent Role (Strands SDK 기반)
1. **Interface Agent:** 자연어 명령 해석 및 실행 계획(Action Plan) 수립.
2. **Observer Agent:** Prometheus 지표 감시 및 이상 징후 탐지.
3. **Chaos Orchestrator:** 하이브리드 경로별 Chaos Mesh API 제어 및 장애 주입.
4. **Reporter Agent:** 수집 데이터 + OpenSearch 과거 사례 기반 RAG 분석 리포트 생성.

## 5. Development & Operational Policy
- **Prefix:** 모든 리소스는 `bookjjeok-cloud-` 사용.
- **Security:** Security Group ID 참조 기반 최소 권한 원칙.
- **Cost:** 데모 시에만 ECS Task 가동 및 중앙 관리형 Prometheus 배제로 비용 최적화.