"""Сниппеты кода для генерируемых коммитов: язык -> (файл, префикс комментария, код).

Код лежит в snippets/example.<ext>, где ext совпадает с расширением целевого файла.
"""

from pathlib import Path

SNIPPETS_DIR = Path(__file__).resolve().parent.parent / "snippets"

# язык -> (имя файла в целевом репо, префикс комментария)
_META: dict[str, tuple[str, str]] = {
    "c": ("main.c", "//"),
    "c++": ("main.cpp", "//"),
    "c#": ("Program.cs", "//"),
    "go": ("main.go", "//"),
    "java": ("Main.java", "//"),
    "javascript": ("index.js", "//"),
    "kotlin": ("Main.kt", "//"),
    "php": ("index.php", "//"),
    "python": ("main.py", "#"),
    "ruby": ("main.rb", "#"),
    "rust": ("main.rs", "//"),
    "scala": ("Main.scala", "//"),
    "swift": ("main.swift", "//"),
    "typescript": ("index.ts", "//"),
}

LANGUAGES: dict[str, tuple[str, str, str]] = {
    lang: (
        filename,
        comment,
        (SNIPPETS_DIR / f"example{Path(filename).suffix}").read_text(encoding="utf-8"),
    )
    for lang, (filename, comment) in _META.items()
}

# Сниппеты дополнены комментариями до одинакового размера, чтобы все языки
# имели равный вес в статистике GitHub. Не даём размерам молча разъехаться.
_sizes = {lang: len(code) for lang, (_, _, code) in LANGUAGES.items()}
if len(set(_sizes.values())) != 1:
    raise ValueError(f"Сниппеты разного размера: {_sizes}")
