import os
import sys
import shutil
import atexit
import argparse
import subprocess
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple
from yt_dlp import YoutubeDL
from yt_dlp.utils import download_range_func
from dotenv import load_dotenv

# Cargar variables de entorno desde el archivo .env
load_dotenv()

# =====================================================================
# Configuración Global y Constantes por Defecto (Cargadas desde .env)
# =====================================================================
DEFAULT_OUTPUT_FOLDER: str = os.getenv("OUTPUT_FOLDER", "downloads")
DEFAULT_CACHE_FILE: str = os.getenv("CACHE_FILE", ".last_download")
DEFAULT_FFMPEG_LOCATION: Optional[str] = os.getenv("FFMPEG_LOCATION")
DEFAULT_MERGE_FORMAT: str = os.getenv("MERGE_OUTPUT_FORMAT", "mp4")
DEFAULT_AUDIO_FORMAT: str = os.getenv("AUDIO_OUTPUT_FORMAT", "mp3")
DEFAULT_VIDEO_ENCODER: str = os.getenv("VIDEO_ENCODER", "libx264")
DEFAULT_AUDIO_BITRATE: str = os.getenv("AUDIO_BITRATE", "128k")
DEFAULT_ENCODE_PRESET: str = os.getenv("ENCODE_PRESET", "medium")
DEFAULT_SLEEP_INTERVAL: int = int(os.getenv("SLEEP_INTERVAL_DEFAULT", 3))
DEFAULT_RATELIMIT: str = os.getenv("DEFAULT_RATELIMIT", "10M")
DEFAULT_COMPRESS_CRF: int = int(os.getenv("COMPRESS_CRF", 28))
DEFAULT_RETRIES: int = int(os.getenv("DOWNLOAD_RETRIES", 3))
DEFAULT_CONCURRENT_FRAGMENTS: int = int(os.getenv("CONCURRENT_FRAGMENTS", 4))
DEFAULT_MAX_FILENAME_LENGTH: int = int(os.getenv("MAX_FILENAME_LENGTH", 120))

SUPPORTED_LANGUAGES: Dict[str, str] = {
    'es': 'Español',
    'es-orig': 'Español (Original)',
    'es-419': 'Español (Latinoamérica)',
    'en': 'English',
    'en-US': 'English (US)',
    'en-US-orig': 'English (US Original)',
    'pt': 'Português',
    'pt-PT': 'Português (Portugal)',
    'pt-BR': 'Português (Brasil)',
    'pt-BR-orig': 'Português (Brasil Original)',
}


class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    MAGENTA = '\033[35m'
    YELLOW = '\033[93m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


@dataclass
class DownloadConfig:
    """Objeto de configuración de descarga unificado (Data Transfer Object)."""
    audio_only: bool = False
    audio_format: str = DEFAULT_AUDIO_FORMAT
    cookies_browser: Optional[str] = None
    cookie_file: Optional[str] = None
    no_cookies: bool = False
    subtitles: Optional[str] = None
    clean_raw: bool = False
    compress: bool = False
    sleep_interval: int = DEFAULT_SLEEP_INTERVAL
    verbose: bool = False
    no_history: bool = False
    time_range: Optional[str] = None
    organize: bool = False
    notify: bool = False
    ratelimit: Optional[str] = None
    sponsorblock: bool = False
    split_chapters: bool = False
    allow_playlist: bool = False
    playlist_items: Optional[str] = None
    custom_format: Optional[str] = None
    custom_resolution: Optional[str] = None


