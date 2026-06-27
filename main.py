#!/usr/bin/env python3
"""
backPusher for remnawave
by @error_kill
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


def get_db_credentials(backend_container, silent=False):
    if not silent:
        print("🔍 Получаем данные для подключения к БД...")
    
    env_output = run(f"docker inspect {backend_container} --format '{{{{range .Config.Env}}}}{{{{println .}}}}{{{{end}}}}'")
    if not env_output:
        if not silent:
            print("  ❌ Не удалось получить переменные окружения")
        return None
    
    db_url = None
    for line in env_output.split("\n"):
        if line.startswith("DATABASE_URL="):
            db_url = line.split("=", 1)[1]
            break
            
    if not db_url:
        if not silent:
            print("  ❌ DATABASE_URL не найден в переменных окружения")
        return None
    
    if not silent:
        print(f"  ✅ URL: {db_url}")
    
    match = re.match(r'postgres(?:ql)?://([^:]+):(.+)@([^:/]+):(\d+)/([^?]+)', db_url)
    if not match:
        match = re.match(r'postgres(?:ql)?://([^:]+):(.+)@([^:/]+)/([^?]+)', db_url)
        
    if not match:
        if not silent:
            print("  ❌ Не удалось распарсить DATABASE_URL")
        return None
        
    user, password, host, port_or_db, extra = match.groups()
    
    if port_or_db.isdigit():
        port = port_or_db
        dbname = extra
    else:
        port = "5432"
        dbname = port_or_db
        
    if not silent:
        print(f"  ✅ Хост: {host}, Порт: {port}, БД: {dbname}, Пользователь: {user}")
    return host, user, password, dbname


def find_database_container(db_host, silent=False):
    if not silent:
        print(f"🔍 Ищем контейнер БД по хосту '{db_host}'...")
    
    output = run("docker ps --format '{{.Names}}'")
    if not output:
        if not silent:
            print("  ❌ Не удалось получить список контейнеров")
        return None
    
    for container in output.split("\n"):
        if container.strip() == db_host:
            if not silent:
                print(f"  ✅ Найден: {container}")
            return container
    
    for container in output.split("\n"):
        if db_host in container:
            if not silent:
                print(f"  ✅ Найден (частичное совпадение): {container}")
            return container
    
    if not silent:
        print(f"  ❌ Контейнер с именем '{db_host}' не найден")
        print(f"  📋 Доступные контейнеры: {output.replace(chr(10), ', ')}")
    return None


def get_first_admin(backend_container, silent=False):
    if not silent:
        print("🔍 Получаем данные первого администратора из БД...")
    
    db_creds = get_db_credentials(backend_container, silent=silent)
    if not db_creds:
        if not silent:
            print("  ❌ Не удалось получить креды БД")
        return None
    
    db_host, db_user, db_password, db_name = db_creds
    
    db_container = find_database_container(db_host, silent=silent)
    if not db_container:
        if not silent:
            print("  ❌ Не удалось найти контейнер БД")
        return None
    
    psql_check = run(f"docker exec {db_container} which psql", check=False)
    if not psql_check:
        if not silent:
            print(f"  ⚠️  psql не найден в контейнере {db_container}")
        return None
    
    if not silent:
        print(f"  ✅ psql найден в {db_container}")
    
    safe_password = db_password.replace("'", "'\\''")
    
    query = "SELECT username FROM admin ORDER BY created_at ASC LIMIT 1;"
    cmd = f"docker exec -e PGPASSWORD='{safe_password}' {db_container} psql -U {db_user} -d {db_name} -t -A -c \"{query}\""
    
    if not silent:
        print(f"  📝 Выполняем запрос к БД...")
    
    result = run(cmd, check=False)
    
    if result and result.strip():
        if not silent:
            print(f"  ✅ Получен результат: {result.strip()}")
        return result.strip()
    
    if not silent:
        print(f"  ❌ Пустой результат от БД")
        test_cmd = f"docker exec -e PGPASSWORD='{safe_password}' {db_container} psql -U {db_user} -d {db_name} -c \"SELECT 1;\" 2>&1"
        test_result = run(test_cmd, check=False)
        if test_result:
            print(f"  🔍 Диагностический вывод: {test_result[:200]}")
    
    return None


def show_first_admin():
    print("=" * 60)
    print("  Поиск первого администратора")
    print("=" * 60)
    print()

    container = find_backend_container()
    if not container:
        sys.exit(1)

    print()
    username = get_first_admin(container, silent=False)
    
    if username:
        print()
        print("  ✅ Первый администратор найден!")
        print(f"  👤 Логин (username): \033[1m{username}\033[0m")
        print()
        print("  💡 Так как хеш пароля нельзя расшифровать, используйте ЛЮБОЙ пароль для входа.")
        print("     (При условии, что патч bypass.py уже применен!)")
        print()
    else:
        print()
        print("❌ Не удалось получить данные из базы данных.")
        print("   Возможно, таблица 'admin' пуста или структура БД изменилась.")


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
  python3 bypass.py --admin      # Показать первого администратора из БД
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--undo", action="store_true", help="Включить проверку пароля")
    parser.add_argument("--status", action="store_true", help="Проверить статус")
    parser.add_argument("--admin", action="store_true", help="Показать первого администратора из БД")

    args = parser.parse_args()

    print("=" * 60)
    print("  Remnawave Bypass Universal")
    print("=" * 60)
    print()

    if args.admin:
        print("🔍 РЕЖИМ: ПОИСК АДМИНИСТРАТОРА")
        print("-" * 60)
        print()
        show_first_admin()
        return

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
        
        username = get_first_admin(container, silent=False)
        
        if username:
            print()
            print(f"  👤 Логин первого админа: \033[1m{username}\033[0m")
            print("  💡 Используйте этот логин и ЛЮБОЙ пароль для входа!")
        else:
            print()
            print("  ⚠️  Не удалось получить логин админа")
            
        print()
        print("💡 Для отката: python3 bypass.py --undo")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
