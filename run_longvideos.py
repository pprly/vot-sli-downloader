#!/usr/bin/env python3
"""
Пакетная обработка ДЛИННЫХ YouTube видео с переводом и живыми голосами
Версия для видео которые не прошли в основном скрипте (таймаут 20 минут)
"""
import subprocess
import sys
import os
from pathlib import Path
import time
import glob
import re
import sqlite3
from datetime import datetime
import threading
from queue import Queue
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from deep_translator import GoogleTranslator
    TRANSLATOR_AVAILABLE = True
except ImportError:
    TRANSLATOR_AVAILABLE = False
    print("⚠️ Для перевода названий установите: pip install deep-translator")

# Пути к файлам
FAILED_LOG = "failed.txt"
DATABASE = "processed_videos.db"
COOKIES_FILE = "cookies.txt"

# Настройки многопоточности
MAX_WORKERS = 1  # Меньше потоков для длинных видео

# УВЕЛИЧЕННЫЙ ТАЙМАУТ ДЛЯ ДЛИННЫХ ВИДЕО
LONG_VIDEO_TIMEOUT = 3000  # 20 минут вместо 5

# Блокировка для потокобезопасной работы с БД и выводом
db_lock = threading.Lock()
print_lock = threading.Lock()

def safe_print(*args, **kwargs):
    """Потокобезопасный вывод"""
    with print_lock:
        print(*args, **kwargs)

def extract_cookies_from_browser():
    """Извлечь cookies из браузера"""
    safe_print("🍪 Извлечение cookies из браузера...")
    
    # Пробуем извлечь из разных браузеров
    browsers = ['chrome', 'firefox', 'edge', 'opera', 'brave']
    
    for browser in browsers:
        try:
            result = subprocess.run(
                f'yt-dlp --cookies-from-browser {browser} --cookies {COOKIES_FILE} --skip-download "https://www.youtube.com/watch?v=dQw4w9WgXcQ"',
                shell=True,
                capture_output=True,
                timeout=30
            )
            
            if result.returncode == 0 and os.path.exists(COOKIES_FILE):
                safe_print(f"  ✅ Cookies извлечены из {browser.title()}")
                return True
        except Exception:
            continue
    
    safe_print("  ⚠️ Не удалось извлечь cookies из браузера")
    return False

