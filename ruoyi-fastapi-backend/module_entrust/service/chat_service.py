"""
委外加工 -- 聊天 Service
"""
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from module_entrust.entity.do.entrust_do import (
    EntrustChatMessage, EntrustChatSession, EntrustSupplier,
)
from module_entrust.entity.vo.entrust_vo import ChatMessageVO, ChatSessionVO
from module_admin.entity.do.user_do import SysUser


class ChatService:

    @staticmethod
    async def resolve_session_participants(
        db: AsyncSession, session_id: int, sender_user_id: int,
    ) -> tuple[str | None, int | None]:
        """
        Determine sender identity based on session ownership.
        Uses session.our_user_id and session.supplier_user_id directly (no join).
        Returns (sender_type, receiver_user_id), or (None, None) if unauthorized.
        """
        stmt = select(EntrustChatSession).where(EntrustChatSession.id == session_id)
        session = (await db.execute(stmt)).scalar_one_or_none()
        if not session:
            return None, None

        if session.our_user_id == sender_user_id:
            return 'our', session.supplier_user_id

        if session.supplier_user_id == sender_user_id:
            return 'supplier', session.our_user_id

        return None, None

    @staticmethod
    async def get_or_create_session(
        db: AsyncSession,
        our_user_id: int,
        supplier_id: int,
        project_id: int | None = None,
        request_id: int | None = None,
    ) -> int | None:
        """Get or create session, handle concurrent duplicate inserts."""
        stmt = select(EntrustChatSession).where(
            EntrustChatSession.our_user_id == our_user_id,
            EntrustChatSession.supplier_id == supplier_id,
        )
        session = (await db.execute(stmt)).scalar_one_or_none()
        if session:
            # Unhide for our side when navigating from supplier list
            if session.our_hidden:
                session.our_hidden = False
            return session.id

        # Look up supplier_user_id
        sup_stmt = select(EntrustSupplier.user_id).where(EntrustSupplier.id == supplier_id)
        supplier_user_id = (await db.execute(sup_stmt)).scalar_one_or_none()

        new_session = EntrustChatSession(
            our_user_id=our_user_id,
            supplier_id=supplier_id,
            supplier_user_id=supplier_user_id,
            project_id=project_id,
            request_id=request_id,
            status='inquiring',
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        db.add(new_session)
        try:
            await db.flush()
        except IntegrityError:
            # Concurrent scenario: another request already created the same session
            await db.rollback()
            session = (await db.execute(stmt)).scalar_one_or_none()
            return session.id if session else None

        return new_session.id

    @staticmethod
    async def send_message(
        db: AsyncSession,
        sender_type: str,
        sender_id: int,
        session_id: int,
        content: str,
        message_type: str = 'text',
        extra_data: dict | None = None,
    ) -> ChatMessageVO:
        """Send message and return ChatMessageVO."""
        now = datetime.now()
        msg = EntrustChatMessage(
            session_id=session_id,
            sender_type=sender_type,
            sender_id=sender_id,
            content=content,
            message_type=message_type,
            extra_data=extra_data,
            created_at=now,
        )
        db.add(msg)

        # Update session (including updated_at)
        session_stmt = select(EntrustChatSession).where(EntrustChatSession.id == session_id)
        session_obj = (await db.execute(session_stmt)).scalar_one_or_none()
        if session_obj:
            session_obj.last_message = content[:200]
            session_obj.last_message_type = message_type
            session_obj.last_message_at = now
            session_obj.updated_at = now

            # Auto-fill supplier_user_id if missing (session created before supplier was linked)
            if not session_obj.supplier_user_id:
                sup_stmt = select(EntrustSupplier.user_id).where(EntrustSupplier.id == session_obj.supplier_id)
                uid = (await db.execute(sup_stmt)).scalar_one_or_none()
                if uid:
                    session_obj.supplier_user_id = uid

            # Unhide for receiver when a new message arrives
            if sender_type == 'our':
                session_obj.supplier_hidden = False
                session_obj.supplier_unread = (session_obj.supplier_unread or 0) + 1
            else:
                session_obj.our_hidden = False
                session_obj.our_unread = (session_obj.our_unread or 0) + 1

            # Quotation card: inquiring -> quoted (lenient, allow multiple quotes)
            if message_type == 'quotation' and session_obj.status == 'inquiring':
                session_obj.status = 'quoted'

        await db.flush()

        # Get sender name
        sender_name = await ChatService._get_sender_name(db, sender_type, sender_id)

        return ChatMessageVO(
            id=msg.id,
            session_id=session_id,
            sender_type=sender_type,
            sender_name=sender_name,
            content=content,
            message_type=message_type,
            extra_data=extra_data,
            created_at=now,
        )

    @staticmethod
    async def get_sessions(db: AsyncSession, user_id: int, roles: list[str]) -> list[ChatSessionVO]:
        """Get session list, filter hidden, sort pinned first."""
        is_processor = 'processor' in roles

        if is_processor:
            stmt = (
                select(EntrustChatSession)
                .where(
                    EntrustChatSession.supplier_user_id == user_id,
                    EntrustChatSession.supplier_hidden == False,
                )
                .order_by(
                    EntrustChatSession.is_pinned.desc(),
                    EntrustChatSession.pinned_at.desc().nulls_last(),
                    EntrustChatSession.last_message_at.desc().nulls_last(),
                )
            )
        else:
            stmt = (
                select(EntrustChatSession)
                .where(
                    EntrustChatSession.our_user_id == user_id,
                    EntrustChatSession.our_hidden == False,
                )
                .order_by(
                    EntrustChatSession.is_pinned.desc(),
                    EntrustChatSession.pinned_at.desc().nulls_last(),
                    EntrustChatSession.last_message_at.desc().nulls_last(),
                )
            )

        sessions = (await db.execute(stmt)).scalars().all()
        result = []
        for s in sessions:
            our_user_name = await ChatService._get_sender_name(db, 'our', s.our_user_id)
            supplier_name_stmt = select(EntrustSupplier.name).where(EntrustSupplier.id == s.supplier_id)
            supplier_name = (await db.execute(supplier_name_stmt)).scalar_one_or_none() or ''

            result.append(ChatSessionVO(
                id=s.id,
                our_user_id=s.our_user_id,
                our_user_name=our_user_name,
                supplier_id=s.supplier_id,
                supplier_user_id=s.supplier_user_id,
                supplier_name=supplier_name,
                project_id=s.project_id,
                request_id=s.request_id,
                status=s.status,
                last_message=s.last_message,
                last_message_type=s.last_message_type,
                last_message_at=s.last_message_at,
                is_pinned=s.is_pinned,
                unread=s.supplier_unread if is_processor else s.our_unread,
                created_at=s.created_at,
            ))
        return result

    @staticmethod
    async def get_messages(
        db: AsyncSession,
        session_id: int,
        limit: int = 50,
        before_id: int | None = None,
        after_id: int | None = None,
    ) -> list[ChatMessageVO]:
        """
        Get messages:
        - after_id (incremental pull / reconnect): ASC order, return earliest limit messages after after_id
        - before_id (load history): DESC order, return latest limit messages before before_id
        - No params: DESC order, return latest limit messages
        """
        if after_id:
            # Incremental pull: from after_id onwards, ascending
            stmt = (
                select(EntrustChatMessage)
                .where(
                    EntrustChatMessage.session_id == session_id,
                    EntrustChatMessage.id > after_id,
                )
                .order_by(EntrustChatMessage.id.asc())
                .limit(limit)
            )
            msgs = (await db.execute(stmt)).scalars().all()
            # Already in ascending order, return directly
        else:
            # History / initial load: descending, then reverse
            stmt = (
                select(EntrustChatMessage)
                .where(EntrustChatMessage.session_id == session_id)
                .order_by(EntrustChatMessage.id.desc())
                .limit(limit)
            )
            if before_id:
                stmt = stmt.where(EntrustChatMessage.id < before_id)
            msgs = (await db.execute(stmt)).scalars().all()
            msgs = list(reversed(msgs))

        result = []
        for m in msgs:
            sender_name = await ChatService._get_sender_name(db, m.sender_type, m.sender_id)
            result.append(ChatMessageVO(
                id=m.id,
                session_id=m.session_id,
                sender_type=m.sender_type,
                sender_name=sender_name,
                content=m.content,
                message_type=m.message_type,
                extra_data=m.extra_data,
                created_at=m.created_at,
            ))
        return result

    @staticmethod
    async def hide_session(db: AsyncSession, session_id: int, user_id: int, is_processor: bool) -> bool:
        """Hide (soft-delete) a session for the current user."""
        stmt = select(EntrustChatSession).where(EntrustChatSession.id == session_id)
        session = (await db.execute(stmt)).scalar_one_or_none()
        if not session:
            return False
        # Verify ownership
        if is_processor:
            if session.supplier_user_id != user_id:
                return False
            session.supplier_hidden = True
        else:
            if session.our_user_id != user_id:
                return False
            session.our_hidden = True
        await db.flush()
        return True

    @staticmethod
    async def clear_messages(db: AsyncSession, session_id: int) -> int:
        """Delete all messages in a session. Returns count of deleted messages."""
        stmt = delete(EntrustChatMessage).where(EntrustChatMessage.session_id == session_id)
        result = await db.execute(stmt)
        # Reset session last_message
        session_stmt = select(EntrustChatSession).where(EntrustChatSession.id == session_id)
        session_obj = (await db.execute(session_stmt)).scalar_one_or_none()
        if session_obj:
            session_obj.last_message = None
            session_obj.last_message_type = None
            # Keep last_message_at so session stays in place in the list
        await db.flush()
        return result.rowcount

    @staticmethod
    async def toggle_pin(db: AsyncSession, session_id: int) -> bool | None:
        """Toggle pin status. Returns new is_pinned value, or None if session not found."""
        stmt = select(EntrustChatSession).where(EntrustChatSession.id == session_id)
        session = (await db.execute(stmt)).scalar_one_or_none()
        if not session:
            return None
        session.is_pinned = not session.is_pinned
        session.pinned_at = datetime.now() if session.is_pinned else None
        await db.flush()
        return session.is_pinned

    @staticmethod
    async def mark_read(db: AsyncSession, session_id: int, user_id: int, is_processor: bool) -> bool:
        """Clear unread count for the current user when opening a session."""
        stmt = select(EntrustChatSession).where(EntrustChatSession.id == session_id)
        session = (await db.execute(stmt)).scalar_one_or_none()
        if not session:
            return False
        if is_processor:
            if session.supplier_user_id != user_id:
                return False
            session.supplier_unread = 0
        else:
            if session.our_user_id != user_id:
                return False
            session.our_unread = 0
        await db.flush()
        return True

    @staticmethod
    async def _get_sender_name(db: AsyncSession, sender_type: str, sender_id: int) -> str:
        """Get sender display name."""
        if sender_type == 'our':
            stmt = select(SysUser.nick_name).where(SysUser.user_id == sender_id)
            name = (await db.execute(stmt)).scalar_one_or_none()
            return name or ''
        else:
            stmt = select(EntrustSupplier.name).where(EntrustSupplier.user_id == sender_id)
            name = (await db.execute(stmt)).scalar_one_or_none()
            return name or ''
