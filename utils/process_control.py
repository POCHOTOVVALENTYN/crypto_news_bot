import os
import sys
import logging

logger = logging.getLogger(__name__)

PID_FILE = "bot.pid"

def check_single_instance():
    """
    Проверяет, не запущен ли уже бот. 
    Если запущен - завершает работу.
    Если нет - создает PID файл.
    """
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, 'r') as f:
                old_pid = int(f.read().strip())
            
            # Проверяем, жив ли процесс
            try:
                os.kill(old_pid, 0) # 0 signal does not kill, just checks existence
                logger.critical(f"⛔️ Бот уже запущен (PID: {old_pid}). Остановка нового экземпляра.")
                print(f"⛔️ Бот уже запущен (PID: {old_pid}). Остановка.")
                sys.exit(1)
            except OSError:
                # Процесса нет, PID файл остался от краша
                logger.warning(f"⚠️ Найден старый PID файл ({old_pid}), но процесс мертв. Удаляем.")
                os.remove(PID_FILE)
        except ValueError:
             # PID файл поврежден
            logger.warning("⚠️ PID файл поврежден. Удаляем.")
            os.remove(PID_FILE)

    # Пишем свой PID
    pid = os.getpid()
    with open(PID_FILE, 'w') as f:
        f.write(str(pid))
    
    logger.info(f"🔒 PID файл создан: {pid}")

def cleanup_pid():
    """Удаляет PID файл при выходе"""
    if os.path.exists(PID_FILE):
        try:
            os.remove(PID_FILE)
            logger.info("🔓 PID файл удален")
        except Exception as e:
            logger.error(f"❌ Не удалось удалить PID файл: {e}")
