import chess.polyglot
path = "Solista-ENG 2026E-BIN/Solista-ENG 2026E.bin"
board = chess.Board()
with chess.polyglot.open_reader(path) as reader:
    moves = [str(e.move) for e in reader.find_all(board)]
    print(f"Moves found for starting position: {moves}")