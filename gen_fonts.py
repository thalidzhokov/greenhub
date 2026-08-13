# pyright: basic
"""Одноразовый генератор: OTF (FontStruct) -> файлы глифов в формате glyphs.

Для каждого символа A-Z a-z 0-9 сэмплирует центры клеток пиксельной сетки
по контурам глифа (nonzero winding). Шрифты выше 7 клеток пропускаются.
"""

import math
import sys
from pathlib import Path

from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTFont

ROWS = 7
CHARS = [chr(c) for c in [*range(65, 91), *range(97, 123), *range(48, 58)]]

FONT_FILES = {
    # id -> (otf, отображаемое имя)
    "astronomas-mono": ("astronomas-mono.otf", "Astronomas Mono"),
    "5x7-mono": ("5x7mono.otf", "5x7 mono"),
    "5x7-pixel-slanted": ("5x7-pixel-slanted-v3.otf", "5x7 Pixel Slanted V3"),
    "5x7-dotmatrix": ("5x7-fixed-dotmatrix-iso8859-1.otf", "5x7 fixed dotmatrix ISO8859-1"),
    "tom-thumb": ("tom-thumb.otf", "Tom Thumb"),
    "hd44780": ("hd44780-5x8.otf", "hd44780 5x8"),
}

# у slanted верхние 3 строки сдвинуты на клетку вправо - выпрямляем
UNSLANT = {"5x7-pixel-slanted"}


def unslant(matrix: list[str]) -> list[str]:
    for r in range(3):
        matrix[r] = matrix[r][1:] + "."
    while all(row[-1] == "." for row in matrix) and len(matrix[0]) > 1:
        matrix = [row[:-1] for row in matrix]
    return matrix


class PolyPen(BasePen):
    """Собирает контуры глифа, кривые аппроксимирует ломаной.

    anchors — только опорные точки (без сэмплов кривых), по ним ищем шаг сетки.
    """

    def __init__(self, glyph_set):
        super().__init__(glyph_set)
        self.contours: list[list[tuple[float, float]]] = []
        self.anchors: list[tuple[float, float]] = []

    def _moveTo(self, pt):
        self.contours.append([pt])
        self.anchors.append(pt)

    def _lineTo(self, pt):
        self.contours[-1].append(pt)
        self.anchors.append(pt)

    def _curveToOne(self, pt1, pt2, pt3):
        p0 = self.contours[-1][-1]
        for i in range(1, 17):
            t = i / 16
            u = 1 - t
            x = u**3 * p0[0] + 3 * u**2 * t * pt1[0] + 3 * u * t**2 * pt2[0] + t**3 * pt3[0]
            y = u**3 * p0[1] + 3 * u**2 * t * pt1[1] + 3 * u * t**2 * pt2[1] + t**3 * pt3[1]
            self.contours[-1].append((x, y))
        self.anchors.append(pt3)

    def _closePath(self):
        pass


def grid_step(values: list[float]) -> float:
    """Шаг сетки: минимальная положительная разница соседних уникальных значений."""
    unique = sorted(set(round(v, 1) for v in values))
    diffs = [b - a for a, b in zip(unique, unique[1:]) if b - a > 0.5]
    step = min(diffs)
    # значения должны сидеть на сетке с этим шагом (допуск 5%)
    for d in diffs:
        ratio = d / step
        if abs(ratio - round(ratio)) > 0.05:
            raise ValueError(f"шаг {step} не делит разницу {d}")
    return step


def filled(px: float, py: float, contours) -> bool:
    """Точка внутри контуров (nonzero winding, луч вправо)."""
    w = 0
    for pts in contours:
        for i in range(len(pts)):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % len(pts)]
            if (y1 <= py < y2) or (y2 <= py < y1):
                xi = x1 + (py - y1) / (y2 - y1) * (x2 - x1)
                if xi > px:
                    w += 1 if y2 > y1 else -1
    return w != 0


def contour_center(pts: list[tuple[float, float]]) -> tuple[float, float]:
    return sum(x for x, _ in pts) / len(pts), sum(y for _, y in pts) / len(pts)


def dot_glyph(pts, brick: float, cy_max: float, pad_top: int) -> list[str]:
    """Матрица одного глифа по центрам его контуров-точек."""
    cx_min = min(cx for cx, _ in pts)
    cells = {
        (round((cy_max - cy) / brick) + pad_top, round((cx - cx_min) / brick))
        for cx, cy in pts
    }
    width = max(c for _, c in cells) + 1
    return [
        "".join("#" if (r, c) in cells else "." for c in range(width))
        for r in range(ROWS)
    ]


