"""Routes shared big-game text commands to the active game."""

from games.hide_and_seek import (
    active_hide_games,
    join_hide_game,
    begin_hide_game,
    end_hide_game,
)
from games.penalties import (
    active_penalty_games,
    join_penalty_game,
    begin_penalties,
    continue_penalties,
    end_penalty_game,
)


def get_active_game(chat_id: int) -> str | None:
    if chat_id in active_penalty_games:
        return "penalty"
    if chat_id in active_hide_games:
        return "hide"
    return None


async def join_big_game_router(update, context):
    chat = update.effective_chat
    if not chat:
        return
    game = get_active_game(chat.id)
    if game == "penalty":
        await join_penalty_game(update, context)
    elif game == "hide":
        await join_hide_game(update, context)


async def begin_big_game_router(update, context):
    chat = update.effective_chat
    if not chat:
        return
    game = get_active_game(chat.id)
    if game == "penalty":
        await begin_penalties(update, context)
    elif game == "hide":
        await begin_hide_game(update, context)


async def continue_big_game_router(update, context):
    chat = update.effective_chat
    if not chat:
        return
    if chat.id in active_penalty_games:
        await continue_penalties(update, context)


async def end_big_game_router(update, context):
    chat = update.effective_chat
    if not chat:
        return
    game = get_active_game(chat.id)
    if game == "penalty":
        await end_penalty_game(update, context)
    elif game == "hide":
        await end_hide_game(update, context)
