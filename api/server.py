from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from core.config import settings
from infrastructure.redis_client import redis_client

app = FastAPI(title="Aegis-Chaos Dashboard API")

# 로컬 개발 시 React(Vite)와 API 간의 포트 충돌 방지(CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/status")
async def get_status():
    return {
        "status": "ok",
        "environment": settings.ENVIRONMENT,
        "clusters": {name: cfg.name for name, cfg in settings.CLUSTERS.items()}
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_json({
        "sender": "system", 
        "text": f"[SYSTEM] Aegis-Chaos ({settings.ENVIRONMENT}) 에이전트 허브에 연결되었습니다.\n현재 활성 클러스터: {', '.join([cfg.name for cfg in settings.CLUSTERS.values()])}"
    })
    
    # Redis에서 에이전트의 응답을 수신하는 콜백 함수
    async def on_agent_message(data: dict):
        try:
            await websocket.send_json(data)
        except Exception as e:
            print(f"[WebSocket] Error sending to client: {e}")

    # 'agent.outbound' 채널을 구독하여 웹소켓 클라이언트에게 브로드캐스트
    redis_task = await redis_client.subscribe("agent.outbound", on_agent_message)
    
    try:
        while True:
            # 브라우저에서 입력받은 명령어 수신 (JSON 형태 예상: {"cluster_id": "vpc1", "text": "..."})
            raw_text = await websocket.receive_text()
            
            try:
                import json
                data = json.loads(raw_text)
                cluster_id = data.get("cluster_id", "vpc1")
                text = data.get("text", "")
            except Exception:
                # 하위 호환성 (단순 텍스트)
                cluster_id = "vpc1"
                text = raw_text
                
            # 사용자 메시지 에코 (채팅창 UI용)
            await websocket.send_json({"sender": "user", "text": text, "cluster_id": cluster_id})
            
            # 수신한 명령어를 Redis 'agent.inbound' 채널로 발행하여 백그라운드 에이전트가 처리하게 함
            payload = {"sender": "user", "text": text, "cluster_id": cluster_id}
            await redis_client.publish("agent.inbound", payload)
            
    except WebSocketDisconnect:
        print("[SYSTEM] Client disconnected.")
    except Exception as e:
        print(f"[WebSocket] Error: {e}")
    finally:
        redis_task.cancel() # 클라이언트 종료 시 Redis 구독 해제

# 단일 컨테이너(Fargate) 배포를 위해 빌드된 React 정적 파일 서빙
import os
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(frontend_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dir, "assets")), name="assets")
    
    @app.get("/{full_path:path}")
    async def serve_react(full_path: str):
        index_file = os.path.join(frontend_dir, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        return {"error": "Frontend build not found."}
