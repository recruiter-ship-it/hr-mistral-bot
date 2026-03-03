#!/usr/bin/env python3
"""
Watchdog для HR бота 24/7
- Защита от множественных инстансов
- Автоматический перезапуск
- Проверка здоровья
"""
import subprocess
import time
import os
import signal
import sys
import fcntl
import requests

BOT_DIR = "/home/z/my-project/hr-mistral-bot"
BOT_SCRIPT = "bot.py"
PYTHON = "/usr/bin/python3"
LOG_FILE = os.path.join(BOT_DIR, "bot.log")
PID_FILE = os.path.join(BOT_DIR, "bot.pid")
LOCK_FILE = os.path.join(BOT_DIR, "bot.lock")
WATCHDOG_LOG = os.path.join(BOT_DIR, "watchdog.log")
BOT_TOKEN = "8399347076:AAFLtRxXEKESWuTQb19vc6mhMQph7rHxsLg"

def log(msg):
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(WATCHDOG_LOG, 'a') as f:
        f.write(line + "\n")

def kill_all_bots():
    """Убить ВСЕ процессы bot.py"""
    try:
        result = subprocess.run(["pgrep", "-f", "python.*bot.py"], capture_output=True, text=True)
        pids = [p for p in result.stdout.strip().split('\n') if p.isdigit()]
        for pid in pids:
            try:
                os.kill(int(pid), signal.SIGKILL)
                log(f"Killed bot PID {pid}")
            except:
                pass
        if pids:
            time.sleep(2)
    except Exception as e:
        log(f"Kill error: {e}")

def acquire_lock():
    """Получить эксклюзивную блокировку"""
    try:
        lock_file = open(LOCK_FILE, 'w')
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_file
    except IOError:
        return None

def start_bot():
    """Запустить бота"""
    kill_all_bots()
    
    # Очищаем лог
    with open(LOG_FILE, 'w') as f:
        f.write(f"=== Bot started at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    
    proc = subprocess.Popen(
        [PYTHON, BOT_SCRIPT],
        stdout=open(LOG_FILE, 'a'),
        stderr=subprocess.STDOUT,
        start_new_session=True,
        cwd=BOT_DIR
    )
    
    with open(PID_FILE, 'w') as f:
        f.write(str(proc.pid))
    
    log(f"Bot started PID {proc.pid}")
    return proc.pid

def is_running(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except:
        return False

def main():
    # Проверяем блокировку
    lock = acquire_lock()
    if not lock:
        print("Another watchdog already running!")
        sys.exit(1)
    
    log("=" * 50)
    log("Watchdog started - 24/7 monitoring")
    log("=" * 50)
    
    # Проверяем Telegram API
    try:
        r = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getMe", timeout=10)
        if r.status_code != 200:
            log("WARNING: Telegram API error")
    except Exception as e:
        log(f"WARNING: Network error: {e}")
    
    # Запускаем бота
    start_bot()
    time.sleep(10)
    
    checks = 0
    while True:
        try:
            checks += 1
            
            # Читаем PID
            try:
                with open(PID_FILE) as f:
                    pid = int(f.read().strip())
            except:
                pid = None
            
            running = is_running(pid)
            
            # Каждые 10 проверок логируем
            if checks % 10 == 0:
                log(f"Health check #{checks}: PID {pid} - {'OK' if running else 'DOWN'}")
            
            # Если не работает - перезапускаем
            if not running:
                log("Bot DOWN! Restarting...")
                start_bot()
                time.sleep(10)
                continue
            
            time.sleep(30)
            
        except KeyboardInterrupt:
            log("Watchdog stopped")
            break
        except Exception as e:
            log(f"Error: {e}")
            time.sleep(30)

if __name__ == "__main__":
    main()
