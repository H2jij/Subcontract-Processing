"""
WebSocket 连接管理器 -- 纯内存实现
- asyncio.Lock 保护并发操作 dict
- send_json 带 timeout 防客户端假死
- 失败自动清理连接
"""
import asyncio

from fastapi import WebSocket

from utils.log_util import logger


class WebSocketManager:
    _connections: dict[int, WebSocket] = {}
    _lock = asyncio.Lock()
    _SEND_TIMEOUT = 10  # seconds

    @classmethod
    async def connect(cls, user_id: int, websocket: WebSocket):
        await websocket.accept()
        async with cls._lock:
            old = cls._connections.get(user_id)
            if old:
                try:
                    await old.close()
                except Exception:
                    pass
            cls._connections[user_id] = websocket

    @classmethod
    async def disconnect(cls, user_id: int):
        async with cls._lock:
            cls._connections.pop(user_id, None)

    @classmethod
    async def send_to_user(cls, user_id: int, message: dict) -> bool:
        """Send message with timeout, auto-cleanup on failure."""
        async with cls._lock:
            ws = cls._connections.get(user_id)
        if not ws:
            return False
        try:
            await asyncio.wait_for(ws.send_json(message), timeout=cls._SEND_TIMEOUT)
            return True
        except Exception:
            logger.warning(f'WebSocket send failed/timeout, cleaning up user {user_id}')
            await cls.disconnect(user_id)
            return False

    @classmethod
    def is_online(cls, user_id: int) -> bool:
        return user_id in cls._connections
