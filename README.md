# 🛡️ Aegis-Chaos: Hybrid AIOps Multi-Agent System

Aegis-Chaos는 **AWS EKS와 온프레미스(K8s) 하이브리드 환경**의 자동화 및 AI 기반 장애 관제/분석을 위한 멀티 에이전트 시스템입니다. 
복잡한 인프라 관리를 AWS Bedrock (Claude 3.5) 기반의 AI 에이전트들이 돕고, React 기반의 채팅 대시보드를 통해 직관적으로 제어합니다.

## ✨ Key Features
- **Multi-Agent Architecture**: 자연어 해석(Interface), 지표 모니터링(Observer), 장애 주입(Chaos Orchestrator), 사후 분석 및 브리핑(Reporter) 에이전트 협업.
- **Context-Aware AI (상황 인지형 AI)**: K8s 클러스터의 실시간 상태(네임스페이스, 파드 라벨 등)를 프롬프트에 주입하여, 환각(Hallucination) 없는 정확한 타겟팅 및 지능적 인터랙션(Ask & Ready) 제공.
- **Delayed & Event-Driven Reporting**: 카오스 실험의 실제 지속 시간(Duration)을 계산하여 비동기로 대기한 후, 실험이 끝나는 시점에 맞춰 사후 브리핑 발송.
- **Hybrid Cluster Management**: Test(K3s)와 Production(AWS EKS & On-Premises) 클러스터를 단일 인터페이스에서 제어.
- **Real-time Dashboard**: FastAPI와 WebSocket을 통해 Redis Pub/Sub을 거치는 실시간 에이전트 통신. Datadog/Grafana 스타일의 프리미엄 UI 제공.
- **Serverless & Cost Optimized**: AWS ECS Fargate 기반으로 필요 시에만 가동(Scale-to-Zero) 가능한 단일 컨테이너 설계.

## 📁 Project Structure
- `api/`: FastAPI 서버 (React 정적 서빙 및 WebSocket 채팅 허브)
- `frontend/`: React + Vite 기반의 프리미엄 관제 대시보드 (좌측 Metrics, 우측 Agent Chat)
- `agents/`: AWS Bedrock(Claude 3.5) 연동 인공지능 에이전트 로직 (`interface.py` 등)
- `infrastructure/`: K8s API, Redis Pub/Sub, OpenSearch 통신 클라이언트
- `core/`: Multi-Cluster 및 Test/Prod 동적 환경 변수 설정 (`config.py`)

## 🚀 How to Run (Local Test)

1. **Redis Server 시작**
   ```bash
   docker start redis-hub
   # 컨테이너가 없다면: docker run -d --name redis-hub -p 6379:6379 redis:alpine
   ```
   
2. **Frontend UI 가동**
   ```bash
   cd frontend
   npm run dev
   ```
   
3. **FastAPI Backend 가동**
   ```bash
   uvicorn api.server:app --reload
   ```
   
4. **Interface Agent 구동**
   ```bash
   # AWS 자격 증명(Access Key) 및 Kubeconfig 설정 필요
   python -m agents.interface
   ```

## 📜 Specifications
자세한 시스템 및 환경 명세는 다음 문서들을 참조하세요:
- [PROJECT_SPEC.md](./PROJECT_SPEC.md) - 전체 프로젝트 비전 및 구조
- [TEST_ENVIRONMENT.md](./TEST_ENVIRONMENT.md) - 로컬/샌드박스 환경 명세
- [PRODUCTION_ENVIRONMENT.md](./PRODUCTION_ENVIRONMENT.md) - AWS 프로덕션 배포 명세
