#!/usr/bin/env python3
"""
backPusher for remnawave
by @error_kill

Использование:
  python3 bypass.py
  python3 bypass.py --undo
  python3 bypass.py --status
"""

import subprocess
import sys
import os
import re
import argparse


def run(cmd, check=True):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        return None
    return result.stdout.strip()


def find_backend_container():
    print("🔍 Ищем контейнер Remnawave backend...")
    output = run("docker ps --format '{{.Names}} {{.Image}}'")
    if not output:
        print("❌ Docker не запущен или нет контейнеров")
        return None

    for line in output.split("\n"):
        if "remnawave/backend" in line:
            container = line.split()[0]
            print(f"  ✅ Найден: {container}")
            return container

    print("❌ Контейнер remnawave/backend не найден")
    return None


def find_auth_service(container):
    print("🔍 Ищем auth.service.js...")

    paths = [
        "/opt/app/dist/src/modules/auth/auth.service.js",
        "/app/dist/src/modules/auth/auth.service.js",
        "/app/src/modules/auth/auth.service.js",
    ]

    for path in paths:
        result = run(f"docker exec {container} test -f {path} && echo 'found'", check=False)
        if result == "found":
            print(f"  ✅ Найден: {path}")
            return path

    print("  ⏳ Ищем через find...")
    output = run(f"docker exec {container} find / -name 'auth.service.js' -type f 2>/dev/null")
    if output:
        for path in output.split("\n"):
            if path.strip():
                print(f"  ✅ Найден: {path.strip()}")
                return path.strip()

    print("❌ auth.service.js не найден")
    return None


def get_file_content(container, path):
    return run(f"docker exec {container} cat {path}", check=False)


def set_file_content(container, path, content):
    tmp_file = "/tmp/auth.service.js.temp"
    with open(tmp_file, "w") as f:
        f.write(content)
    run(f"docker cp {tmp_file} {container}:{path}")
    os.remove(tmp_file)


def check_status(container, path):
    content = get_file_content(container, path)
    if not content:
        return None

    if "const isPasswordValid = true; // BYPASS" in content:
        return "patched"
    elif "verifyPassword" in content:
        return "original"
    return "unknown"


def apply_bypass(container, path):
    """Отключает проверку пароля."""
    print("🔧 Отключаем проверку пароля...")

    content = get_file_content(container, path)
    if not content:
        print("❌ Не удалось прочитать файл")
        return False

    new_content = re.sub(
        r'const isPasswordValid = await this\.verifyPassword\([^)]+\);',
        'const isPasswordValid = true; // BYPASS',
        content
    )

    if new_content == content:
        print("❌ Не удалось найти строку для замены")
        return False

    set_file_content(container, path, new_content)
    print("  ✅ Проверка пароля отключена")
    return True


def undo_bypass(container, path):
    print("🔧 Включаем проверку пароля...")

    content = get_file_content(container, path)
    if not content:
        print("❌ Не удалось прочитать файл")
        return False

    new_content = content.replace(
        "const isPasswordValid = true; // BYPASS",
        "const isPasswordValid = await this.verifyPassword(password, admin.response.passwordHash);"
    )

    if new_content == content:
        print("❌ Патч не найден (возможно, уже откатан)")
        return False

    set_file_content(container, path, new_content)
    print("  ✅ Проверка пароля включена")
    return True


def restart_container(container):
    """Перезапускает контейнер."""
    print(f"🔄 Перезапускаем {container}...")
    run(f"docker restart {container}")
    print("  ✅ Перезапущен")


def main():
    parser = argparse.ArgumentParser(
        description="Remnawave Bypass Universal",
        epilog="""
Примеры:
  python3 bypass.py              # Отключить проверку пароля
  python3 bypass.py --undo       # Включить проверку пароля
  python3 bypass.py --status     # Проверить статус
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--undo", action="store_true", help="Включить проверку пароля")
    parser.add_argument("--status", action="store_true", help="Проверить статус")

    args = parser.parse_args()

    print("=" * 60)
    print("  Remnawave Bypass Universal")
    print("=" * 60)
    print()

    container = find_backend_container()
    if not container:
        sys.exit(1)

    path = find_auth_service(container)
    if not path:
        sys.exit(1)

    print()

    if args.status:
        print("🔍 РЕЖИМ: ПРОВЕРКА СТАТУСА")
        print("-" * 60)
        print()

        status = check_status(container, path)

        if status == "patched":
            print("  ⚠️  Патч ПРИМЕНЁН (проверка пароля отключена)")
            print()
            print("💡 Для отката: python3 bypass.py --undo")
        elif status == "original":
            print("  ✅ Патч НЕ применён (проверка пароля включена)")
            print()
            print("💡 Для применения: python3 bypass.py")
        else:
            print("  ❌ Не удалось определить статус")
        return

    if args.undo:
        print("🔄 РЕЖИМ: ОТКАТ")
        print("-" * 60)
        print()

        if undo_bypass(container, path):
            print()
            restart_container(container)
            print()
            print("=" * 60)
            print("  ✅ ОТКАТ ЗАВЕРШЁН!")
            print("=" * 60)
            print()
            print("📋 Проверка пароля включена")
            print(" Используйте оригинальный пароль для входа")
        else:
            sys.exit(1)
        return

    print(" РЕЖИМ: ПРИМЕНЕНИЕ ПАТЧА")
    print("-" * 60)
    print()

    status = check_status(container, path)
    if status == "patched":
        print("⚠️  Патч уже применён!")
        print("💡 Для отката: python3 bypass.py --undo")
        return

    if apply_bypass(container, path):
        print()
        restart_container(container)
        print()
        print("=" * 60)
        print("  ✅ ПАТЧ ПРИМЕНЁН!")
        print("=" * 60)
        print()
        print("📋 Проверка пароля отключена")
        print("📋 Войдите с ЛЮБЫМ паролем")
        print()
        print("💡 Для отката: python3 bypass.py --undo")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
