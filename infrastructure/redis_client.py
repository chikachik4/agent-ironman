import json
import asyncio
from typing import Callable, Any, Coroutine
from redis.asyncio import Redis, ConnectionPool
from core.config import settings

class RedisPubSubClient:
    def __init__(self):
        self.pool = ConnectionPool(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            decode_responses=True
        )
        self.client = Redis(connection_pool=self.pool)
    
    async def publish(self, channel: str, message: dict):
        """
        주어진 채널로 메시지(JSON)를 발행합니다.
        """
        payload = json.dumps(message)
        await self.client.publish(channel, payload)
        
    async def subscribe(self, channel: str, callback: Callable[[dict], Coroutine[Any, Any, None]]):
        """
        주어진 채널을 구독하고, 메시지가 도착하면 비동기 콜백을 실행합니다.
        에이전트가 백그라운드에서 계속 실행될 수 있도록 asyncio Task를 반환합니다.
        """
        pubsub = self.client.pubsub()
        await pubsub.subscribe(channel)
        print(f"[SYSTEM] Subscribed to Redis channel: {channel}")
        
        async def _listen():
            try:
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        data = json.loads(message["data"])
                        await callback(data)
            except asyncio.CancelledError:
                print(f"[SYSTEM] Unsubscribing from channel: {channel}")
            except Exception as e:
                print(f"[ERROR] Redis subscribe error on {channel}: {e}")
            finally:
                await pubsub.unsubscribe(channel)
                await pubsub.close()
                
        return asyncio.create_task(_listen())
        
    async def close(self):
        """
        클라이언트 연결을 우아하게 종료합니다.
        """
        await self.client.aclose()

# Singleton 인스턴스로 사용하여 전체 시스템에서 커넥션 풀 공유
redis_client = RedisPubSubClient()
