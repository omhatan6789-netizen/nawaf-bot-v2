import time
import chess

VALUES = {chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330, chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 0}
DEPTHS = {'سهل': 1, 'متوسط': 2, 'صعب': 3, 'مستحيل': 4}

def score_position(board):
    if board.is_checkmate():
        return -100000 if board.turn else 100000
    if board.is_stalemate() or board.is_insufficient_material() or board.can_claim_draw():
        return 0
    score = 0
    for kind, value in VALUES.items():
        score += len(board.pieces(kind, chess.WHITE)) * value
        score -= len(board.pieces(kind, chess.BLACK)) * value
    for sq in (chess.D4, chess.E4, chess.D5, chess.E5):
        piece = board.piece_at(sq)
        if piece:
            score += 20 if piece.color else -20
    return score

def _search(board, depth, alpha, beta, deadline):
    if depth <= 0 or board.is_game_over(claim_draw=True) or time.monotonic() >= deadline:
        value = score_position(board)
        return value if board.turn == chess.WHITE else -value
    best = -10**9
    moves = list(board.legal_moves)
    moves.sort(key=lambda m: (board.is_capture(m), board.gives_check(m)), reverse=True)
    for move in moves:
        board.push(move)
        value = -_search(board, depth - 1, -beta, -alpha, deadline)
        board.pop()
        best = max(best, value)
        alpha = max(alpha, value)
        if alpha >= beta or time.monotonic() >= deadline:
            break
    return best

def choose_ai_move(fen, difficulty):
    board = chess.Board(fen)
    if board.is_game_over(claim_draw=True):
        return None
    depth = DEPTHS.get(difficulty, 2)
    limit = {'سهل': .12, 'متوسط': .4, 'صعب': 1.0, 'مستحيل': 2.0}.get(difficulty, .4)
    deadline = time.monotonic() + limit
    best_move, best_score = None, -10**9
    moves = list(board.legal_moves)
    moves.sort(key=lambda m: (board.is_capture(m), board.gives_check(m)), reverse=True)
    for move in moves:
        if time.monotonic() >= deadline and best_move is not None:
            break
        board.push(move)
        value = -_search(board, depth - 1, -10**9, 10**9, deadline)
        board.pop()
        if value > best_score:
            best_score, best_move = value, move
    return (best_move or moves[0]).uci()
