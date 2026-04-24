import asyncio
import uvicorn
import sys
import os

# 프로젝트 루트 경로 추가 (모듈 import 문제 방지)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from api.server import app
from agents.interface import InterfaceAgent
from agents.observer import ObserverAgent
from agents.orchestrator import ChaosOrchestratorAgent
from agents.reporter import ReporterAgent
from core.config import settings

async def start_background_agents():
    """
    모든 AI 에이전트들을 백그라운드 비동기 태스크로 구동합니다.
    (FastAPI와 메모리 및 이벤트 루프를 공유합니다)
    """
    print("🤖 [SYSTEM] AI 에이전트 인스턴스 초기화 중...")
    try:
        # 1. Interface Agent (명령어 해석 및 조치)
        interface_agent = InterfaceAgent()
        
        # 2. Observer Agent (이상 징후 상시 모니터링)
        observer_agent = ObserverAgent()
        
        # 3. Chaos Orchestrator Agent (장애 주입 수행)
        orchestrator_agent = ChaosOrchestratorAgent()
        
        # 4. Reporter Agent (카오스 결과 분석 및 브리핑)
        reporter_agent = ReporterAgent()
        
        # 모든 에이전트의 start() 메서드를 병렬로 실행
        await asyncio.gather(
            interface_agent.start(),
            observer_agent.start(),
            orchestrator_agent.start(),
            reporter_agent.start()
        )
    except Exception as e:
        print(f"❌ [SYSTEM] 에이전트 구동 실패: {e}")

async def main():
    print(f"🚀 Aegis-Chaos ({settings.ENVIRONMENT.upper()}) 단일 컨테이너 모드 구동 🚀")
    
    # 1. FastAPI 및 웹소켓 서버 설정 (React 정적 파일 서빙 포함)
    config = uvicorn.Config(
        app=app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        loop="asyncio"
    )
    server = uvicorn.Server(config)
    
    # 2. Uvicorn 웹 서버와 AI 에이전트 통신망을 비동기로 동시 가동
    # 이를 통해 AWS Fargate 단일 Task 안에서 Scale-to-Zero 비용 최적화가 가능합니다.
    await asyncio.gather(
        server.serve(),
        start_background_agents()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[SYSTEM] 시스템이 안전하게 종료되었습니다.")