def init_database():
    """Инициализировать базу данных"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS processed_videos (
            video_id TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            title TEXT,
            processed_at TEXT NOT NULL,
            file_size_kb REAL
        )
    ''')
    conn.commit()
    conn.close()

def is_video_processed(video_id):
    """Проверить обработано ли видео (потокобезопасно)"""
    with db_lock:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('SELECT video_id FROM processed_videos WHERE video_id = ?', (video_id,))
        result = cursor.fetchone()
        conn.close()
        return result is not None

def mark_video_processed(video_id, url, title, file_size_kb):
    """Отметить видео как обработанное (потокобезопасно)"""
    with db_lock:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO processed_videos (video_id, url, title, processed_at, file_size_kb)
            VALUES (?, ?, ?, ?, ?)
        ''', (video_id, url, title, datetime.now().isoformat(), file_size_kb))
        conn.commit()
        conn.close()

def log_failed_video(url, reason):
    """Записать неудачное видео в лог (потокобезопасно)"""
    with db_lock:
        with open(FAILED_LOG, 'a', encoding='utf-8') as f:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            f.write(f"[{timestamp}] {url} - {reason}\n")

def clean_youtube_url(url):
    """Очистить URL от параметров плейлиста и конвертировать shorts"""
    # Конвертируем shorts в обычный формат
    if '/shorts/' in url:
        match = re.search(r'/shorts/([0-9A-Za-z_-]{11})', url)
        if match:
            video_id = match.group(1)
            return f"https://www.youtube.com/watch?v={video_id}", True
    
    # Обычная очистка URL
    patterns = [
        r'(?:v=|/)([0-9A-Za-z_-]{11}).*',
        r'youtu\.be/([0-9A-Za-z_-]{11}).*',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            video_id = match.group(1)
            return f"https://www.youtube.com/watch?v={video_id}", False
    
    return url, False

def extract_video_id(url):
    """Извлечь video ID из URL"""
    patterns = [
        r'(?:v=|/)([0-9A-Za-z_-]{11})',
        r'youtu\.be/([0-9A-Za-z_-]{11})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def sanitize_filename(filename):
    """Очистить имя файла от недопустимых символов"""
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '')
    return filename.strip()[:200] if filename else "video"

def translate_to_russian(text):
    """Перевести текст на русский"""
    if not TRANSLATOR_AVAILABLE or not text:
        return text
    
    try:
        translated = GoogleTranslator(source='auto', target='ru').translate(text)
        return translated if translated else text
    except Exception:
        return text

def get_video_title(url, translate=True):
    """Получить название видео с YouTube"""
    try:
        # Используем строку для лучшей совместимости с Windows
        cmd = f'yt-dlp --print title --no-warnings'
        
        if os.path.exists(COOKIES_FILE):
            cmd += f' --cookies "{COOKIES_FILE}"'
        
        cmd += f' "{url}"'
        
        # Для Windows используем системную кодировку (cp1251/cp866)
        import sys
        encoding = sys.stdout.encoding if sys.stdout.encoding else 'utf-8'
        
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            encoding=encoding,
            errors='ignore'  # Игнорируем ошибки кодировки
        )
        
        if result.returncode == 0:
            title = result.stdout.strip()
            
            if not title:
                return None
            
            # Переводим на русский если нужно
            if translate and TRANSLATOR_AVAILABLE:
                translated = translate_to_russian(title)
                if translated:
                    title = translated
            
            return sanitize_filename(title)
    except Exception:
        pass
    return None

def load_urls_from_failed_log():
    """Загрузить URL из failed.txt"""
    if not os.path.exists(FAILED_LOG):
        return []
    
    urls = []
    with open(FAILED_LOG, 'r', encoding='utf-8') as f:
        for line in f:
            # Извлекаем URL из строки лога
            # Формат: [timestamp] URL - reason
            match = re.search(r'\] (https?://[^\s]+) -', line)
            if match:
                url = match.group(1)
                urls.append(url)
    
    # Убираем дубликаты
    return list(set(urls))

def process_single_video(url, output_dir="output", video_volume=0.05, translation_volume=0.58, translate_names=True):
    """
    Обработка одного ДЛИННОГО видео (для многопоточности)
    Возвращает: (success: bool, video_id: str, message: str)
    """
    # Очищаем URL и определяем тип
    clean_url, is_short = clean_youtube_url(url)
    video_id = extract_video_id(clean_url)
    
    if not video_id:
        return False, None, f"Невалидный URL: {url}"
    
    # Проверяем обработано ли уже
    if is_video_processed(video_id):
        return False, video_id, f"Видео {video_id} уже обработано"
    
    video_type = "📱 Shorts" if is_short else "📹 Длинное видео"
    target_dir = f"{output_dir}/{'shorts' if is_short else 'videos'}"
    Path(target_dir).mkdir(parents=True, exist_ok=True)
    
    # Создаём уникальную папку для этого видео (избегаем конфликтов)
    unique_id = str(uuid.uuid4())[:8]
    temp_dir = f"{target_dir}/temp_{video_id}_{unique_id}"
    Path(temp_dir).mkdir(exist_ok=True)
    
    try:
        safe_print(f"\n🎬 {video_type} [{video_id}] Начинаю обработку (таймаут 20 минут)...")
        
        # ========== ЭТАП 1: Скачивание озвучки ==========
        safe_print(f"  🎤 [{video_id}] Скачивание озвучки (это может занять до 20 минут)...")
        
        cmd = f'npx vot-cli-live --voice-style live --output "{temp_dir}" "{clean_url}"'
        
        try:
            process = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # УВЕЛИЧЕННЫЙ ТАЙМАУТ: 20 минут для длинных видео
            safe_print(f"  ⏱️  [{video_id}] Жду до 20 минут на перевод...")
            process.communicate(timeout=LONG_VIDEO_TIMEOUT)
            returncode = process.returncode
            
        except subprocess.TimeoutExpired:
            safe_print(f"  ⏱️ [{video_id}] Таймаут (20 мин), убиваю процесс...")
            
            try:
                process.terminate()
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=2)
                except Exception:
                    pass
            
            log_failed_video(url, "Таймаут 20 минут (очень длинное видео)")
            return False, video_id, f"Таймаут даже при 20 минутах - видео слишком длинное"
        
        if returncode != 0:
            log_failed_video(url, f"Ошибка VOT (код {returncode})")
            return False, video_id, f"Ошибка скачивания озвучки (код {returncode})"
        
        # Ждём и проверяем mp3
        time.sleep(1)
        mp3_files = glob.glob(f"{temp_dir}/*.mp3")
        
        if not mp3_files:
            log_failed_video(url, "MP3 файл не создан")
            return False, video_id, "MP3 файл не создан"
        
        # Берём первый mp3 (в temp_dir только один файл)
        temp_audio = mp3_files[0]
        file_size = os.path.getsize(temp_audio) / 1024  # KB
        
        if file_size < 10:
            log_failed_video(url, f"Видео без речи ({file_size:.1f}KB)")
            return False, video_id, f"Видео без речи ({file_size:.1f}KB)"
        
        safe_print(f"  ✅ [{video_id}] Озвучка скачана ({file_size:.1f}KB)")
        
        # Пауза между запросами к VOT
        time.sleep(5)
        
        # ========== ЭТАП 2: Получение названия ==========
        safe_print(f"  🔍 [{video_id}] Получение названия...")
        title = get_video_title(clean_url, translate=translate_names)
        base_name = title if title else video_id
        
        # Добавляем video_id к имени для уникальности
        base_name_unique = f"{base_name}_{video_id}"
        safe_print(f"  📝 [{video_id}] Название: {base_name}")
        
        # ========== ЭТАП 3: Скачивание видео ==========
        safe_print(f"  📥 [{video_id}] Скачивание видео...")
        
        video_file = f"{temp_dir}/video.mp4"
        
        cmd = f'yt-dlp -f "bestvideo[height<=1080]+ba[language=ru]/bestvideo[height<=1080]+ba/best" --merge-output-format mp4 --write-thumbnail --convert-thumbnails jpg'
        
        if os.path.exists(COOKIES_FILE):
            cmd += f' --cookies "{COOKIES_FILE}"'
        
        cmd += f' -o "{video_file}" "{clean_url}"'
        
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, errors='ignore')
        
        # Главное - проверяем что файл создан (warnings не важны)
        if not os.path.exists(video_file):
            # Если файла нет - логируем последние строки ошибки
            error_lines = result.stderr.split('\n') if result.stderr else []
            error_msg = '\n'.join([line for line in error_lines if 'ERROR' in line.upper()][-3:])
            if not error_msg:
                error_msg = "Файл не создан, причина неизвестна"
            safe_print(f"  ❌ [{video_id}] yt-dlp error: {error_msg}")
            log_failed_video(url, f"Ошибка yt-dlp: {error_msg}")
            return False, video_id, "Файл видео не создан"
        
        safe_print(f"  ✅ [{video_id}] Видео скачано")
        
        # ========== ЭТАП 4: Микширование ==========
        safe_print(f"  🔊 [{video_id}] Микширование (Оригинал {int(video_volume*100)}%, Перевод {int(translation_volume*100)}%)...")
        
        final_file = f"{target_dir}/{base_name_unique}.mp4"
        
        cmd = f'ffmpeg -i "{video_file}" -i "{temp_audio}" -filter_complex "[0:a]volume={video_volume}[a1];[1:a]volume={translation_volume}[a2];[a1][a2]amix=inputs=2:duration=shortest[aout]" -map 0:v -map "[aout]" -c:v copy -y "{final_file}"'
        result = subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        if result.returncode != 0:
            log_failed_video(url, "Ошибка микширования через ffmpeg")
            return False, video_id, "Ошибка микширования"
        
        # ========== ЭТАП 5: Сохранение превью ==========
        thumbnail_patterns = [
            f"{temp_dir}/video.jpg",
            f"{temp_dir}/video.webp",
        ]
        
        thumbnail_file = f"{target_dir}/{base_name_unique}.jpg"
        
        for pattern in thumbnail_patterns:
            if os.path.exists(pattern):
                try:
                    # Конвертируем webp в jpg если нужно
                    if pattern.endswith('.webp'):
                        subprocess.run(
                            f'ffmpeg -i "{pattern}" -y "{thumbnail_file}"',
                            shell=True,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL
                        )
                    else:
                        os.rename(pattern, thumbnail_file)
                    break
                except Exception:
                    pass
        
        # Получаем размер финального файла
        final_file_size = os.path.getsize(final_file) / 1024  # KB
        
        # Сохраняем в базу данных
        mark_video_processed(video_id, url, base_name, final_file_size)
        
        safe_print(f"  ✅ [{video_id}] Готово: {base_name}.mp4 ({final_file_size/1024:.1f}MB)")
        if os.path.exists(thumbnail_file):
            safe_print(f"  🖼️ [{video_id}] Превью: {base_name}.jpg")
        
        return True, video_id, "Успешно обработано"
        
    except Exception as e:
        log_failed_video(url, f"Неожиданная ошибка: {str(e)}")
        return False, video_id, f"Ошибка: {str(e)}"
    
    finally:
        # Очистка временной папки
        try:
            import shutil
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
        except Exception:
            pass

def process_batch_parallel(urls, output_dir="output", video_volume=0.05, translation_volume=0.58, translate_names=True, max_workers=MAX_WORKERS):
    """
    Параллельная обработка пакета ДЛИННЫХ видео
    """
    # Инициализируем базу данных
    init_database()
    
    # Проверяем наличие cookies
    if not os.path.exists(COOKIES_FILE):
        extract_cookies_from_browser()
    else:
        safe_print(f"🍪 Используем существующий файл cookies: {COOKIES_FILE}")
    
    Path(output_dir).mkdir(exist_ok=True)
    Path(f"{output_dir}/videos").mkdir(exist_ok=True)
    Path(f"{output_dir}/shorts").mkdir(exist_ok=True)
    
    # Фильтруем уже обработанные
    new_urls = []
    skipped_count = 0
    
    for url in urls:
        clean_url, _ = clean_youtube_url(url)
        video_id = extract_video_id(clean_url)
        
        if video_id and is_video_processed(video_id):
            safe_print(f"⏭️  Видео {video_id} уже обработано, пропускаю")
            skipped_count += 1
        else:
            new_urls.append(url)
    
    if skipped_count > 0:
        safe_print(f"📊 Пропущено уже обработанных: {skipped_count}")
    
    if not new_urls:
        safe_print("\n✅ Все видео уже обработаны!")
        return
    
    safe_print(f"\n{'='*60}")
    safe_print(f"📋 К обработке: {len(new_urls)} длинных видео")
    safe_print(f"⏱️  Таймаут на видео: 20 минут")
    safe_print(f"🔄 Параллельных потоков: {max_workers}")
    if translate_names and TRANSLATOR_AVAILABLE:
        safe_print("🌍 Перевод названий: включен")
    safe_print(f"{'='*60}\n")
    
    # Параллельная обработка
    success_count = 0
    failed_count = 0
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Запускаем все задачи
        future_to_url = {
            executor.submit(
                process_single_video,
                url,
                output_dir,
                video_volume,
                translation_volume,
                translate_names
            ): url for url in new_urls
        }
        
        # Собираем результаты по мере выполнения
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                success, video_id, message = future.result()
                if success:
                    success_count += 1
                else:
                    failed_count += 1
                    if video_id:
                        safe_print(f"⚠️  [{video_id}] {message}")
            except Exception as e:
                failed_count += 1
                safe_print(f"❌ Ошибка обработки {url}: {e}")
    
    # Итоговая статистика
    safe_print(f"\n{'='*60}")
    safe_print(f"🎉 Обработка длинных видео завершена!")
    safe_print(f"✅ Успешно: {success_count}")
    safe_print(f"❌ Ошибок: {failed_count}")
    safe_print(f"📂 Обычные видео: {os.path.abspath(output_dir)}/videos")
    safe_print(f"📱 Shorts: {os.path.abspath(output_dir)}/shorts")
    if os.path.exists(FAILED_LOG):
        safe_print(f"⚠️  Лог ошибок: {os.path.abspath(FAILED_LOG)}")
    safe_print(f"💾 База данных: {os.path.abspath(DATABASE)}")
    safe_print(f"{'='*60}")

def main():
    """Главная функция"""
    safe_print("🚀 YouTube Long Videos Dubbing Tool (20 min timeout)")
    safe_print("="*60)
    
    # Загружаем URL из failed.txt
    if os.path.exists(FAILED_LOG):
        urls = load_urls_from_failed_log()
        if urls:
            safe_print(f"📄 Загружено {len(urls)} URL из {FAILED_LOG}")
            safe_print(f"⏱️  Таймаут: 20 минут на каждое видео")
        else:
            safe_print(f"⚠️  Файл {FAILED_LOG} пуст или не содержит URL!")
            safe_print(f"💡 Сначала запустите основной скрипт (dub2.bat)")
            input("\nНажмите Enter для выхода...")
            return
    else:
        safe_print(f"⚠️  Файл {FAILED_LOG} не найден!")
        safe_print(f"💡 Сначала запустите основной скрипт (dub2.bat)")
        safe_print(f"   После него появится файл с проблемными видео")
        input("\nНажмите Enter для выхода...")
        return
    
    # Запускаем обработку
    try:
        process_batch_parallel(urls, translate_names=True, max_workers=MAX_WORKERS)
    except KeyboardInterrupt:
        safe_print("\n\n⚠️  Прервано пользователем (Ctrl+C)")
        safe_print("💡 Обработанные видео сохранены в базе данных")
    except Exception as e:
        safe_print(f"\n\n❌ Критическая ошибка: {e}")
    
    input("\nНажмите Enter для выхода...")

if __name__ == "__main__":
    main()
