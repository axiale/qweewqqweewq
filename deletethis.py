#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from pathlib import Path

# Список папок, которые нужно игнорировать (можно расширить)
IGNORED_DIRS = {
    '.git', '__pycache__', 'node_modules', '.idea', '.vscode',
    'venv', 'env', '.venv', '.env', 'dist', 'build', '.pytest_cache'
}


def print_tree(directory: Path, prefix: str = '', is_last: bool = True) -> None:
    """
    Рекурсивно выводит структуру директории в виде дерева.

    :param directory: Путь к текущей директории (объект Path)
    :param prefix: Строка-префикс для форматирования отступов
    :param is_last: Флаг, указывающий, является ли текущая директория последней в родительской
    """
    # Выводим название текущей директории
    connector = "└── " if is_last else "├── "
    print(prefix + connector + directory.name)

    # Формируем префикс для дочерних элементов
    new_prefix = prefix + ("    " if is_last else "│   ")

    try:
        # Получаем список всех элементов в директории (файлы и папки)
        items = list(directory.iterdir())
    except PermissionError:
        # Если нет прав на чтение, выводим сообщение и прекращаем обход
        print(new_prefix + "└── [Ошибка доступа]")
        return

    # Разделяем на папки и файлы, папки выводим первыми
    dirs = []
    files = []
    for item in items:
        if item.is_dir():
            if item.name not in IGNORED_DIRS:
                dirs.append(item)
        else:
            files.append(item)

    # Сортируем по имени
    dirs.sort(key=lambda p: p.name)
    files.sort(key=lambda p: p.name)

    # Объединяем: сначала папки, затем файлы
    all_items = dirs + files

    for i, item in enumerate(all_items):
        is_last_item = (i == len(all_items) - 1)

        if item.is_dir():
            # Рекурсивно обрабатываем подпапку
            print_tree(item, new_prefix, is_last_item)
        else:
            # Выводим файл
            file_connector = "└── " if is_last_item else "├── "
            print(new_prefix + file_connector + item.name)


def main() -> None:
    # Определяем корневую директорию
    if len(sys.argv) > 1:
        root_path = Path(sys.argv[1])
    else:
        root_path = Path.cwd()  # Текущая директория по умолчанию

    if not root_path.exists():
        print(f"Ошибка: путь '{root_path}' не существует.")
        sys.exit(1)
    if not root_path.is_dir():
        print(f"Ошибка: '{root_path}' не является директорией.")
        sys.exit(1)

    print(root_path.name)  # Выводим корень
    # Начинаем обход с префикса "" и флагом, что корень - последний (всегда True)
    # Но для корня мы уже вывели имя отдельно, поэтому запускаем обработку его содержимого
    # с пустым префиксом и is_last=True (так как у корня нет "родительского" элемента)
    try:
        items = list(root_path.iterdir())
    except PermissionError:
        print("└── [Ошибка доступа к корневой директории]")
        sys.exit(1)

    # Фильтруем игнорируемые папки на верхнем уровне
    dirs = []
    files = []
    for item in items:
        if item.is_dir():
            if item.name not in IGNORED_DIRS:
                dirs.append(item)
        else:
            files.append(item)

    dirs.sort(key=lambda p: p.name)
    files.sort(key=lambda p: p.name)
    all_items = dirs + files

    for i, item in enumerate(all_items):
        is_last_item = (i == len(all_items) - 1)
        if item.is_dir():
            print_tree(item, "", is_last_item)
        else:
            connector = "└── " if is_last_item else "├── "
            print(connector + item.name)


if __name__ == "__main__":
    main()