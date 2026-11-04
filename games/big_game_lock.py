"""In-memory lock allowing one large game per group."""

active_big_games: dict[int, dict[str, str]] = {}


def get_big_game(chat_id: int):
    return active_big_games.get(int(chat_id))


def lock_big_game(chat_id: int, key: str, name: str) -> bool:
    chat_id = int(chat_id)
    if chat_id in active_big_games:
        return False
    active_big_games[chat_id] = {"key": key, "name": name}
    return True


def unlock_big_game(chat_id: int, key: str | None = None) -> None:
    chat_id = int(chat_id)
    current = active_big_games.get(chat_id)
    if not current or (key is not None and current["key"] != key):
        return
    active_big_games.pop(chat_id, None)
