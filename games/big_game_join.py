"""Routes shared large-game commands; the broken liars-table game is excluded."""

from games.liar import (
    active_liar_games,
    join_liar_game,
    leave_liar_game,
    begin_liar_game,
    end_liar_game,
)
from games.penalties import (
    active_penalty_games,
    join_penalty_game,
    distribute_penalties,
    begin_penalties,
    continue_penalties,
    end_penalty_game,
)
from games.hide_and_seek import (
    active_hide_games,
    join_hide_game,
    begin_hide_game,
    end_hide_game,
)
from games.image_quiz.image_quiz import (
    IMAGE_QUIZZES,
    join_image_quiz,
    leave_image_quiz,
    begin_image_quiz,
    continue_image_quiz,
    end_image_quiz,
)
from games.word_race import (
    RACES,
    join_word_race,
    leave_word_race,
    begin_word_race,
    continue_word_race,
    end_word_race,
    word_race_distribution,
)


def get_active_game(chat_id: int) -> str | None:
    if chat_id in active_liar_games:
        return "liar"
    if chat_id in active_penalty_games:
        return "penalty"
    if chat_id in active_hide_games:
        return "hide"
    if chat_id in IMAGE_QUIZZES:
        return "image_quiz"
    if chat_id in RACES:
        return "word_race"
    return None


async def join_big_game_router(update, context):
    chat = update.effective_chat
    if not chat:
        return
    game = get_active_game(chat.id)
    if game == "liar":
        await join_liar_game(update, context)
    elif game == "penalty":
        await join_penalty_game(update, context)
    elif game == "hide":
        await join_hide_game(update, context)
    elif game == "word_race":
        await join_word_race(update, context)
    elif game == "image_quiz":
        await join_image_quiz(update, context)


async def leave_big_game_router(update, context):
    chat = update.effective_chat
    if not chat:
        return
    if chat.id in active_liar_games:
        await leave_liar_game(update, context)
    elif chat.id in RACES:
        await leave_word_race(update, context)
    elif chat.id in IMAGE_QUIZZES:
        await leave_image_quiz(update, context)


async def begin_big_game_router(update, context):
    chat = update.effective_chat
    if not chat:
        return
    game = get_active_game(chat.id)
    if game == "liar":
        await begin_liar_game(update, context)
    elif game == "penalty":
        await begin_penalties(update, context)
    elif game == "hide":
        await begin_hide_game(update, context)
    elif game == "word_race":
        await begin_word_race(update, context)
    elif game == "image_quiz":
        await begin_image_quiz(update, context)


async def continue_big_game_router(update, context):
    chat = update.effective_chat
    if not chat:
        return
    if chat.id in active_penalty_games:
        await continue_penalties(update, context)
    elif chat.id in RACES:
        await continue_word_race(update, context)
    elif chat.id in IMAGE_QUIZZES:
        await continue_image_quiz(update, context)


async def end_big_game_router(update, context):
    chat = update.effective_chat
    if not chat:
        return
    game = get_active_game(chat.id)
    if game == "liar":
        await end_liar_game(update, context)
    elif game == "penalty":
        await end_penalty_game(update, context)
    elif game == "hide":
        await end_hide_game(update, context)
    elif game == "word_race":
        await end_word_race(update, context)
    elif game == "image_quiz":
        await end_image_quiz(update, context)


async def distribute_big_game_router(update, context):
    chat = update.effective_chat
    if not chat:
        return
    if chat.id in RACES:
        await word_race_distribution(update, context)
    elif chat.id in active_penalty_games:
        await distribute_penalties(update, context)
