"""
委外加工 -- 聊天 Controller (REST + WebSocket)
"""
import time
from typing import Annotated

import jwt
from fastapi import Path, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.router import APIRouterPro
from common.vo import DataResponseModel
from config.database import AsyncSessionLocal
from config.env import JwtConfig
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_entrust.service.chat_service import ChatService
from module_entrust.service.ws_manager import WebSocketManager
from utils.log_util import logger
from utils.response_util import ResponseUtil

chat_controller = APIRouterPro(
    prefix='/entrust/chat',
    order_num=12,
    tags=['委外管理-聊天'],
)

# ---------------------------------------------------------------------------
# Security constants for WebSocket
# ---------------------------------------------------------------------------
ALLOWED_MESSAGE_TYPES = {'text', 'quotation', 'inquiry', 'file'}
ALLOWED_MIME_TYPES = {
    'image/jpeg', 'image/png', 'image/gif', 'image/bmp',
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/zip', 'application/x-rar-compressed',
    'text/plain',
}
MAX_CONTENT_LENGTH = 4000

# Rate limiting: in-memory sliding window
_rate_limit: dict[int, list[float]] = {}  # user_id -> [timestamp, ...]
RATE_LIMIT_WINDOW = 1.0   # 1 second window
RATE_LIMIT_MAX = 3         # max 3 messages per window


def _check_rate_limit(user_id: int) -> bool:
    """Return True if allowed, False if rate limited."""
    now = time.monotonic()
    timestamps = _rate_limit.get(user_id, [])
    timestamps = [t for t in timestamps if now - t < RATE_LIMIT_WINDOW]
    if len(timestamps) >= RATE_LIMIT_MAX:
        _rate_limit[user_id] = timestamps
        return False
    timestamps.append(now)
    _rate_limit[user_id] = timestamps
    return True


def _verify_ws_token(token: str) -> int | None:
    """Verify JWT token for WebSocket connection. Returns user_id or None."""
    if token.startswith('Bearer '):
        token = token[7:]
    try:
        payload = jwt.decode(token, JwtConfig.jwt_secret_key, algorithms=[JwtConfig.jwt_algorithm])
        uid = payload.get('user_id')
        return int(uid) if uid else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

@chat_controller.get(
    '/sessions',
    summary='获取会话列表',
    response_model=DataResponseModel,
    dependencies=[PreAuthDependency()],
)
async def get_sessions(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
):
    sessions = await ChatService.get_sessions(
        query_db, current_user.user.user_id, current_user.roles or []
    )
    return ResponseUtil.success(data=[s.model_dump(by_alias=True) for s in sessions])


@chat_controller.post(
    '/sessions',
    summary='创建/获取会话',
    response_model=DataResponseModel,
    dependencies=[PreAuthDependency()],
)
async def create_session(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    supplier_id: int = Query(..., description='加工方ID'),
):
    session_id = await ChatService.get_or_create_session(query_db, current_user.user.user_id, supplier_id)
    await query_db.commit()
    return ResponseUtil.success(data=session_id)


@chat_controller.get(
    '/messages/{session_id}',
    summary='获取消息列表',
    response_model=DataResponseModel,
    dependencies=[PreAuthDependency()],
)
async def get_messages(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    session_id: int = Path(..., description='会话ID'),
    limit: int = Query(default=50, ge=1, le=200),
    before_id: int = Query(default=None, description='加载此ID之前的消息'),
    after_id: int = Query(default=None, description='加载此ID之后的消息（增量拉取）'),
):
    messages = await ChatService.get_messages(query_db, session_id, limit, before_id, after_id)
    return ResponseUtil.success(data=[m.model_dump(by_alias=True) for m in messages])


@chat_controller.delete(
    '/sessions/{session_id}',
    summary='删除会话（隐藏）',
    response_model=DataResponseModel,
    dependencies=[PreAuthDependency()],
)
async def delete_session(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    session_id: int = Path(..., description='会话ID'),
):
    is_processor = 'processor' in (current_user.roles or [])
    ok = await ChatService.hide_session(query_db, session_id, current_user.user.user_id, is_processor)
    await query_db.commit()
    if not ok:
        return ResponseUtil.failure(msg='会话不存在或无权操作')
    return ResponseUtil.success()


