#!/usr/bin/env python3
"""
Пакетная обработка YouTube видео с переводом и живыми голосами
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

def extract_cookies_from_browser():
    """Извлечь cookies из браузера"""
    print("🍪 Извлечение cookies из браузера...")
    
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
                print(f"  ✅ Cookies извлечены из {browser.title()}")
                return True
        except:
            continue
    
    print("  ⚠️ Не удалось извлечь cookies из браузера")
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
    """Проверить обработано ли видео"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT video_id FROM processed_videos WHERE video_id = ?', (video_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def mark_video_processed(video_id, url, title, file_size_kb):
    """Отметить видео как обработанное"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO processed_videos (video_id, url, title, processed_at, file_size_kb)
        VALUES (?, ?, ?, ?, ?)
    ''', (video_id, url, title, datetime.now().isoformat(), file_size_kb))
    conn.commit()
    conn.close()

def log_failed_video(url, reason):
    """Записать неудачное видео в лог"""
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
            return f"https://www.youtube.com/watch?v={video_id}"
    
    # Обычная очистка URL
    patterns = [
        r'(?:v=|/)([0-9A-Za-z_-]{11}).*',
        r'youtu\.be/([0-9A-Za-z_-]{11}).*',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            video_id = match.group(1)
            return f"https://www.youtube.com/watch?v={video_id}"
    
    return url

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
    except:
        return text

def get_video_title(url, translate=True):
    """Получить название видео с YouTube"""
    try:
        cmd = ['yt-dlp', '--print', 'title', '--extractor-args', 'youtube:lang=ru']
        
        if os.path.exists(COOKIES_FILE):
            cmd.extend(['--cookies', COOKIES_FILE])
        
        cmd.append(url)
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            shell=True
        )
        
        if result.returncode == 0:
            title = result.stdout.strip()
            
            # Переводим на русский если нужно
            if translate and TRANSLATOR_AVAILABLE:
                print(f"  🔤 Оригинал: {title}")
                translated = translate_to_russian(title)
                print(f"  🇷🇺 Перевод: {translated}")
                title = translated
            
            return sanitize_filename(title)
    except:
        pass
    return None

def is_shorts_url(url):
    """Проверить является ли URL шортсом"""
    return '/shorts/' in url

def process_batch(urls, output_dir="output", video_volume=0.05, translation_volume=0.58, translate_names=True):
    """
    Обработка пакета видео
    """
    # Инициализируем базу данных
    init_database()
    
    # Проверяем наличие cookies, если нет - пробуем извлечь
    if not os.path.exists(COOKIES_FILE):
        extract_cookies_from_browser()
    else:
        print(f"🍪 Используем существующий файл cookies: {COOKIES_FILE}")
    
    Path(output_dir).mkdir(exist_ok=True)
    
    # Создаём отдельные папки для обычных видео и шортсов
    videos_dir = f"{output_dir}/videos"
    shorts_dir = f"{output_dir}/shorts"
    Path(videos_dir).mkdir(exist_ok=True)
    Path(shorts_dir).mkdir(exist_ok=True)
    
    # Очищаем URL от параметров плейлиста
    clean_urls = [clean_youtube_url(url) for url in urls]
    
    # Фильтруем уже обработанные видео
    new_urls = []
    skipped_count = 0
    
    for url, original_url in zip(clean_urls, urls):
        video_id = extract_video_id(url)
        if video_id and is_video_processed(video_id):
            print(f"⏭️  Видео {video_id} уже обработано, пропускаю")
            skipped_count += 1
        else:
            new_urls.append((url, original_url))
    
    if skipped_count > 0:
        print(f"📊 Пропущено уже обработанных: {skipped_count}")
    
    if not new_urls:
        print("\n✅ Все видео уже обработаны!")
        return
    
    print(f"📋 К обработке: {len(new_urls)} новых видео")
    if translate_names and TRANSLATOR_AVAILABLE:
        print("🌍 Перевод названий: включен")
    print("📂 Обычные видео → videos/")
    print("📱 Shorts → shorts/")
    print("="*60)
    
    # 1. Скачать озвучки по одной (с таймаутом на каждую)
    print("🎤 Этап 1: Скачивание озвучек с живыми голосами...")
    
    downloaded_urls = []
    
    for i, (url, original_url) in enumerate(new_urls, 1):
        is_short = is_shorts_url(original_url)
        video_type = "📱 Shorts" if is_short else "📹 Видео"
        target_dir = shorts_dir if is_short else videos_dir
        video_id = extract_video_id(url)
        
        print(f"\n[{i}/{len(new_urls)}] {video_type} - Скачивание озвучки...")
        print(f"  🆔 ID: {video_id}")
        
        cmd = f'npx vot-cli-live --voice-style live --output "{target_dir}" "{url}"'
        
        try:
            # Таймаут 3 минуты на озвучку
            print(f"  ⏱️  Максимум 5 минуты на перевод...")
            
            process = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            try:
                # Ждём завершения с таймаутом
                process.communicate(timeout=700)
                returncode = process.returncode
            except subprocess.TimeoutExpired:
                # Принудительно убиваем процесс
                print(f"  ⏱️ Таймаут (3 мин), убиваю процесс...")
                
                try:
                    process.terminate()  # Сначала мягко
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()  # Потом жёстко
                    try:
                        process.wait(timeout=2)
                    except:
                        pass
                
                print(f"  ⚠️ Видео пропущено")
                log_failed_video(url, "Таймаут 3 минуты")
                time.sleep(5)
                continue
            
            if returncode == 0:
                # Проверяем что mp3 файл действительно создан
                time.sleep(2)
                mp3_check = glob.glob(f"{target_dir}/*.mp3")
                
                if mp3_check:
                    # Проверяем размер файла
                    latest_mp3 = max(mp3_check, key=os.path.getctime)
                    file_size = os.path.getsize(latest_mp3) / 1024  # в KB
                    
                    if file_size < 10:
                        print(f"  ⚠️ Видео без речи (файл {file_size:.1f}KB), пропускаю")
                        log_failed_video(url, f"Видео без речи ({file_size:.1f}KB)")
                        os.remove(latest_mp3)
                    else:
                        downloaded_urls.append((url, original_url, target_dir, video_id))
                        print(f"  ✅ Озвучка скачана ({file_size:.1f}KB)")
                else:
                    print(f"  ⚠️ MP3 файл не создан, пропускаю")
                    log_failed_video(url, "MP3 файл не создан")
            else:
                print(f"  ⚠️ Ошибка скачивания озвучки, пропускаю")
                log_failed_video(url, f"Ошибка VOT (код {returncode})")
            
            # Пауза 5 секунд между запросами к VOT
            print(f"  ⏸️  Пауза 5 сек...")
            time.sleep(5)
            
        except Exception as e:
            print(f"  ❌ Неожиданная ошибка: {e}")
            log_failed_video(url, f"Ошибка: {str(e)}")
            continue
    
    if not downloaded_urls:
        print("\n❌ Ни одна озвучка не скачалась")
        return
    
    time.sleep(2)
    
    # 2. Обрабатываем только успешно скачанные
    print("\n📹 Этап 2: Скачивание видео и микширование...")
    print("="*60)
    
    success_count = 0
    
    for i, (url, original_url, target_dir, video_id) in enumerate(downloaded_urls, 1):
        is_short = is_shorts_url(original_url)
        video_type = "📱 Shorts" if is_short else "📹 Видео"
        
        print(f"\n[{i}/{len(downloaded_urls)}] {video_type} - Обработка...")
        print(f"  🆔 ID: {video_id}")
        
        # Получаем название видео (с переводом если включено)
        print(f"  🔍 Получение информации...")
        title = get_video_title(url, translate=translate_names)
        
        # Используем название или ID
        base_name = title if title else video_id
        print(f"  📝 Финальное название: {base_name}")
        
        # Ищем скачанный mp3 в нужной папке
        mp3_files = glob.glob(f"{target_dir}/*.mp3")
        
        if not mp3_files:
            print(f"⚠️ Аудио файл не найден")
            log_failed_video(url, "Аудио файл потерян перед обработкой")
            continue
        
        # Берём последний mp3
        temp_audio = max(mp3_files, key=os.path.getctime)
        
        # Пути к файлам в нужной папке
        video_file = os.path.abspath(f"{target_dir}/{base_name}_temp.mp4")
        final_file = os.path.abspath(f"{target_dir}/{base_name}.mp4")
        thumbnail_file = f"{target_dir}/{base_name}.jpg"
        
        # Скачать видео с превью
        print(f"  📥 Скачивание видео с превью...")
        
        # Формируем команду с cookies
        cmd = f'yt-dlp -f "bestvideo[height<=1080]+ba[language=ru]/bestvideo[height<=1080]+ba/best" --merge-output-format mp4 --write-thumbnail --convert-thumbnails jpg --extractor-args "youtube:lang=ru"'
        
        if os.path.exists(COOKIES_FILE):
            cmd += f' --cookies "{COOKIES_FILE}"'
        
        cmd += f' -o "{video_file}" "{url}"'
        
        result = subprocess.run(cmd, shell=True)
        
        if result.returncode != 0 or not os.path.exists(video_file):
            print(f"  ❌ Ошибка скачивания видео")
            log_failed_video(url, "Ошибка скачивания видео через yt-dlp")
            continue
        
        # Микшировать
        print(f"  🔊 Микширование (Оригинал {int(video_volume*100)}%, Перевод {int(translation_volume*100)}%)...")
        
        abs_audio = os.path.abspath(temp_audio)
        
        cmd = f'ffmpeg -i "{video_file}" -i "{abs_audio}" -filter_complex "[0:a]volume={video_volume}[a1];[1:a]volume={translation_volume}[a2];[a1][a2]amix=inputs=2:duration=shortest[aout]" -map 0:v -map "[aout]" -c:v copy -y "{final_file}"'
        result = subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        if result.returncode == 0:
            # Ищем и переименовываем превью от yt-dlp
            temp_thumbnail_patterns = [
                f"{target_dir}/{base_name}_temp.jpg",
                f"{target_dir}/{base_name}_temp.webp",
                f"{target_dir}/{Path(temp_audio).stem}.jpg",
            ]
            
            for pattern in temp_thumbnail_patterns:
                if os.path.exists(pattern):
                    try:
                        os.rename(pattern, thumbnail_file)
                        break
                    except:
                        pass
            
            # Получаем размер финального файла
            final_file_size = os.path.getsize(final_file) / 1024  # KB
            
            # Сохраняем в базу данных
            mark_video_processed(video_id, url, base_name, final_file_size)
            
            # Очистка
            try:
                os.remove(temp_audio)
                if os.path.exists(video_file):
                    os.remove(video_file)
            except:
                pass
            
            print(f"  ✅ Готово: {base_name}.mp4 ({final_file_size/1024:.1f}MB)")
            if os.path.exists(thumbnail_file):
                print(f"  🖼️ Превью: {base_name}.jpg")
            print(f"  💾 Сохранено в базу данных")
            success_count += 1
        else:
            print(f"  ❌ Ошибка микшированиsя")
            log_failed_video(url, "Ошибка микширования через ffmpeg")
    
    print("\n" + "="*60)
    print(f"🎉 Успешно обработано: {success_count}/{len(new_urls)}")
    print(f"📂 Обычные видео: {os.path.abspath(videos_dir)}")
    print(f"📱 Shorts: {os.path.abspath(shorts_dir)}")
    if os.path.exists(FAILED_LOG):
        print(f"⚠️  Лог ошибок: {os.path.abspath(FAILED_LOG)}")
    print(f"💾 База данных: {os.path.abspath(DATABASE)}")
    print("="*60)
    
def main():
    if len(sys.argv) < 2:
        print("Использование: python run.py 'URL1, URL2, URL3'")
        input("\nНажмите Enter для выхода...")
        return
    
    urls_str = sys.argv[1]
    urls = [url.strip() for url in urls_str.split(',') if url.strip()]
    
    if not urls:
        print("❌ Не указаны ссылки")
        input("\nНажмите Enter для выхода.,..")
        return
    
    process_batch(urls, translate_names=True)
    input("\nНажмите Enter для выхода...")

if __name__ == "__main__":
    main()