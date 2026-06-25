"""
稳定化缓冲区 - 通过多帧投票消除检测抖动
"""

import numpy as np
from collections import deque
from typing import Dict, Tuple
import logging
import os
import time

logger = logging.getLogger(__name__)
MAX_NOISY_MOVE_EXTRA_CHANGES = int(os.getenv("CHRO_MAX_NOISY_MOVE_EXTRA_CHANGES", "2"))


class StableBoardBuffer:
    """
    稳定化棋盘缓冲区
    
    原理:
    - 维护最近N帧的检测结果
    - 对每个位置进行投票
    - 只有超过阈值的棋子才被认定为稳定
    """
    
    def __init__(self, maxlen: int = 5, ratio: float = 0.6):
        """
        初始化缓冲区
        
        Args:
            maxlen: 缓冲队列最大长度
            ratio: 稳定判定比例阈值 (0-1)
        """
        self.buf = deque(maxlen=maxlen)
        self.ratio = ratio
        logger.info(f"稳定化缓冲区初始化: maxlen={maxlen}, ratio={ratio}")
    
    def add(self, state: Dict[Tuple[int, int], str]):
        """
        添加一帧检测结果
        
        Args:
            state: 当前帧的棋盘状态
        """
        self.buf.append(dict(state))
    
    def get_stable(self) -> Dict[Tuple[int, int], str]:
        """
        获取稳定的棋盘状态（通过多帧投票）
        
        Returns:
            稳定的棋盘状态 {(col, row): piece_char}
        """
        if not self.buf:
            return {}
        
        stable = {}
        need = max(1, int(np.ceil(len(self.buf) * self.ratio)))
        
        # 收集所有出现过的棋子位置
        all_positions = set()
        for board in self.buf:
            all_positions.update(board.keys())
        
        # 对每个位置进行投票
        for pos in all_positions:
            # 统计每个棋子字符的出现次数
            piece_votes = {}
            
            for board in self.buf:
                piece = board.get(pos)
                if piece and piece != '.' and piece != 'x':
                    piece_votes[piece] = piece_votes.get(piece, 0) + 1
            
            # 找出得票最多的棋子
            if piece_votes:
                best_piece = max(piece_votes, key=piece_votes.get)
                best_count = piece_votes[best_piece]
                
                # 如果得票数超过阈值，认定为稳定
                if best_count >= need:
                    stable[pos] = best_piece
        
        return stable
    
    def clear(self, log=True):
        """清空缓冲区"""
        self.buf.clear()
        if log:
            logger.info("稳定化缓冲区已清空")


def _between_count(board: Dict[Tuple[int, int], str], from_pos: Tuple[int, int], to_pos: Tuple[int, int]) -> int:
    from_col, from_row = from_pos
    to_col, to_row = to_pos
    count = 0

    if from_col == to_col:
        step = 1 if to_row > from_row else -1
        for row in range(from_row + step, to_row, step):
            if (from_col, row) in board:
                count += 1
    elif from_row == to_row:
        step = 1 if to_col > from_col else -1
        for col in range(from_col + step, to_col, step):
            if (col, from_row) in board:
                count += 1

    return count


def _in_palace(piece: str, pos: Tuple[int, int]) -> bool:
    col, row = pos
    if not 3 <= col <= 5:
        return False
    return 7 <= row <= 9 if piece.isupper() else 0 <= row <= 2