@chat_controller.delete(
    '/messages/{session_id}',
    summary='清空聊天记录',
    response_model=DataResponseModel,
    dependencies=[PreAuthDependency()],
)
async def clear_messages(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    session_id: int = Path(..., description='会话ID'),
):
    count = await ChatService.clear_messages(query_db, session_id)
    await query_db.commit()
    return ResponseUtil.success(data=count)


@chat_controller.put(
    '/sessions/{session_id}/pin',
    summary='置顶/取消置顶',
    response_model=DataResponseModel,
    dependencies=[PreAuthDependency()],
)
async def toggle_pin(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    session_id: int = Path(..., description='会话ID'),
):
    is_pinned = await ChatService.toggle_pin(query_db, session_id)
    await query_db.commit()
    if is_pinned is None:
        return ResponseUtil.failure(msg='会话不存在')
    return ResponseUtil.success(data=is_pinned)


@chat_controller.put(
    '/sessions/{session_id}/read',
    summary='标记会话已读',
    response_model=DataResponseModel,
    dependencies=[PreAuthDependency()],
)
async def mark_read(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    session_id: int = Path(..., description='会话ID'),
):
    is_processor = 'processor' in (current_user.roles or [])
    ok = await ChatService.mark_read(query_db, session_id, current_user.user.user_id, is_processor)
    await query_db.commit()
    if not ok:
        return ResponseUtil.failure(msg='会话不存在或无权操作')
    return ResponseUtil.success()


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@chat_controller.websocket('/ws')
async def chat_websocket(websocket: WebSocket, token: str = Query(...)):
    # 1. Auth
    user_id = _verify_ws_token(token)
    if not user_id:
        await websocket.close(code=4001)
        return

    # 2. Connect
    await WebSocketManager.connect(user_id, websocket)
    try:
        while True:
            try:
                data = await websocket.receive_json()
            except Exception:
                break  # Invalid JSON / oversized payload / connection error

            msg_type = data.get('type')
            if msg_type == 'send_message':
                if not _check_rate_limit(user_id):
                    continue  # Rate limited, silently drop
                await _handle_send_message(user_id, data.get('data', {}))
            elif msg_type == 'ping':
                await WebSocketManager.send_to_user(user_id, {'type': 'pong'})

    except WebSocketDisconnect:
        pass
    finally:
        await WebSocketManager.disconnect(user_id)
        _rate_limit.pop(user_id, None)


async def _handle_send_message(sender_user_id: int, data: dict):
    """Handle an incoming send_message from WebSocket."""
    # 1. Basic validation
    session_id = data.get('session_id')
    content = data.get('content', '')
    if isinstance(content, str):
        content = content.strip()
    message_type = data.get('message_type', 'text')
    extra_data = data.get('extra_data')

    if not session_id or not content:
        return
    if len(content) > MAX_CONTENT_LENGTH:
        return
    if message_type not in ALLOWED_MESSAGE_TYPES:
        return

    # 2. Validate mime_type for file messages
    if message_type == 'file':
        mime = (extra_data or {}).get('mime_type', '')
        if mime not in ALLOWED_MIME_TYPES:
            return

    # 3. Resolve session participants (determine sender identity)
    async with AsyncSessionLocal() as db:
        sender_type, receiver_id = await ChatService.resolve_session_participants(
            db, session_id, sender_user_id
        )
        if not sender_type:
            return  # Unauthorized, silently drop

        # 4. Save to DB
        msg_vo = await ChatService.send_message(
            db, sender_type, sender_user_id, session_id,
            content, message_type, extra_data
        )
        await db.commit()

        msg_data = msg_vo.model_dump(by_alias=True)

    # 5. Push to sender and receiver
    await WebSocketManager.send_to_user(sender_user_id, {
        'type': 'new_message', 'data': msg_data
    })
    if receiver_id and receiver_id != sender_user_id:
        await WebSocketManager.send_to_user(receiver_id, {
            'type': 'new_message', 'data': msg_data
        })