class MediaGrabber:
    def __init__(self, output_folder: Optional[str] = None, cache_filename: Optional[str] = None, 
                 ffmpeg_location: Optional[str] = None, merge_format: Optional[str] = None) -> None:
        self.output_folder: str = output_folder or DEFAULT_OUTPUT_FOLDER
        cache_name: str = cache_filename or DEFAULT_CACHE_FILE
        self.cache_file: str = os.path.join(self.output_folder, cache_name)

        self.ffmpeg_location: str = self._resolve_ffmpeg(ffmpeg_location)
        self.merge_output_format: str = merge_format or DEFAULT_MERGE_FORMAT

        self.current_url: Optional[str] = None
        self.no_cache_enabled: bool = False

        atexit.register(self._save_cache_on_exit)

    def _resolve_ffmpeg(self, custom_location: Optional[str]) -> str:
        env_ffmpeg = DEFAULT_FFMPEG_LOCATION
        if env_ffmpeg and os.path.exists(env_ffmpeg):
            return env_ffmpeg
        if custom_location and os.path.exists(custom_location):
            return custom_location
        return shutil.which("ffmpeg") or "ffmpeg"

    # ------------------------------------------------------------------
    # Ejecución DRY de Subprocesos
    # ------------------------------------------------------------------
    def _run_system_command(self, cmd: List[str], success_message: str, error_context: str) -> bool:
        """Método unificado para ejecutar comandos de sistema y manejar errores."""
        try:
            result = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace"
            )
            if result.returncode == 0:
                if success_message:
                    print(f"{Colors.GREEN}[✔ Success]{Colors.ENDC} {success_message}")
                return True
            else:
                print(f"{Colors.FAIL}[!]{Colors.ENDC} {error_context} warning: {result.stderr}")
                return False
        except Exception as e:
            print(f"{Colors.FAIL}[!]{Colors.ENDC} {error_context} error: {str(e)}")
            return False

    # ------------------------------------------------------------------
    # Notificaciones del Sistema
    # ------------------------------------------------------------------
    @staticmethod
    def _send_desktop_notification(title: str, message: str) -> None:
        """Envía una notificación nativa del sistema según el sistema operativo."""
        try:
            if sys.platform == "win32":
                ps_script = f'''
                [void] [System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms")
                $objNotifyIcon = New-Object System.Windows.Forms.NotifyIcon
                $objNotifyIcon.Icon = [System.Drawing.SystemIcons]::Information
                $objNotifyIcon.BalloonTipIcon = "Info"
                $objNotifyIcon.BalloonTipTitle = "{title}"
                $objNotifyIcon.BalloonTipText = "{message}"
                $objNotifyIcon.Visible = $True
                $objNotifyIcon.ShowBalloonTip(5000)
                '''
                subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], 
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif sys.platform == "darwin":
                cmd = f'display notification "{message}" with title "{title}"'
                subprocess.run(["osascript", "-e", cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif sys.platform.startswith("linux"):
                subprocess.run(["notify-send", title, message], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Gestión del Caché de Sesión
    # ------------------------------------------------------------------
    def _save_cache_on_exit(self) -> None:
        if not self.no_cache_enabled and self.current_url:
            try:
                os.makedirs(self.output_folder, exist_ok=True)
                with open(self.cache_file, "w", encoding="utf-8") as f:
                    f.write(self.current_url)
                print(f"\n{Colors.BLUE}[i]{Colors.ENDC} Cache saved for URL: {self.current_url}")
            except Exception:
                pass

    def load_cached_url(self) -> Optional[str]:
        if not self.no_cache_enabled and os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    url = f.read().strip()
                    return url if url else None
            except Exception:
                return None
        return None

    def clear_cache(self) -> None:
        self.current_url = None
        if os.path.exists(self.cache_file):
            try:
                os.remove(self.cache_file)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Auditoría de Errores (URLs Fallidas)
    # ------------------------------------------------------------------
    def log_failed_url(self, url: str, error_msg: str = "Unknown error") -> None:
        try:
            os.makedirs(self.output_folder, exist_ok=True)
            log_path = os.path.join(self.output_folder, "failed_urls.txt")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"{url} # Error: {error_msg}\n")
            print(f"{Colors.WARNING}[⚠️ Audit]{Colors.ENDC} Failed URL recorded in '{log_path}'")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Formateo e Interfaz
    # ------------------------------------------------------------------
    @staticmethod
    def format_bytes(b: Optional[float]) -> str:
        if not b:
            return ""
        for unit in ['B', 'KiB', 'MiB', 'GiB', 'TiB']:
            if b < 1024.0:
                return f"{b:.2f} {unit}"
            b /= 1024.0
        return f"{b:.2f} PiB"

    @classmethod
    def progress_hook(cls, d: Dict[str, Any]) -> None:
        status = d.get('status')

        if status == 'downloading':
            percent = d.get('_percent_str')
            if percent:
                percent = percent.strip()
            else:
                downloaded = d.get('downloaded_bytes', 0)
                percent = cls.format_bytes(downloaded) if downloaded else "Processing..."

            speed = d.get('_speed_str', 'N/A').strip()
            eta = d.get('_eta_str', 'N/A').strip()

            total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate')
            size_str = cls.format_bytes(total_bytes) if total_bytes else ""
            size_info = f"| Size: {size_str}" if size_str else ""

            fragment_index = d.get('fragment_index')
            fragment_count = d.get('fragment_count')
            frag_info = f"| Frag: {fragment_index}/{fragment_count}" if fragment_index and fragment_count else ""

            playlist_index = d.get('playlist_index')
            playlist_count = d.get('n_entries')
            playlist_info = f"[Item {playlist_index}/{playlist_count}] " if playlist_index and playlist_count else ""

            status_line = f"\r{Colors.CYAN}[Downloading]{Colors.ENDC} {playlist_info}Progress: {percent} | Speed: {speed} | ETA: {eta} {size_info} {frag_info}"
            sys.stdout.write(status_line + "\033[K")
            sys.stdout.flush()

        elif status == 'finished':
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()
            filename = d.get('filename')
            base_name = os.path.basename(filename) if filename else "media file"
            print(f"{Colors.GREEN}[✔] Download completed:{Colors.ENDC} {base_name}. Finalizing media file...")

    # ------------------------------------------------------------------
    # Configuración Base de yt-dlp
    # ------------------------------------------------------------------
    def _apply_cookie_settings(self, ydl_opts: Dict[str, Any], config: DownloadConfig) -> None:
        if config.no_cookies:
            return
        if config.cookie_file and os.path.exists(config.cookie_file):
            ydl_opts['cookiefile'] = config.cookie_file
        elif os.path.exists("cookies.txt"):
            ydl_opts['cookiefile'] = "cookies.txt"
        elif config.cookies_browser:
            ydl_opts['cookiesfrombrowser'] = (config.cookies_browser, 'Default')

    def _build_base_options(self, target_folder: str, config: DownloadConfig) -> Dict[str, Any]:
        archive_path = None
        if not config.no_history:
            if config.audio_only:
                archive_name = f".download_archive_audio_{config.audio_format}.txt"
            elif config.custom_resolution:
                archive_name = f".download_archive_video_{config.custom_resolution}.txt"
            else:
                archive_name = ".download_archive_video_default.txt"
            archive_path = os.path.join(target_folder, archive_name)

        opts: Dict[str, Any] = {
            'ffmpeg_location': self.ffmpeg_location,
            'download_archive': archive_path,
            'nooverwrites': True,
            'noplaylist': not config.allow_playlist,
            'retries': DEFAULT_RETRIES,
            'fragment_retries': DEFAULT_RETRIES,
            'extractor_retries': DEFAULT_RETRIES,
            'concurrent_fragment_downloads': DEFAULT_CONCURRENT_FRAGMENTS,
            'sleep_interval': config.sleep_interval,
            'max_sleep_interval': config.sleep_interval + 4,
            'trim_file_name': DEFAULT_MAX_FILENAME_LENGTH,
            'windowsfilenames': True,
        }

        if config.sponsorblock:
            opts['sponsorblock_remove'] = ['sponsor', 'selfpromo', 'interaction', 'intro', 'outro']

        if config.split_chapters:
            opts['split_chapters'] = True

        if config.ratelimit:
            def parse_rate(rate_str: Any) -> Optional[int]:
                if isinstance(rate_str, (int, float)): return int(rate_str)
                rate_str = str(rate_str).upper().strip()
                units = {'K': 1024, 'M': 1024**2, 'G': 1024**3}
                for unit, mult in units.items():
                    if rate_str.endswith(unit):
                        try: return int(float(rate_str[:-1]) * mult)
                        except ValueError: pass
                try: return int(float(rate_str))
                except ValueError: return None

            limit_bytes = parse_rate(config.ratelimit)
            if limit_bytes:
                opts['ratelimit'] = limit_bytes

        if config.playlist_items:
            opts['playlist_items'] = config.playlist_items
            opts['noplaylist'] = False

        self._apply_cookie_settings(opts, config)

        if not config.verbose:
            opts.update({
                'quiet': True,
                'no_warnings': True,
                'noprogress': False,
            })

        return opts

    # ------------------------------------------------------------------
    # Procesamiento Post-Descarga
    # ------------------------------------------------------------------
    def _create_subtitled_copy(self, original_video: str, requested_subs: Dict[str, Any]) -> bool:
        available_subs = {lang: sub.get('filepath') for lang, sub in requested_subs.items() 
                          if sub.get('filepath') and os.path.exists(sub.get('filepath'))}
        
        if not available_subs:
            print(f"{Colors.WARNING}[⚠️ Warning]{Colors.ENDC} No valid subtitle files were retrieved.")
            return False

        grouped_subs: Dict[str, List[Tuple[str, str]]] = {}
        for lang, filepath in available_subs.items():
            base_lang = lang.split('-')[0].lower()
            grouped_subs.setdefault(base_lang, []).append((lang, filepath))

        selected_subs = []
        for variants in grouped_subs.values():
            variants.sort(key=lambda item: 1 if 'orig' in item[0].lower() else 2 if '-' in item[0].lower() else 3)
            selected_subs.append(variants[0])

        all_downloaded_paths = list(available_subs.values())
        downloaded_langs = sorted([sub[0] for sub in selected_subs], reverse=True)
        lang_label = ", ".join(downloaded_langs)

        base_path, ext = os.path.splitext(original_video)
        output_subtitled_file = f"{base_path} [sub {lang_label}]{ext}"

        print(f"{Colors.BLUE}[*]{Colors.ENDC} Creating subtitled copy with unique language tracks and cover art: {os.path.basename(output_subtitled_file)}")

        cmd = [self.ffmpeg_location, "-y", "-i", original_video]
        for _, sub_path in selected_subs:
            cmd.extend(["-i", sub_path])

        cmd.extend(["-c:v", "copy", "-c:a", "copy", "-c:s", "mov_text", "-map", "0:v", "-map", "0:a"])

        for idx, (lang_code, _) in enumerate(selected_subs):
            display_title = SUPPORTED_LANGUAGES.get(lang_code, lang_code)
            clean_iso = lang_code.split('-')[0]
            cmd.extend([
                "-map", f"{idx + 1}:s:0",
                f"-metadata:s:s:{idx}", f"language={clean_iso}",
                f"-metadata:s:s:{idx}", f"title={display_title}",
                f"-metadata:s:s:{idx}", f"handler_name={display_title}"
            ])

        cmd.append(output_subtitled_file)
        
        success = self._run_system_command(
            cmd, 
            success_message=f"Subtitled copy created with {len(selected_subs)} unique language tracks: {os.path.basename(output_subtitled_file)}", 
            error_context="FFmpeg subtitle embedding"
        )

        for sub_path in all_downloaded_paths:
            if os.path.exists(sub_path):
                try: os.remove(sub_path)
                except Exception: pass
        
        return success

    def _compress_video(self, video_path: str, crf: int = DEFAULT_COMPRESS_CRF) -> str:
        if not video_path or not os.path.exists(video_path):
            return video_path

        base_path, ext = os.path.splitext(video_path)
        compressed_file = f"{base_path}_compressed{ext}"

        print(f"{Colors.BLUE}[*]{Colors.ENDC} Compressing video with FFmpeg (CRF {crf})... This may take a few moments.")

        cmd = [
            self.ffmpeg_location, "-y", "-i", video_path,
            "-c:v", DEFAULT_VIDEO_ENCODER, "-crf", str(crf),
            "-preset", DEFAULT_ENCODE_PRESET,
            "-c:a", "aac", "-b:a", DEFAULT_AUDIO_BITRATE,
            compressed_file
        ]

        success = self._run_system_command(cmd, success_message="", error_context="FFmpeg compression")
        
        if success and os.path.exists(compressed_file) and os.path.getsize(compressed_file) > 0:
            orig_size = os.path.getsize(video_path)
            comp_size = os.path.getsize(compressed_file)
            os.remove(video_path)
            os.rename(compressed_file, video_path)
            savings = ((orig_size - comp_size) / orig_size) * 100
            print(f"{Colors.GREEN}[✔ Success]{Colors.ENDC} Video successfully compressed. Space savings: {savings:.1f}% ({self.format_bytes(orig_size)} -> {self.format_bytes(comp_size)})")
            return video_path
        else:
            if os.path.exists(compressed_file):
                os.remove(compressed_file)
            return video_path

    # ------------------------------------------------------------------
    # Helper Metodos de Descarga
    # ------------------------------------------------------------------
    def _get_target_directory(self, config: DownloadConfig) -> str:
        if config.organize:
            subfolder = "Audio" if config.audio_only else "Playlists" if (config.allow_playlist or config.playlist_items) else "Video"
            return os.path.join(self.output_folder, subfolder)
        return self.output_folder

    def _apply_time_range(self, ydl_opts: Dict[str, Any], time_range: str) -> None:
        def parse_sec(t: Optional[str]) -> Optional[float]:
            if not t: return None
            parts = list(map(float, t.strip().split(':')))
            return sum(p * 60**i for i, p in enumerate(reversed(parts)))

        start_str, end_str = time_range.split('-', 1) if '-' in time_range else (time_range, None)
        ydl_opts['download_ranges'] = download_range_func(None, [(parse_sec(start_str), parse_sec(end_str))])
        ydl_opts['force_keyframes_at_cuts'] = True

    def _process_subtitles(self, url: str, downloaded_file: str, target_dir: str, config: DownloadConfig) -> None:
        print(f"{Colors.BLUE}[*]{Colors.ENDC} Fetching preferred subtitles (Languages: {config.subtitles})...")
        ydl_opts_subs = self._build_base_options(target_dir, config)
        ydl_opts_subs['no_history'] = True 
        
        if config.sleep_interval > 0:
            if config.verbose:
                print(f"{Colors.BLUE}[*]{Colors.ENDC} Pausing {config.sleep_interval}s before requesting subtitles...")
            import time
            time.sleep(config.sleep_interval)

        base_no_ext = os.path.splitext(downloaded_file)[0]
        raw_langs = str(config.subtitles).lower().strip()
        
        if raw_langs == "all":
            target_langs = ['es', 'en', 'pt', 'es-ES', 'es-MX', 'en-US', 'pt-BR']
        else:
            user_requested = [l.strip() for l in raw_langs.replace(';', ',').split(',') if l.strip()]
            target_langs = []
            for lang in user_requested:
                if lang.startswith('es'): target_langs.extend(['es', 'es-ES', 'es-MX', 'es-419'])
                elif lang.startswith('en'): target_langs.extend(['en', 'en-US', 'en-GB'])
                elif lang.startswith('pt'): target_langs.extend(['pt', 'pt-PT', 'pt-BR'])
                else: target_langs.append(lang)
            if not target_langs: target_langs = ['es', 'es-ES', 'es-MX']

        ydl_opts_subs.update({
            'skip_download': True,
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': target_langs,
            'subtitlesformat': 'srt/vtt',
            'subtitlesignoreerrors': True,
            'outtmpl': f"{base_no_ext}.%(ext)s"
        })

        try:
            with YoutubeDL(ydl_opts_subs) as ydl_subs:
                sub_info = ydl_subs.extract_info(url, download=True)
                requested_subs = sub_info.get('requested_subtitles') if sub_info else None

            if requested_subs:
                copy_created = self._create_subtitled_copy(downloaded_file, requested_subs)
                if copy_created and config.clean_raw and os.path.exists(downloaded_file):
                    try:
                        os.remove(downloaded_file)
                        print(f"{Colors.MAGENTA}[🧹 Clean]{Colors.ENDC} Original video without subtitles removed: {os.path.basename(downloaded_file)}")
                    except Exception as e:
                        print(f"{Colors.FAIL}[!]{Colors.ENDC} Could not remove original file: {e}")
            else:
                print(f"{Colors.WARNING}[⚠️ Warning]{Colors.ENDC} No matching subtitles found on server.")
        except Exception as e:
            print(f"{Colors.WARNING}[⚠️ Warning]{Colors.ENDC} Could not retrieve subtitles: {str(e)}")

    # ------------------------------------------------------------------
    # Flujos Principales
    # ------------------------------------------------------------------
    def select_video_format(self, url: str, config: DownloadConfig) -> Tuple[Optional[str], Optional[str]]:
        if not config.verbose:
            print(f"{Colors.BLUE}[*]{Colors.ENDC} Fetching available formats...")

        target_dir = self._get_target_directory(config)
        ydl_opts = self._build_base_options(target_dir, config)

        try:
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                formats = info.get('formats', []) if info else []

                video_formats = []
                seen_resolutions = set()

                for f in formats:
                    height = f.get('height')
                    vcodec = f.get('vcodec', 'none')
                    if height and vcodec != 'none':
                        res = f"{height}p"
                        if res not in seen_resolutions:
                            seen_resolutions.add(res)
                            video_formats.append({
                                'format_id': f.get('format_id'),
                                'resolution': res,
                                'height': height,
                                'ext': f.get('ext', 'mp4'),
                                'note': f.get('format_note') or f.get('resolution') or ''
                            })

                video_formats.sort(key=lambda x: x['height'], reverse=True)

                if not video_formats:
                    return None, None

                if config.custom_resolution and config.custom_resolution != "interactive":
                    clean_requested = config.custom_resolution.lower().replace('p', '')
                    matched_fmt = next((fmt for fmt in video_formats if str(fmt['height']) == clean_requested or fmt['resolution'].lower() == config.custom_resolution.lower()), None)
                    if matched_fmt:
                        return f"bestvideo[height<={matched_fmt['height']}]+bestaudio/best", matched_fmt['resolution']
                    else:
                        print(f"\n{Colors.FAIL}[❌ Error]{Colors.ENDC} Resolution '{config.custom_resolution}' not available.")
                        sys.exit(1)

                elif config.custom_resolution == "interactive":
                    print("\n=== AVAILABLE QUALITY OPTIONS ===")
                    print(" 0. Best Quality (Default)")
                    for i, fmt in enumerate(video_formats, 1):
                        print(f" {i}. Resolution: {fmt['resolution']} ({fmt['ext']}) {fmt['note']}")
                    
                    choice = input("\nSelect option [0] or 'c' to exit: ").strip().lower()
                    if choice in ('c', 'cancel', 'exit'):
                        sys.exit(0)
                    if choice.isdigit() and 1 <= int(choice) <= len(video_formats):
                        selected = video_formats[int(choice) - 1]
                        return f"bestvideo[height<={selected['height']}]+bestaudio/best", selected['resolution']
        except SystemExit:
            sys.exit(0)
        except Exception as e:
            print(f"{Colors.FAIL}[!]{Colors.ENDC} Could not fetch formats: {e}")

        return None, None

    def download_media(self, url: str, config: DownloadConfig) -> None:
        self.current_url = url
        target_dir = self._get_target_directory(config)
        os.makedirs(target_dir, exist_ok=True)

        ydl_opts = self._build_base_options(target_dir, config)
        
        channel_folder = '%(uploader,channel,creator)s'
        filename_fmt = f'%(title)s [{config.custom_resolution}].%(ext)s' if config.custom_resolution else '%(title)s.%(ext)s'
        ydl_opts['outtmpl'] = os.path.join(target_dir, channel_folder, filename_fmt)

        if config.time_range:
            self._apply_time_range(ydl_opts, config.time_range)

        if not config.verbose:
            if config.no_cookies:
                print(f"{Colors.BLUE}[i]{Colors.ENDC} Cookie loading disabled.")
            elif not config.cookie_file and os.path.exists("cookies.txt"):
                print(f"{Colors.BLUE}[i]{Colors.ENDC} Auto-detected 'cookies.txt'.")
            ydl_opts['progress_hooks'] = [self.progress_hook]

        if config.audio_only:
            ydl_opts.update({
                'format': 'ba/best',
                'writethumbnail': True,
                'postprocessors': [
                    {'key': 'FFmpegExtractAudio', 'preferredcodec': config.audio_format, 
                     **({'preferredquality': '192'} if config.audio_format in ['mp3', 'm4a', 'aac'] else {})},
                    {'key': 'FFmpegThumbnailsConvertor', 'format': 'jpg'},
                    {'key': 'EmbedThumbnail'},
                    {'key': 'FFmpegMetadata', 'add_metadata': True}
                ],
                'postprocessor_args': {'ffmpegmetadata': ['-id3v2_version', '3'], 'embedthumbnail': ['-disposition:v', 'attached_pic']}
            })
        else:
            if config.custom_format: ydl_opts['format'] = config.custom_format
            ydl_opts['merge_output_format'] = self.merge_output_format
            ydl_opts.update({
                'writethumbnail': True,
                'postprocessors': [
                    {'key': 'FFmpegThumbnailsConvertor', 'format': 'jpg'},
                    {'key': 'EmbedThumbnail'},
                    {'key': 'FFmpegMetadata', 'add_metadata': True}
                ]
            })

        downloaded_file: Optional[str] = None
        try:
            with YoutubeDL(ydl_opts) as ydl:
                if not config.verbose:
                    # Restaurando el log dinámico detallado de la v1.0.2
                    action_type = f"AUDIO ({config.audio_format.upper()})" if config.audio_only else "VIDEO"
                    target_type = "PLAYLIST" if config.allow_playlist else "MEDIA"
                    range_msg = f" [Range: {config.time_range}]" if config.time_range else ""
                    rate_msg = f" [Rate Limit: {config.ratelimit}]" if config.ratelimit else ""
                    sb_msg = " [SponsorBlock]" if config.sponsorblock else ""
                    sc_msg = " [Split Chapters]" if config.split_chapters else ""

                    print(f"{Colors.BLUE}[*]{Colors.ENDC} Processing and downloading {target_type} {action_type}{range_msg}{rate_msg}{sb_msg}{sc_msg} to '{os.path.basename(target_dir)}/' from URL: {url}")

                    if config.time_range:
                        print(f"{Colors.YELLOW}[i]{Colors.ENDC} Note: yt-dlp suppresses progress bars during range trimming (-tr). Please wait while the segment is processed...")
                
                info_dict = ydl.extract_info(url, download=True)
                if info_dict:
                    req = info_dict.get('requested_downloads', [])
                    downloaded_file = req[0].get('_filename') if req else (info_dict.get('_filename') or ydl.prepare_filename(info_dict))

                if not config.audio_only and self.merge_output_format and downloaded_file:
                    possible_merged = f"{os.path.splitext(downloaded_file)[0]}.{self.merge_output_format}"
                    if os.path.exists(possible_merged): downloaded_file = possible_merged

        except KeyboardInterrupt:
            print(f"\n{Colors.FAIL}[!]{Colors.ENDC} Download cancelled.")
            sys.exit(0)
        except Exception as e:
            print(f"\n{Colors.FAIL}[❌ Error]{Colors.ENDC} Download failed: {str(e)}")
            self.log_failed_url(url, str(e))
            return

        if config.subtitles and not config.audio_only and downloaded_file and os.path.exists(downloaded_file):
            self._process_subtitles(url, downloaded_file, target_dir, config)

        print(f"{Colors.GREEN}[✔ Success]{Colors.ENDC} Process finished for URL: {url}\n")

        if config.compress and not config.audio_only and downloaded_file and os.path.exists(downloaded_file):
            downloaded_file = self._compress_video(downloaded_file, crf=DEFAULT_COMPRESS_CRF)

        if config.notify:
            file_name_display = os.path.basename(downloaded_file) if downloaded_file else "Media file"
            self._send_desktop_notification("Media Grabber", f"Download complete:\n{file_name_display}")

        self.clear_cache()

# ------------------------------------------------------------------
# Controladores CLI
# ------------------------------------------------------------------
def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Python Stream Media Grabber")
    
    parser.add_argument("url", nargs="?", default=None, help="Direct URL of the video/audio to download")
    parser.add_argument("-q", "--quality", nargs="?", const="interactive", default=None, help="Resolution format or interactive menu")
    parser.add_argument("-f", "--file", default=None, help="Path to a text file containing a list of URLs")
    parser.add_argument("-a", "--audio", nargs="?", const=DEFAULT_AUDIO_FORMAT, default=None, choices=["mp3", "m4a", "wav", "flac", "aac", "opus"], help="Download audio only")
    parser.add_argument("-s", "--subtitles", nargs="?", const="es", default=None, help="Download and embed subtitles. Defaults to 'es' if used alone, or specify languages like 'en', 'pt', 'es,en' or 'all'")
    parser.add_argument("--clean", action="store_true", help="Deletes the raw video after generating the subtitled copy (requires -s)")
    parser.add_argument("--compress", action="store_true", help="Compresses the resulting video with FFmpeg (libx264) to reduce file size")
    parser.add_argument("-sb", "--sponsorblock", action="store_true", help="Remove SponsorBlock segments (sponsors, selfpromo, interaction) automatically")
    parser.add_argument("-sc", "--split-chapters", action="store_true", help="Split video automatically into separate files based on chapters")
    parser.add_argument("-p", "--playlist", action="store_true", help="Allow downloading entire playlists")
    parser.add_argument("-pi", "--playlist-items", default=None, help="Playlist video items to download (e.g. 1-5, 1,3,7)")
    parser.add_argument("-tr", "--time-range", default=None, help="Time range for trimming (e.g. '20-30', '01:00-02:30', '01:00-' or '-02:30')")
    parser.add_argument("-r", "--ratelimit", nargs="?", const=DEFAULT_RATELIMIT, default=None, help=f"Maximum download rate (e.g. '-r' defaults to {DEFAULT_RATELIMIT}, or specify like '500k', '2m')")
    parser.add_argument("-o", "--organize", action="store_true", help="Automatically organize downloads into category subfolders (Video, Audio, Playlists)")
    parser.add_argument("-n", "--notify", action="store_true", help="Send a native desktop notification upon completion")
    parser.add_argument("-si", "--sleep-interval", type=int, default=DEFAULT_SLEEP_INTERVAL, help="Minimum seconds to sleep between downloads")
    parser.add_argument("-c", "--cookies", nargs="?", const="chrome", default=None, help="Extract cookies from browser (default: chrome)")
    parser.add_argument("-cf", "--cookie-file", default=None, help="Path to a cookies.txt file")
    parser.add_argument("-nc", "--no-cookies", action="store_true", help="Bypass automatic detection of cookies")
    parser.add_argument("-nh", "--no-history", action="store_true", help="Bypass recording download history in archive files")
    parser.add_argument("--no-cache", action="store_true", help="Bypass cache checking and session saving")
    parser.add_argument("-b", "--best", action="store_true", help="Automatic mode: activates subtitles (-s), cleanup (--clean), notify (-n), no-cache (--no-cache), rate-limit (-r), and sleep interval (-si)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show native yt-dlp log output")
    
    return parser.parse_args()

def apply_best_mode(args: argparse.Namespace) -> None:
    if args.best:
        args.subtitles = "es"
        args.clean = True
        args.notify = True
        args.no_cache = True
        args.ratelimit = args.ratelimit or DEFAULT_RATELIMIT
        args.sleep_interval = 5 if args.sleep_interval == DEFAULT_SLEEP_INTERVAL else args.sleep_interval

        print(f"{Colors.BLUE}[i]{Colors.ENDC} --best mode activated. Auto-applied settings:")
        print(f"    - Subtitles: {args.subtitles} | Cleanup: {args.clean} | Notify: {args.notify}")
        print(f"    - Rate Limit: {args.ratelimit}/s | Sleep: {args.sleep_interval}s")

def build_config(args: argparse.Namespace, custom_format: Optional[str] = None, custom_res: Optional[str] = None) -> DownloadConfig:
    return DownloadConfig(
        audio_only=args.audio is not None,
        audio_format=args.audio if args.audio else DEFAULT_AUDIO_FORMAT,
        cookies_browser=args.cookies,
        cookie_file=args.cookie_file,
        no_cookies=args.no_cookies,
        subtitles=args.subtitles,
        clean_raw=args.clean,
        compress=args.compress,
        sleep_interval=args.sleep_interval,
        verbose=args.verbose,
        no_history=args.no_history,
        time_range=args.time_range,
        organize=args.organize,
        notify=args.notify,
        ratelimit=args.ratelimit,
        sponsorblock=args.sponsorblock,
        split_chapters=args.split_chapters,
        allow_playlist=args.playlist or bool(args.playlist_items),
        playlist_items=args.playlist_items,
        custom_format=custom_format,
        custom_resolution=custom_res or args.quality
    )

def main() -> None:
    args = parse_arguments()
    apply_best_mode(args)

    if args.clean and not args.subtitles:
        print(f"{Colors.WARNING}[⚠️ Warning]{Colors.ENDC} --clean requires -s. Disabling --clean.")
        args.clean = False

    if args.time_range and args.subtitles:
        print(f"{Colors.WARNING}[⚠️ Warning]{Colors.ENDC} Subtitles unsupported with -tr. Disabling subtitles.")
        args.subtitles = None
        args.clean = False

    grabber = MediaGrabber()
    if args.file or args.no_cache:
        grabber.no_cache_enabled = True

    print(f"{Colors.HEADER}=== MEDIA GRABBER ==={Colors.ENDC}")

    urls_to_process: List[str] = []
    if args.file:
        if os.path.exists(args.file):
            with open(args.file, "r", encoding="utf-8") as f:
                urls_to_process = [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]
            print(f"{Colors.BLUE}[*]{Colors.ENDC} Loaded {len(urls_to_process)} URLs from {args.file}")
        else:
            print(f"{Colors.FAIL}[❌ Error]{Colors.ENDC} File '{args.file}' not found.")
            sys.exit(1)
    elif args.url:
        urls_to_process = [args.url]
    else:
        cached_url = grabber.load_cached_url()
        if cached_url:
            print(f"{Colors.WARNING}[?]{Colors.ENDC} Found interrupted download:\n    {cached_url}")
            if input("Resume this URL? (y/n): ").strip().lower() in ('', 'y', 'yes'):
                urls_to_process = [cached_url]
            grabber.clear_cache()
        if not urls_to_process:
            user_url = input("Enter URL: ").strip()
            if user_url: urls_to_process = [user_url]

    if not urls_to_process:
        print(f"{Colors.WARNING}[!]{Colors.ENDC} No valid URLs.")
        sys.exit(0)

    is_audio = args.audio is not None
    custom_fmt, custom_res = None, None

    if len(urls_to_process) == 1 and not is_audio and args.quality:
        temp_config = build_config(args)
        custom_fmt, custom_res = grabber.select_video_format(urls_to_process[0], temp_config)

    final_config = build_config(args, custom_format=custom_fmt, custom_res=custom_res)

    for idx, target_url in enumerate(urls_to_process, 1):
        if len(urls_to_process) > 1:
            print(f"\n{Colors.HEADER}--- Processing URL {idx}/{len(urls_to_process)} ---{Colors.ENDC}")
        grabber.download_media(target_url, final_config)


if __name__ == "__main__":
    main()
