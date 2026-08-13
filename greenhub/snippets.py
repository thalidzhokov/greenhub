"""Сниппеты кода для генерируемых коммитов: язык -> (расширение, маркеры комментария, код).

Код лежит в snippets/example.<ext>.
"""

from pathlib import Path

SNIPPETS_DIR = Path(__file__).resolve().parent.parent / "snippets"

# язык -> (расширение файла, открывающий и закрывающий маркеры комментария);
# закрывающий пуст у языков со строчными комментариями
_META: dict[str, tuple[str, str, str]] = {
    "c": ("c", "//", ""),
    "c++": ("cpp", "//", ""),
    "c#": ("cs", "//", ""),
    "css": ("css", "/*", " */"),
    "go": ("go", "//", ""),
    "html": ("html", "<!--", " -->"),
    "java": ("java", "//", ""),
    "javascript": ("js", "//", ""),
    "kotlin": ("kt", "//", ""),
    "php": ("php", "//", ""),
    "python": ("py", "#", ""),
    "ruby": ("rb", "#", ""),
    "rust": ("rs", "//", ""),
    "scala": ("scala", "//", ""),
    "shell": ("sh", "#", ""),
    "swift": ("swift", "//", ""),
    "typescript": ("ts", "//", ""),
    "yaml": ("yaml", "#", ""),
}

LANGUAGES: dict[str, tuple[str, str, str, str]] = {
    lang: (
        ext,
        opener,
        closer,
        (SNIPPETS_DIR / f"example.{ext}").read_text(encoding="utf-8"),
    )
    for lang, (ext, opener, closer) in _META.items()
}

# Сниппеты дополнены комментариями до одинакового размера, чтобы все языки
# имели равный вес в статистике GitHub. Не даём размерам молча разъехаться.
_sizes = {lang: len(code) for lang, (_, _, _, code) in LANGUAGES.items()}
if len(set(_sizes.values())) != 1:
    raise ValueError(f"Сниппеты разного размера: {_sizes}")