def _is_legal_xiangqi_move(piece: str, from_pos: Tuple[int, int], to_pos: Tuple[int, int], board: Dict[Tuple[int, int], str]) -> bool:
    if not piece or from_pos == to_pos:
        return False

    from_col, from_row = from_pos
    to_col, to_row = to_pos
    dc = to_col - from_col
    dr = to_row - from_row
    abs_dc = abs(dc)
    abs_dr = abs(dr)
    lower = piece.lower()
    is_red = piece.isupper()
    forward = -1 if is_red else 1

    if not (0 <= to_col < 9 and 0 <= to_row < 10):
        return False

    if lower == 'p':
        crossed_river = from_row <= 4 if is_red else from_row >= 5
        return (dc == 0 and dr == forward) or (crossed_river and abs_dc == 1 and dr == 0)

    if lower == 'r':
        return (from_col == to_col or from_row == to_row) and _between_count(board, from_pos, to_pos) == 0

    if lower == 'c':
        if from_col != to_col and from_row != to_row:
            return False
        screen_count = _between_count(board, from_pos, to_pos)
        is_capture = to_pos in board
        return screen_count == (1 if is_capture else 0)

    if lower == 'n':
        if sorted((abs_dc, abs_dr)) != [1, 2]:
            return False
        leg = (from_col + dc // 2, from_row) if abs_dc == 2 else (from_col, from_row + dr // 2)
        return leg not in board

    if lower == 'b':
        if abs_dc != 2 or abs_dr != 2:
            return False
        if is_red and to_row < 5:
            return False
        if not is_red and to_row > 4:
            return False
        eye = (from_col + dc // 2, from_row + dr // 2)
        return eye not in board

    if lower == 'a':
        return abs_dc == 1 and abs_dr == 1 and _in_palace(piece, to_pos)

    if lower == 'k':
        if abs_dc + abs_dr == 1 and _in_palace(piece, to_pos):
            return True
        target = board.get(to_pos)
        return from_col == to_col and target and target.lower() == 'k' and _between_count(board, from_pos, to_pos) == 0

    return False


def _infer_noisy_one_move(prev: Dict[Tuple[int, int], str], curr: Dict[Tuple[int, int], str], removed, added, changed):
    source_candidates = list(dict.fromkeys(removed + changed))
    target_candidates = list(dict.fromkeys(added + changed))
    candidates = []
    total_changes = len(removed) + len(added) + len(changed)

    for from_pos in source_candidates:
        piece = prev.get(from_pos)
        if not piece:
            continue
        for to_pos in target_candidates:
            if from_pos == to_pos or to_pos not in curr:
                continue

            legal = _is_legal_xiangqi_move(piece, from_pos, to_pos, prev)
            if not legal:
                continue

            explained = {from_pos, to_pos}
            noise_count = max(0, total_changes - len(explained))
            dest_piece = curr.get(to_pos)
            same_piece_bonus = 0 if dest_piece == piece else 2
            source_noise_penalty = 2 if from_pos in changed else 0
            distance_penalty = (abs(to_pos[0] - from_pos[0]) + abs(to_pos[1] - from_pos[1])) * 0.1
            score = noise_count * 3 + same_piece_bonus + source_noise_penalty + distance_penalty
            candidates.append((score, from_pos, to_pos, piece, noise_count))

    if not candidates:
        return False, None, None, None

    candidates.sort(key=lambda item: item[0])
    if len(candidates) > 1 and abs(candidates[0][0] - candidates[1][0]) < 0.001:
        return False, None, None, None

    _score, from_pos, to_pos, moved_piece, noise_count = candidates[0]
    if noise_count > MAX_NOISY_MOVE_EXTRA_CHANGES:
        return False, None, None, None

    logical_board = dict(prev)
    logical_board.pop(from_pos, None)
    logical_board[to_pos] = moved_piece

    return True, f"容错识别: {moved_piece} {from_pos}->{to_pos}，忽略噪声点{noise_count}个", (from_pos, to_pos), logical_board


def infer_one_move_from_occupancy(prev: Dict[Tuple[int, int], str], curr: Dict[Tuple[int, int], str]):
    """
    Compare two board states and infer a single move from occupancy changes.

    The moved piece type is intentionally taken from prev[from_pos]. Dynamic
    camera recognition is trusted for "which squares changed", not for the
    piece class after it moved.

    Returns:
        (ok, message, move_points, logical_board)
        move_points is ((from_col, from_row), (to_col, to_row)) when ok.
    """
    prev_positions = set(prev.keys())
    curr_positions = set(curr.keys())

    removed = list(prev_positions - curr_positions)
    added = list(curr_positions - prev_positions)
    changed = [
        pos
        for pos in (prev_positions & curr_positions)
        if prev.get(pos) != curr.get(pos)
    ]

    from_pos = None
    to_pos = None

    if len(removed) == 1 and len(added) == 1 and not changed:
        # Normal move: source becomes empty, target was empty and becomes occupied.
        from_pos = removed[0]
        to_pos = added[0]
    elif len(removed) == 1 and not added and len(changed) == 1:
        # Capture: source becomes empty, occupied target changes visual class/color.
        from_pos = removed[0]
        to_pos = changed[0]
    else:
        ok, message, move_points, logical_board = _infer_noisy_one_move(prev, curr, removed, added, changed)
        if ok:
            return True, message, move_points, logical_board
        change_count = len(removed) + len(added) + len(changed)
        return False, f"变动点数量({change_count})不符", None, None

    moved_piece = prev.get(from_pos)
    if moved_piece is None:
        return False, "起点没有逻辑棋子", None, None

    logical_board = dict(prev)
    logical_board.pop(from_pos, None)
    logical_board[to_pos] = moved_piece

    return True, f"{moved_piece} {from_pos}->{to_pos}", (from_pos, to_pos), logical_board


class DynamicBoardTracker:
    """
    Dynamic board-state tracker for camera streams.

    It follows the same shape as xiangqi_move_with_patch.py:
    - smooth every detection through StableBoardBuffer
    - wait until the same stable state remains unchanged for a short time
    - lock the first stable board as baseline
    - compare later stable states with the baseline to detect one move
    """

    def __init__(self, buffer_window=3, buffer_ratio=0.6, stable_seconds=0.4, min_piece_count=10):
        self.buffer = StableBoardBuffer(maxlen=buffer_window, ratio=buffer_ratio)
        self.stable_seconds = stable_seconds
        self.min_piece_count = min_piece_count
        self.saved_board = None
        self.pending_board = None
        self.pending_since = None

    def reset(self):
        self.buffer.clear()
        self.saved_board = None
        self.pending_board = None
        self.pending_since = None

    def sync_baseline(self, board_state):
        self.saved_board = dict(board_state or {})
        self.buffer.clear(log=False)
        self.pending_board = None
        self.pending_since = None

    def update(self, raw_state):
        self.buffer.add(raw_state or {})
        stable_board = self.buffer.get_stable()
        now = time.monotonic()

        result = {
            'event': 'observing',
            'stable': False,
            'board_state': stable_board,
            'message': '',
            'move': None,
        }

        if len(stable_board) < self.min_piece_count:
            self.pending_board = None
            self.pending_since = None
            result['message'] = f"稳定棋子数量不足: {len(stable_board)}"
            return result

        if self.pending_board != stable_board:
            self.pending_board = dict(stable_board)
            self.pending_since = now
            result['message'] = '等待画面稳定'
            return result

        stable_for = now - (self.pending_since or now)
        result['stable_for'] = stable_for
        if stable_for < self.stable_seconds:
            result['message'] = f"稳定中 {stable_for:.1f}s"
            return result

        result['stable'] = True

        if self.saved_board is None:
            self.saved_board = dict(stable_board)
            result['event'] = 'initial_locked'
            result['message'] = '初始基准已锁定'
            return result

        if set(stable_board.keys()) == set(self.saved_board.keys()):
            result['event'] = 'unchanged'
            result['message'] = '棋盘稳定，未变化'
            result['board_state'] = dict(self.saved_board)
            return result

        ok, message, move_points, logical_board = infer_one_move_from_occupancy(self.saved_board, stable_board)
        result['message'] = message

        if ok:
            self.saved_board = logical_board
            from_pos, to_pos = move_points
            result['event'] = 'move'
            result['board_state'] = dict(self.saved_board)
            result['move'] = {
                'from': {'col': from_pos[0], 'row': from_pos[1]},
                'to': {'col': to_pos[0], 'row': to_pos[1]},
                'code': f"{from_pos[0]}{from_pos[1]}{to_pos[0]}{to_pos[1]}",
                'piece': self.saved_board[to_pos],
            }
        else:
            result['event'] = 'invalid_change'
            result['board_state'] = dict(self.saved_board)

        self.pending_board = None
        self.pending_since = None
        return result