def build_from_dots(outlines: dict[str, list]) -> tuple[dict[str, list[str]], int] | None:
    """Для шрифтов из отдельных точек: клетка = центр контура-точки."""
    centers = {
        ch: [contour_center(pts) for pts in contours]
        for ch, contours in outlines.items()
    }
    all_cy = [cy for pts in centers.values() for _, cy in pts]
    brick = grid_step(all_cy)
    cy_max = max(all_cy)
    rows = round((cy_max - min(all_cy)) / brick) + 1
    print(f"  точки: кирпич={brick}, строк={rows}")
    if rows > ROWS:
        return None

    pad_top = (ROWS - rows + 1) // 2
    glyphs = {ch: dot_glyph(pts, brick, cy_max, pad_top) for ch, pts in centers.items()}
    return glyphs, rows


def collect_outlines(otf_path: Path) -> tuple[dict[str, list], list[float]] | None:
    """Контуры всех символов и y опорных точек; None, если символ отсутствует или пуст."""
    font = TTFont(otf_path)
    cmap = font.getBestCmap() or {}
    glyph_set = font.getGlyphSet()

    outlines: dict[str, list] = {}
    anchor_ys: list[float] = []
    for ch in CHARS:
        if ord(ch) not in cmap:
            print(f"  нет символа {ch!r}")
            return None
        pen = PolyPen(glyph_set)
        glyph_set[cmap[ord(ch)]].draw(pen)
        contours = [c for c in pen.contours if len(c) >= 3]
        if not contours:
            print(f"  пустой глиф {ch!r}")
            return None
        outlines[ch] = contours
        anchor_ys += [y for _, y in pen.anchors]
    return outlines, anchor_ys


def rasterize_glyph(
    contours, brick: float, ymax: float, rows: int, pad_top: int
) -> list[str]:
    """Матрица одного глифа: сэмплирует центры клеток сетки по контурам."""
    xs = [x for pts in contours for x, _ in pts]
    # допуск на накопленную ошибку округления координат (шаг может быть дробным)
    c0 = math.floor(min(xs) / brick + 0.05)
    c1 = math.ceil(max(xs) / brick - 0.05)
    width = c1 - c0
    matrix = []
    for r in range(ROWS):
        fr = r - pad_top
        if not 0 <= fr < rows:
            matrix.append("." * width)
            continue
        py = ymax - (fr + 0.5) * brick
        row = "".join(
            "#" if filled((c0 + c + 0.5) * brick, py, contours) else "."
            for c in range(width)
        )
        matrix.append(row)
    return matrix


def build_font(otf_path: Path) -> tuple[dict[str, list[str]], int] | None:
    collected = collect_outlines(otf_path)
    if collected is None:
        return None
    outlines, anchor_ys = collected

    try:
        brick = grid_step(anchor_ys)
    except ValueError:
        return build_from_dots(outlines)
    ymin, ymax = min(anchor_ys), max(anchor_ys)
    rows = round((ymax - ymin) / brick)
    caps_y = [y for ch in "AEM0" for pts in outlines[ch] for _, y in pts]
    caps_rows = round((max(caps_y) - min(caps_y)) / brick)
    print(f"  кирпич={brick}, строк всего={rows} (заглавные={caps_rows}), y={ymin}..{ymax}")
    if rows > ROWS:
        return None

    pad_top = (ROWS - rows + 1) // 2
    glyphs = {
        ch: rasterize_glyph(contours, brick, ymax, rows, pad_top)
        for ch, contours in outlines.items()
    }
    return glyphs, rows


def write_font(path: Path, name: str, glyphs: dict[str, list[str]]) -> None:
    blocks = ["ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz", "0123456789"]
    out = [f"name: {name}", ""]
    for block in blocks:
        out.append(" ".join(block))
        for r in range(ROWS):
            out.append(" ".join(glyphs[ch][r] for ch in block))
        out.append("")
    path.write_text("\n".join(out), encoding="utf-8", newline="\n")


def main() -> None:
    src = Path(sys.argv[1])
    dest = Path(sys.argv[2])
    dest.mkdir(exist_ok=True)
    for font_id, (otf, name) in FONT_FILES.items():
        print(f"{name} ({otf}):")
        result = build_font(src / otf)
        if result is None:
            print("  ИСКЛЮЧЁН")
            continue
        glyphs, _ = result
        if font_id in UNSLANT:
            glyphs = {ch: unslant(matrix) for ch, matrix in glyphs.items()}
        write_font(dest / f"{font_id}.txt", name, glyphs)
        widths = {len(m[0]) for m in glyphs.values()}
        print(f"  OK -> {font_id}.txt (ширины: {sorted(widths)})")


if __name__ == "__main__":
    main()
