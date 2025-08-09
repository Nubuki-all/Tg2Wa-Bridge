from sqlalchemy import Index, Integer, LargeBinary, String, and_, or_, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from bridge_bot.config import bot


class Base(DeclarativeBase):
    pass


class Message(Base):
    __tablename__ = "Bridged_Message"
    __table_args__ = (
        Index("tg_idx_id", "tg_id", "chat_id"),
        Index("wa_idx_id", "wa_id", "chat_id"),
    )
    _id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(Integer)
    tg_id: Mapped[int] = mapped_column(Integer)
    wa_id: Mapped[str] = mapped_column(String(30))
    raw: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    raw_user: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    timestamp: Mapped[int] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return (
            f"Message(_id={self._id!r}, "
            f"chat_id={self.chat_id!r}, "
            f"tg_id={self.tg_id!r}, "
            f"wa_id={self.wa_id!r}, "
            # f"raw={self.raw!r}, "
        )


class Reaction(Base):
    __tablename__ = "Bridged_Reaction"
    __table_args__ = (
        Index("tgr_idx_id", "tg_id", "chat_id"),
        Index("war_idx_id", "wa_id", "chat_id"),
    )
    _id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(Integer)
    tg_id: Mapped[int] = mapped_column(Integer)
    wa_id: Mapped[str] = mapped_column(String(30))
    raw: Mapped[bytes] = mapped_column(LargeBinary, nullable=True)
    raw_user: Mapped[bytes] = mapped_column(LargeBinary, nullable=True)
    timestamp: Mapped[int] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return (
            f"Reaction(_id={self._id!r}, "
            f"chat_id={self.chat_id!r}, "
            f"tg_id={self.tg_id!r}, "
            f"wa_id={self.wa_id!r}, "
        )


engines = {}
sessions = {}


async def initialize_session(gc_id):
    if gc_id in sessions:
        return
    engine = create_async_engine(
        f"sqlite+aiosqlite:///chat_dbs/{gc_id}.db",
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        connect_args={"timeout": 10},
    )
    engines[gc_id] = engine
    sessions[gc_id] = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print(f"initialized database: {gc_id}.db")


async def deinitialize_session(gc_id: str) -> None:
    """Clean up and remove session resources for a group chat ID"""
    # Check if session exists
    if gc_id not in sessions or gc_id not in engines:
        return

    # Dispose engine and clean up resources
    engine = engines[gc_id]
    await engine.dispose()

    # Remove references from dictionaries
    del sessions[gc_id]
    del engines[gc_id]

    print(f"Cleaned up resources for database: {gc_id}.db")


async def initialize_all_sessions():
    active_wa_bridges = bot.group_dict.setdefault("active_wa_bridges", [])
    active_wa_subs = bot.group_dict.setdefault("active_wa_subs", [])
    gc_ids = list(set(active_wa_bridges + active_wa_subs))
    for gc_id in gc_ids:
        await initialize_session(gc_id)


async def save_message(
    gc_id, chat_id, jid, msg, tg_id, wa_id, timestamp=None, is_reaction=False
):
    async_session = sessions[gc_id]
    message = Message if not is_reaction else Reaction
    async with async_session() as session:
        msg = message(
            chat_id=chat_id,
            tg_id=tg_id,
            wa_id=wa_id,
            raw=msg.SerializeToString() if msg else None,
            raw_user=(jid or bot.client.me.JID).SerializeToString(),
            timestamp=timestamp,
        )
        async with session.begin():
            session.add(msg)
        await session.commit()


async def get_message(
    gc_id: str,
    chat_id: int,
    tg_id: int = None,
    wa_id: str = None,
    is_reaction: bool = False,
):
    try:
        async_session = sessions[gc_id]
        message = Message if not is_reaction else Reaction
        async with async_session() as session:
            stmt = (
                select(message).where(
                    and_(
                        message.chat_id.in_([chat_id]),
                        message.tg_id.in_([tg_id]),
                    )
                )
                if tg_id
                else select(message).where(
                    and_(
                        message.chat_id.in_([chat_id]),
                        message.wa_id.in_([wa_id]),
                    )
                )
            )
            results = (await session.scalars(stmt)).all()
        return results[0] if results else None
    except Exception as e:
        raise e


async def delete_message(
    gc_id: str,
    chat_id: int,
    tg_id: int | None = None,
    wa_id: str | None = None,
    is_reaction: bool = False,
) -> bool:
    """
    Delete a message using the same parameters as get_message
    Returns True if message was deleted, False if not found
    """
    try:
        # Validate input
        if not tg_id and not wa_id:
            raise ValueError("Either tg_id or wa_id must be provided")

        async_session = sessions[gc_id]
        message = Message if not is_reaction else Reaction
        async with async_session() as session:
            # Build query with same conditions as get_message
            stmt = select(message).where(
                and_(
                    message.chat_id == chat_id,
                    or_(message.tg_id == tg_id, message.wa_id == wa_id),
                )
            )

            result = await session.scalar(stmt)

            if result:
                await session.delete(result)
                await session.commit()
                return True
            return False

    except Exception as e:
        # Handle specific case where session might not exist
        if isinstance(e, KeyError):
            print(f"Session not initialized for gc_id: {gc_id}")
        raise e


async def edit_message(
    gc_id: str,
    chat_id: int,
    update_data: dict,
    tg_id: int | None = None,
    wa_id: str | None = None,
    is_reaction: bool = False,
) -> Message | Reaction | None:
    """
    Edit a message using the same parameters as get_message
    Returns updated message if successful, None if not found
    """
    try:
        # Validate input
        if not tg_id and not wa_id:
            raise ValueError("Either tg_id or wa_id must be provided")

        if not update_data:
            raise ValueError("No update data provided")

        async_session = sessions[gc_id]
        message = Message if not is_reaction else Reaction
        async with async_session() as session:
            # Find message using same logic as get_message
            stmt = (
                select(message)
                .where(
                    and_(
                        message.chat_id == chat_id,
                        or_(
                            message.tg_id == tg_id if tg_id else False,
                            message.wa_id == wa_id if wa_id else False,
                        ),
                    )
                )
                .with_for_update()
            )  # Lock row for update

            message = await session.scalar(stmt)

            if not message:
                return

            # Apply updates
            for key, value in update_data.items():
                if hasattr(message, key):
                    setattr(message, key, value)
                else:
                    raise AttributeError(f"Invalid field: {key}")

            await session.commit()
            return message

    except Exception as e:
        if isinstance(e, KeyError):
            print(f"Session not initialized for gc_id: {gc_id}")
        raise e
