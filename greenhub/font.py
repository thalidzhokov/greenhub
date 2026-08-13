"""Пиксельные шрифты: парсинг файлов глифов и рендер текста в колонки таймлайна."""

from pathlib import Path

FONTS_DIR = Path(__file__).resolve().parent.parent / "fonts"

ROWS = 7  # дней в неделе, вс-сб
CHAR_GAP = 1  # пустых недель между символами
WORD_GAP = 2  # пустых недель между словами

Glyph = list[str]  # 7 строк из '#' и '.'
Column = list[bool]  # 7 клеток одной недели, вс-сб


def available_fonts() -> dict[str, str]:
    """Шрифты из fonts/: id (имя файла без .txt) -> отображаемое имя."""
    fonts = {}
    for path in sorted(FONTS_DIR.glob("*.txt")):
        first_line = path.read_text(encoding="utf-8").splitlines()[0]
        name = first_line.removeprefix("name:").strip()
        fonts[path.stem] = name or path.stem
    return fonts


def load_font(path: Path) -> dict[str, Glyph]:
    """Разбирает glyphs.txt: строка-заголовок с символами, под ней 7 строк матриц."""
    lines = path.read_text(encoding="utf-8").splitlines()
    font: dict[str, Glyph] = {}
    for i, line in enumerate(lines):
        chars = line.split()
        if not chars or not all(len(c) == 1 and c.isalnum() for c in chars):
            continue
        block = [row.split() for row in lines[i + 1 : i + 1 + ROWS]]
        if len(block) != ROWS or any(
            len(row) != len(chars) or not all(set(cell) <= {"#", "."} for cell in row)
            for row in block
        ):
            continue
        for col, ch in enumerate(chars):
            font[ch] = [row[col] for row in block]
    return font


def _glyph_columns(glyph: Glyph) -> list[Column]:
    return [[row[x] == "#" for row in glyph] for x in range(len(glyph[0]))]


def render_text(text: str, font: dict[str, Glyph]) -> list[Column]:
    """Переводит текст в список колонок-недель."""
    empty: Column = [False] * ROWS
    columns: list[Column] = []
    for word_index, word in enumerate(text.split()):
        if word_index:
            columns += [empty] * WORD_GAP
        for char_index, ch in enumerate(word):
            if ch not in font:
                raise ValueError(
                    f"Символ {ch!r} не поддерживается: только английские буквы и цифры"
                )
            if char_index:
                columns += [empty] * CHAR_GAP
            columns += _glyph_columns(font[ch])
    return columns
