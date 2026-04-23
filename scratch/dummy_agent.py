import asyncio
import sys
import os

# 프로젝트 루트 경로를 sys.path에 추가하여 모듈 임포트 가능하게 설정
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from infrastructure.redis_client import redis_client

async def main():
    print("🤖 [Dummy Agent] 백그라운드 에이전트 구동 완료.")
    print("채팅 대시보드에서 메시지를 입력해보세요 (Listening to 'agent.inbound'...)")
    
    async def on_message(data):
        print(f"📥 [수신] 프론트엔드로부터 받은 메시지: {data}")
        user_text = data.get("text", "")
        
        # 가상의 에이전트 응답 생성 및 발행
        response = {
            "sender": "analyst-agent",
            "text": f"분석 에이전트입니다. 전달해주신 '{user_text}' 명령을 분석 중입니다..."
        }
        print(f"📤 [발신] 프론트엔드로 응답 전송 중...")
        await redis_client.publish("agent.outbound", response)
        
    # React -> FastAPI -> Redis 로 들어오는 메시지 구독
    task = await redis_client.subscribe("agent.inbound", on_message)
    
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n종료합니다...")
    finally:
        task.cancel()

if __name__ == "__main__":
    asyncio.run(main())
