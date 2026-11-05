import os
import sys
import shutil
import atexit
import argparse
import subprocess
from yt_dlp import YoutubeDL
from yt_dlp.utils import download_range_func
from dotenv import load_dotenv

# Cargar variables de entorno desde el archivo .env
load_dotenv()

# =====================================================================
# Configuración Global y Constantes por Defecto (Cargadas desde .env)
# =====================================================================
DEFAULT_OUTPUT_FOLDER = os.getenv("OUTPUT_FOLDER", "downloads")
DEFAULT_CACHE_FILE = os.getenv("CACHE_FILE", ".last_download")
DEFAULT_FFMPEG_LOCATION = os.getenv("FFMPEG_LOCATION")
DEFAULT_MERGE_FORMAT = os.getenv("MERGE_OUTPUT_FORMAT", "mp4")
DEFAULT_AUDIO_FORMAT = os.getenv("AUDIO_OUTPUT_FORMAT", "mp3")
DEFAULT_VIDEO_ENCODER = os.getenv("VIDEO_ENCODER", "libx264")
DEFAULT_AUDIO_BITRATE = os.getenv("AUDIO_BITRATE", "128k")
DEFAULT_ENCODE_PRESET = os.getenv("ENCODE_PRESET", "medium")
DEFAULT_SLEEP_INTERVAL = int(os.getenv("SLEEP_INTERVAL_DEFAULT", 3))
DEFAULT_RATELIMIT = os.getenv("DEFAULT_RATELIMIT", "10M")
DEFAULT_COMPRESS_CRF = int(os.getenv("COMPRESS_CRF", 28))
DEFAULT_RETRIES = int(os.getenv("DOWNLOAD_RETRIES", 3))
DEFAULT_CONCURRENT_FRAGMENTS = int(os.getenv("CONCURRENT_FRAGMENTS", 4))
DEFAULT_MAX_FILENAME_LENGTH = int(os.getenv("MAX_FILENAME_LENGTH", 120))


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


class MediaGrabber:
    def __init__(self, output_folder=None, cache_filename=None, ffmpeg_location=None, merge_format=None):
        self.output_folder = output_folder or DEFAULT_OUTPUT_FOLDER
        cache_name = cache_filename or DEFAULT_CACHE_FILE
        self.cache_file = os.path.join(self.output_folder, cache_name)

        # Resolver ejecutable de FFmpeg
        env_ffmpeg = DEFAULT_FFMPEG_LOCATION
        if env_ffmpeg and os.path.exists(env_ffmpeg):
            self.ffmpeg_location = env_ffmpeg
        elif ffmpeg_location and os.path.exists(ffmpeg_location):
            self.ffmpeg_location = ffmpeg_location
        else:
            self.ffmpeg_location = shutil.which("ffmpeg") or "ffmpeg"

        self.merge_output_format = merge_format or DEFAULT_MERGE_FORMAT

        self.current_url = None
        self.no_cache_enabled = False

        atexit.register(self._save_cache_on_exit)

    # ------------------------------------------------------------------
    # Notificaciones del Sistema
    # ------------------------------------------------------------------
    @staticmethod
    def _send_desktop_notification(title, message):
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
                subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
    def _save_cache_on_exit(self):
        """Guarda la URL actual en caché solo si la descarga fue interrumpida."""
        if not self.no_cache_enabled and self.current_url:
            try:
                if not os.path.exists(self.output_folder):
                    os.makedirs(self.output_folder)
                with open(self.cache_file, "w", encoding="utf-8") as f:
                    f.write(self.current_url)
                print(f"\n{Colors.BLUE}[i]{Colors.ENDC} Cache saved for URL: {self.current_url}")
            except Exception:
                pass

    def load_cached_url(self):
        """Carga la URL previa guardada en el archivo de caché."""
        if not self.no_cache_enabled and os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    url = f.read().strip()
                    return url if url else None
            except Exception:
                return None
        return None

    def clear_cache(self):
        """Elimina el archivo de caché y resetea el estado actual."""
        self.current_url = None
        if os.path.exists(self.cache_file):
            try:
                os.remove(self.cache_file)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Auditoría de Errores (URLs Fallidas)
    # ------------------------------------------------------------------
    def log_failed_url(self, url, error_msg="Unknown error"):
        """Registra URLs fallidas en un archivo de texto independiente para revisión posterior."""
        try:
            if not os.path.exists(self.output_folder):
                os.makedirs(self.output_folder)
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
    def format_bytes(b):
        """Convierte bytes a un formato legible (KiB, MiB, GiB)."""
        if not b:
            return ""
        for unit in ['B', 'KiB', 'MiB', 'GiB', 'TiB']:
            if b < 1024.0:
                return f"{b:.2f} {unit}"
            b /= 1024.0
        return f"{b:.2f} PiB"

    @classmethod
    def progress_hook(cls, d):
        """Imprime el progreso de descarga en tiempo real con detalles de velocidad y ETA."""
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
    # Configuración de Cookies
    # ------------------------------------------------------------------
    def _apply_cookie_settings(self, ydl_opts, cookies_browser=None, cookie_file=None, no_cookies=False):
        """Aplica las cookies respetando la bandera --no-cookies y priorizando archivos planos."""
        if no_cookies:
            return

        if cookie_file and os.path.exists(cookie_file):
            ydl_opts['cookiefile'] = cookie_file
        elif os.path.exists("cookies.txt"):
            ydl_opts['cookiefile'] = "cookies.txt"
        elif cookies_browser:
            ydl_opts['cookiesfrombrowser'] = (cookies_browser, 'Default')

    # ------------------------------------------------------------------
    # Generador Base de Opciones
    # ------------------------------------------------------------------
    def _build_base_options(self, target_folder, cookies_browser=None, cookie_file=None, allow_playlist=False, playlist_items=None, no_cookies=False, custom_resolution=None, download_audio=False, audio_format=DEFAULT_AUDIO_FORMAT, sleep_interval=DEFAULT_SLEEP_INTERVAL, verbose=False, no_history=False, ratelimit=None, sponsorblock=False, split_chapters=False):
        """Genera el diccionario de opciones base para yt-dlp."""
        if no_history:
            archive_path = None
        else:
            if download_audio:
                archive_name = f".download_archive_audio_{audio_format}.txt"
            elif custom_resolution:
                archive_name = f".download_archive_video_{custom_resolution}.txt"
            else:
                archive_name = ".download_archive_video_default.txt"

            archive_path = os.path.join(target_folder, archive_name)

        opts = {
            'ffmpeg_location': self.ffmpeg_location,
            'download_archive': archive_path,
            'nooverwrites': True,
            'noplaylist': not allow_playlist,

            'retries': DEFAULT_RETRIES,
            'fragment_retries': DEFAULT_RETRIES,
            'extractor_retries': DEFAULT_RETRIES,
            'concurrent_fragment_downloads': DEFAULT_CONCURRENT_FRAGMENTS,

            'sleep_interval': sleep_interval,
            'max_sleep_interval': sleep_interval + 4,

            'trim_file_name': DEFAULT_MAX_FILENAME_LENGTH,
            'windowsfilenames': True,
        }

        if sponsorblock:
            opts['sponsorblock_remove'] = ['sponsor', 'selfpromo', 'interaction', 'intro', 'outro']

        if split_chapters:
            opts['split_chapters'] = True

        if ratelimit:
            def parse_rate(rate_str):
                if isinstance(rate_str, (int, float)):
                    return int(rate_str)
                rate_str = str(rate_str).upper().strip()
                units = {'K': 1024, 'M': 1024**2, 'G': 1024**3}
                for unit, mult in units.items():
                    if rate_str.endswith(unit):
                        try:
                            return int(float(rate_str[:-1]) * mult)
                        except ValueError:
                            pass
                try:
                    return int(float(rate_str))
                except ValueError:
                    return None

            limit_bytes = parse_rate(ratelimit)
            if limit_bytes:
                opts['ratelimit'] = limit_bytes

        if playlist_items:
            opts['playlist_items'] = playlist_items
            opts['noplaylist'] = False

        self._apply_cookie_settings(opts, cookies_browser, cookie_file, no_cookies)

        if not verbose:
            opts.update({
                'quiet': True,
                'no_warnings': True,
                'noprogress': True,
            })

        return opts

    # ------------------------------------------------------------------
    # Creación de Copia con Subtítulos Deduplicados por Idioma
    # ------------------------------------------------------------------
    def _create_subtitled_copy(self, original_video, requested_subs):
        """Genera una copia incrustando únicamente la mejor pista única por idioma y preservando la portada."""
        lang_names = {
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

        available_subs = {}
        for lang, sub_data in requested_subs.items():
            filepath = sub_data.get('filepath')
            if filepath and os.path.exists(filepath):
                available_subs[lang] = filepath

        if not available_subs:
            print(f"{Colors.WARNING}[⚠️ Warning]{Colors.ENDC} No valid subtitle files were retrieved.")
            return

        grouped_subs = {}
        for lang, filepath in available_subs.items():
            base_lang = lang.split('-')[0].lower()
            if base_lang not in grouped_subs:
                grouped_subs[base_lang] = []
            grouped_subs[base_lang].append((lang, filepath))

        selected_subs = []
        for base_lang, variants in grouped_subs.items():
            def get_priority(item):
                code = item[0].lower()
                if 'orig' in code:
                    return 1
                if '-' in code:
                    return 2
                return 3

            variants.sort(key=get_priority)
            selected_subs.append(variants[0])

        all_downloaded_paths = list(available_subs.values())

        downloaded_langs = [sub[0] for sub in selected_subs]
        downloaded_langs.sort(reverse=True)
        lang_label = ", ".join(downloaded_langs)

        base_path, ext = os.path.splitext(original_video)
        output_subtitled_file = f"{base_path} [sub {lang_label}]{ext}"

        print(f"{Colors.BLUE}[*]{Colors.ENDC} Creating subtitled copy with unique language tracks and cover art: {os.path.basename(output_subtitled_file)}")

        cmd = [self.ffmpeg_location, "-y", "-i", original_video]

        for _, sub_path in selected_subs:
            cmd.extend(["-i", sub_path])

        cmd.extend(["-c:v", "copy", "-c:a", "copy", "-c:s", "mov_text"])
        cmd.extend(["-map", "0:v", "-map", "0:a"])

        for idx, (lang_code, _) in enumerate(selected_subs):
            display_title = lang_names.get(lang_code, lang_code)
            clean_iso = lang_code.split('-')[0]

            cmd.extend(["-map", f"{idx + 1}:s:0"])
            cmd.extend([f"-metadata:s:s:{idx}", f"language={clean_iso}"])
            cmd.extend([f"-metadata:s:s:{idx}", f"title={display_title}"])
            cmd.extend([f"-metadata:s:s:{idx}", f"handler_name={display_title}"])

        cmd.append(output_subtitled_file)

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            if result.returncode == 0 and os.path.exists(output_subtitled_file) and os.path.getsize(output_subtitled_file) > 0:
                print(f"{Colors.GREEN}[✔ Success]{Colors.ENDC} Subtitled copy created with cover art & {len(selected_subs)} unique language tracks: {os.path.basename(output_subtitled_file)}")
                return True
            else:
                print(f"{Colors.FAIL}[!]{Colors.ENDC} FFmpeg subtitle embedding warning: {result.stderr}")
                return False
        except Exception as e:
            print(f"{Colors.FAIL}[!]{Colors.ENDC} Subtitle process error: {str(e)}")
            return False
        finally:
            for sub_path in all_downloaded_paths:
                if os.path.exists(sub_path):
                    try:
                        os.remove(sub_path)
                    except Exception:
                        pass

    # ------------------------------------------------------------------
    # Compresión de Video con FFmpeg
    # ------------------------------------------------------------------
    def _compress_video(self, video_path, crf=DEFAULT_COMPRESS_CRF):
        """Comprime el archivo de video utilizando FFmpeg para reducir su peso."""
        if not video_path or not os.path.exists(video_path):
            return video_path

        base_path, ext = os.path.splitext(video_path)
        compressed_file = f"{base_path}_compressed{ext}"

        print(f"{Colors.BLUE}[*]{Colors.ENDC} Compressing video with FFmpeg (CRF {crf})... This may take a few moments.")

        cmd = [
            self.ffmpeg_location, "-y",
            "-i", video_path,
            "-c:v", DEFAULT_VIDEO_ENCODER,
            "-crf", str(crf),
            "-preset", DEFAULT_ENCODE_PRESET,
            "-c:a", "aac",
            "-b:a", DEFAULT_AUDIO_BITRATE,
            compressed_file
        ]

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace"
            )

            if result.returncode == 0 and os.path.exists(compressed_file) and os.path.getsize(compressed_file) > 0:
                orig_size = os.path.getsize(video_path)
                comp_size = os.path.getsize(compressed_file)

                os.remove(video_path)
                os.rename(compressed_file, video_path)

                savings = ((orig_size - comp_size) / orig_size) * 100
                print(f"{Colors.GREEN}[✔ Success]{Colors.ENDC} Video successfully compressed. Space savings: {savings:.1f}% ({self.format_bytes(orig_size)} -> {self.format_bytes(comp_size)})")
                return video_path
            else:
                print(f"{Colors.FAIL}[!]{Colors.ENDC} FFmpeg compression warning: {result.stderr}")
                if os.path.exists(compressed_file):
                    os.remove(compressed_file)
                return video_path
        except Exception as e:
            print(f"{Colors.FAIL}[!]{Colors.ENDC} Compression process error: {str(e)}")
            return video_path

    # ------------------------------------------------------------------
    # Selección de Calidad Tolerante a Errores
    # ------------------------------------------------------------------
    def select_video_format(self, url, requested_res=None, cookies_browser=None, cookie_file=None, no_cookies=False, sleep_interval=DEFAULT_SLEEP_INTERVAL, verbose=False, no_history=False, organize=False, ratelimit=None, sponsorblock=False, split_chapters=False):
        """Obtiene las resoluciones disponibles e incluye una opción limpia de cancelación."""
        if not verbose:
            print(f"{Colors.BLUE}[*]{Colors.ENDC} Fetching available formats...")

        target_base_dir = os.path.join(self.output_folder, "Video") if organize else self.output_folder

        ydl_opts = self._build_base_options(
            target_folder=target_base_dir,
            cookies_browser=cookies_browser,
            cookie_file=cookie_file,
            allow_playlist=False,
            no_cookies=no_cookies,
            sleep_interval=sleep_interval,
            verbose=verbose,
            no_history=no_history,
            ratelimit=ratelimit,
            sponsorblock=sponsorblock,
            split_chapters=split_chapters
        )

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

                available_res_list = [fmt['resolution'] for fmt in video_formats]

                if requested_res and requested_res != "interactive":
                    clean_requested = requested_res.lower().replace('p', '')
                    matched_fmt = next(
                        (fmt for fmt in video_formats if str(fmt['height']) == clean_requested or fmt['resolution'].lower() == requested_res.lower()),
                        None
                    )

                    if matched_fmt:
                        format_str = f"bestvideo[height<={matched_fmt['height']}]+bestaudio/best"
                        return format_str, matched_fmt['resolution']
                    else:
                        print(f"\n{Colors.FAIL}[❌ Error]{Colors.ENDC} Resolution '{requested_res}' is not available for this video.")
                        print(f"{Colors.BLUE}[i]{Colors.ENDC} Available resolutions: {', '.join(available_res_list)}")
                        sys.exit(1)

                elif requested_res == "interactive":
                    print("\n=== AVAILABLE QUALITY OPTIONS ===")
                    print(" 0. Best Quality (Default)")
                    for i, fmt in enumerate(video_formats, 1):
                        print(f" {i}. Resolution: {fmt['resolution']} ({fmt['ext']}) {fmt['note']}")
                    print(" c. Cancel and Exit")

                    try:
                        choice = input("\nSelect quality option number [0] or 'c' to exit: ").strip().lower()
                    except KeyboardInterrupt:
                        print(f"\n\n{Colors.FAIL}[!]{Colors.ENDC} Operation cancelled by user. Exiting...")
                        self.clear_cache()
                        sys.exit(0)

                    if choice in ('c', 'cancel', 'exit'):
                        print(f"\n{Colors.FAIL}[!]{Colors.ENDC} Operation cancelled by user. Exiting...")
                        self.clear_cache()
                        sys.exit(0)

                    if choice.isdigit() and 1 <= int(choice) <= len(video_formats):
                        selected = video_formats[int(choice) - 1]
                        format_str = f"bestvideo[height<={selected['height']}]+bestaudio/best"
                        return format_str, selected['resolution']

        except SystemExit:
            sys.exit(0)
        except Exception as e:
            print(f"{Colors.FAIL}[!]{Colors.ENDC} Could not fetch formats automatically: {e}")

        return None, None

    # ------------------------------------------------------------------
    # Descarga Unificada Principal
    # ------------------------------------------------------------------
    def download_media(self, url, download_audio=False, audio_format=DEFAULT_AUDIO_FORMAT, cookies_browser=None, cookie_file=None, custom_format=None, custom_resolution=None, allow_playlist=False, playlist_items=None, no_cookies=False, subtitles=None, clean=False, compress=False, sleep_interval=DEFAULT_SLEEP_INTERVAL, verbose=False, no_history=False, time_range=None, organize=False, notify=False, ratelimit=None, sponsorblock=False, split_chapters=False):
        """Descarga limpia del medio unificando flujos e incrustando miniatura como carátula de video/audio."""
        self.current_url = url

        if organize:
            if download_audio:
                subfolder = "Audio"
            elif allow_playlist or playlist_items:
                subfolder = "Playlists"
            else:
                subfolder = "Video"
            target_base_dir = os.path.join(self.output_folder, subfolder)
        else:
            target_base_dir = self.output_folder

        if not os.path.exists(target_base_dir):
            os.makedirs(target_base_dir)

        channel_folder = '%(uploader,channel,creator)s'
        filename_fmt = f'%(title)s [{custom_resolution}].%(ext)s' if custom_resolution else '%(title)s.%(ext)s'
        outtmpl = os.path.join(target_base_dir, channel_folder, filename_fmt)

        ydl_opts = self._build_base_options(
            target_folder=target_base_dir,
            cookies_browser=cookies_browser,
            cookie_file=cookie_file,
            allow_playlist=allow_playlist,
            playlist_items=playlist_items,
            no_cookies=no_cookies,
            custom_resolution=custom_resolution,
            download_audio=download_audio,
            audio_format=audio_format,
            sleep_interval=sleep_interval,
            verbose=verbose,
            no_history=no_history,
            ratelimit=ratelimit,
            sponsorblock=sponsorblock,
            split_chapters=split_chapters
        )
        ydl_opts['outtmpl'] = outtmpl

        if time_range:
            def parse_sec(t):
                if not t:
                    return None
                parts = list(map(float, t.strip().split(':')))
                return sum(p * 60**i for i, p in enumerate(reversed(parts)))

            if '-' in time_range:
                start_str, end_str = time_range.split('-', 1)
            else:
                start_str, end_str = time_range, None

            start_sec = parse_sec(start_str)
            end_sec = parse_sec(end_str)

            ydl_opts['download_ranges'] = download_range_func(None, [(start_sec, end_sec)])
            ydl_opts['force_keyframes_at_cuts'] = True

        if not verbose:
            if no_cookies:
                print(f"{Colors.BLUE}[i]{Colors.ENDC} Cookie loading is disabled (--no-cookies).")
            elif not cookie_file and os.path.exists("cookies.txt"):
                print(f"{Colors.BLUE}[i]{Colors.ENDC} Auto-detected 'cookies.txt' in current directory.")

            ydl_opts['progress_hooks'] = [self.progress_hook]

        if download_audio:
            postprocessor_config = {
                'key': 'FFmpegExtractAudio',
                'preferredcodec': audio_format,
            }
            if audio_format in ['mp3', 'm4a', 'aac']:
                postprocessor_config['preferredquality'] = '192'

            ydl_opts.update({
                'format': 'ba/best',
                'writethumbnail': True,
                'postprocessors': [
                    postprocessor_config,
                    {
                        'key': 'FFmpegThumbnailsConvertor',
                        'format': 'jpg',
                    },
                    {
                        'key': 'EmbedThumbnail',
                    },
                    {
                        'key': 'FFmpegMetadata',
                        'add_metadata': True
                    }
                ],
                'postprocessor_args': {
                    'ffmpegmetadata': ['-id3v2_version', '3'],
                    'embedthumbnail': ['-disposition:v', 'attached_pic']
                }
            })
        else:
            if custom_format:
                ydl_opts['format'] = custom_format
            ydl_opts['merge_output_format'] = self.merge_output_format

            ydl_opts['writethumbnail'] = True
            ydl_opts['postprocessors'] = [
                {
                    'key': 'FFmpegThumbnailsConvertor',
                    'format': 'jpg',
                },
                {
                    'key': 'EmbedThumbnail',
                },
                {
                    'key': 'FFmpegMetadata',
                    'add_metadata': True
                }
            ]

        downloaded_file = None

        try:
            with YoutubeDL(ydl_opts) as ydl:
                if not verbose:
                    action_type = f"AUDIO ({audio_format.upper()})" if download_audio else "VIDEO"
                    target_type = "PLAYLIST" if allow_playlist else "MEDIA"
                    range_msg = f" [Range: {time_range}]" if time_range else ""
                    rate_msg = f" [Rate Limit: {ratelimit}]" if ratelimit else ""
                    sb_msg = " [SponsorBlock]" if sponsorblock else ""
                    sc_msg = " [Split Chapters]" if split_chapters else ""

                    print(f"{Colors.BLUE}[*]{Colors.ENDC} Processing and downloading {target_type} {action_type}{range_msg}{rate_msg}{sb_msg}{sc_msg} to '{os.path.basename(target_base_dir)}/' from URL: {url}")

                    if time_range:
                        print(f"{Colors.YELLOW}[i]{Colors.ENDC} Note: yt-dlp suppresses progress bars during range trimming (-tr). Please wait while the segment is processed...")

                info_dict = ydl.extract_info(url, download=True)

                if info_dict:
                    req_downloads = info_dict.get('requested_downloads')
                    if isinstance(req_downloads, list) and len(req_downloads) > 0:
                        downloaded_file = req_downloads[0].get('_filename')

                    if not downloaded_file:
                        downloaded_file = info_dict.get('_filename') or ydl.prepare_filename(info_dict)

                if not download_audio and self.merge_output_format and downloaded_file:
                    base_path, _ = os.path.splitext(downloaded_file)
                    possible_merged = f"{base_path}.{self.merge_output_format}"
                    if os.path.exists(possible_merged):
                        downloaded_file = possible_merged

        except KeyboardInterrupt:
            print(f"\n\n{Colors.FAIL}[!]{Colors.ENDC} Download cancelled by user.")
            sys.exit(0)
        except Exception as e:
            error_text = str(e)
            print(f"\n{Colors.FAIL}[❌ Error]{Colors.ENDC} An error occurred while downloading media: {error_text}")
            self.log_failed_url(url, error_text)
            return

        if subtitles is not None and not download_audio and downloaded_file and os.path.exists(downloaded_file):
            print(f"{Colors.BLUE}[*]{Colors.ENDC} Fetching preferred subtitles (Languages: {subtitles})...")

            ydl_opts_subs = self._build_base_options(
                target_folder=target_base_dir,
                cookies_browser=cookies_browser,
                cookie_file=cookie_file,
                allow_playlist=False,
                no_cookies=no_cookies,
                sleep_interval=sleep_interval,
                verbose=verbose,
                no_history=True,
                ratelimit=ratelimit,
                sponsorblock=sponsorblock,
                split_chapters=split_chapters
            )

            if sleep_interval > 0:
                if verbose:
                    print(f"{Colors.BLUE}[*]{Colors.ENDC} Pausing {sleep_interval}s before requesting subtitles...")
                import time
                time.sleep(sleep_interval)

            base_no_ext = os.path.splitext(downloaded_file)[0]

            raw_langs = str(subtitles).lower().strip()
            if raw_langs == "all":
                target_langs = ['es', 'en', 'pt', 'es-ES', 'es-MX', 'en-US', 'pt-BR']
            else:
                user_requested = [l.strip() for l in raw_langs.replace(';', ',').split(',') if l.strip()]
                target_langs = []
                for lang in user_requested:
                    if lang.startswith('es'):
                        target_langs.extend(['es', 'es-ES', 'es-MX', 'es-419'])
                    elif lang.startswith('en'):
                        target_langs.extend(['en', 'en-US', 'en-GB'])
                    elif lang.startswith('pt'):
                        target_langs.extend(['pt', 'pt-PT', 'pt-BR'])
                    else:
                        target_langs.append(lang)
                if not target_langs:
                    target_langs = ['es', 'es-ES', 'es-MX']

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

                    if copy_created and clean and downloaded_file and os.path.exists(downloaded_file):
                        try:
                            os.remove(downloaded_file)
                            print(f"{Colors.MAGENTA}[🧹 Clean]{Colors.ENDC} Original video without subtitles removed: {os.path.basename(downloaded_file)}")
                        except Exception as cleanup_err:
                            print(f"{Colors.FAIL}[!]{Colors.ENDC} Could not remove original file: {cleanup_err}")
                else:
                    print(f"{Colors.WARNING}[⚠️ Warning]{Colors.ENDC} No matching subtitles found on server.")

            except Exception as sub_err:
                print(f"{Colors.WARNING}[⚠️ Warning]{Colors.ENDC} Could not retrieve subtitles: {str(sub_err)}")
                print(f"{Colors.BLUE}[i]{Colors.ENDC} Keeping base video intact.")

        print(f"{Colors.GREEN}[✔ Success]{Colors.ENDC} Process finished for URL: {url}\n")

        if compress and not download_audio:
            target_to_compress = None
            if subtitles is not None and 'output_subtitled_file' in locals() and os.path.exists(output_subtitled_file):
                target_to_compress = output_subtitled_file
            elif downloaded_file and os.path.exists(downloaded_file):
                target_to_compress = downloaded_file

            if target_to_compress:
                compressed_result = self._compress_video(target_to_compress, crf=DEFAULT_COMPRESS_CRF)
                if compressed_result and subtitles is not None:
                    output_subtitled_file = compressed_result
                elif compressed_result:
                    downloaded_file = compressed_result

        if notify:
            file_name_display = os.path.basename(downloaded_file) if downloaded_file else "Media file"
            self._send_desktop_notification(
                title="Media Grabber",
                message=f"Download complete:\n{file_name_display}"
            )

        self.clear_cache()


# ------------------------------------------------------------------
# Punto de Entrada CLI
# ------------------------------------------------------------------
if __name__ == "__main__":
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
    parser.add_argument("-b", "--best", action="store_true", help="Automatic mode: activates subtitles (-s), cleanup (--clean), notify (-n), no-cache (--no-cache), rate-limit (-r), and sleep interval (-si 5)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show native yt-dlp log output")
    args = parser.parse_args()

    if args.best:
        args.subtitles = "es"
        args.clean = True
        args.notify = True
        args.no_cache = True

        if not args.ratelimit:
            args.ratelimit = DEFAULT_RATELIMIT

        if not args.sleep_interval or args.sleep_interval == DEFAULT_SLEEP_INTERVAL:
            args.sleep_interval = 5

        print(f"{Colors.BLUE}[i]{Colors.ENDC} --best mode activated. Values applied automatically:")
        print(f"    - Subtitles: {args.subtitles}")
        print(f"    - Cleanup: {args.clean}")
        print(f"    - Notify: {args.notify}")
        print(f"    - No Cache: {args.no_cache}")
        print(f"    - Rate Limit: {args.ratelimit}/s")
        print(f"    - Sleep Interval: {args.sleep_interval}s")

    if args.clean and args.subtitles is None:
        print(f"{Colors.WARNING}[⚠️ Warning]{Colors.ENDC} The --clean option requires enabling subtitles (-s). Disabling --clean.")
        args.clean = False

    if args.time_range and args.subtitles is not None:
        print(f"{Colors.WARNING}[⚠️ Warning]{Colors.ENDC} Subtitle embedding (-s) is not supported alongside time range trimming (-tr). Disabling subtitles for this job.")
        args.subtitles = None
        args.clean = False

    grabber = MediaGrabber()

    if args.file or args.no_cache:
        grabber.no_cache_enabled = True

    print(f"{Colors.HEADER}=== MEDIA GRABBER ==={Colors.ENDC}")

    urls_to_process = []

    if args.file:
        if os.path.exists(args.file):
            try:
                with open(args.file, "r", encoding="utf-8") as f:
                    urls_to_process = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
                print(f"{Colors.BLUE}[*]{Colors.ENDC} Loaded {len(urls_to_process)} URLs from file: {args.file}")
            except Exception as e:
                print(f"{Colors.FAIL}[❌ Error]{Colors.ENDC} Could not read the URL file: {str(e)}")
                sys.exit(1)
        else:
            print(f"{Colors.FAIL}[❌ Error]{Colors.ENDC} The file '{args.file}' does not exist.")
            sys.exit(1)

    elif args.url:
        urls_to_process = [args.url]

    else:
        user_url = None
        if not grabber.no_cache_enabled:
            cached_url = grabber.load_cached_url()
            if cached_url:
                print(f"{Colors.WARNING}[?]{Colors.ENDC} Found a previous interrupted download URL:\n    {cached_url}")
                choice = input("Do you want to resume/download this previous URL? (y/n): ").strip().lower()
                grabber.clear_cache()
                if choice in ('', 'y', 'yes'):
                    user_url = cached_url

        if not user_url:
            user_url = input("Enter the URL of the video/audio you want to download: ").strip()

        if user_url:
            urls_to_process = [user_url]

    if urls_to_process:
        total = len(urls_to_process)
        chosen_format = None
        chosen_resolution = None

        is_audio = args.audio is not None
        audio_format = args.audio if is_audio else DEFAULT_AUDIO_FORMAT

        if total == 1 and not is_audio and args.quality is not None:
            try:
                chosen_format, chosen_resolution = grabber.select_video_format(
                    urls_to_process[0],
                    requested_res=args.quality,
                    cookies_browser=args.cookies,
                    cookie_file=args.cookie_file or ("cookies.txt" if os.path.exists("cookies.txt") else None),
                    no_cookies=args.no_cookies,
                    sleep_interval=args.sleep_interval,
                    verbose=args.verbose,
                    no_history=args.no_history,
                    organize=args.organize,
                    ratelimit=args.ratelimit,
                    sponsorblock=args.sponsorblock,
                    split_chapters=args.split_chapters
                )
            except KeyboardInterrupt:
                print(f"\n\n{Colors.FAIL}[!]{Colors.ENDC} Operation cancelled by user. Exiting...")
                grabber.clear_cache()
                sys.exit(0)

        for index, target_url in enumerate(urls_to_process, 1):
            if total > 1:
                print(f"\n{Colors.HEADER}--- Processing URL {index}/{total} ---{Colors.ENDC}")
            grabber.download_media(
                target_url,
                download_audio=is_audio,
                audio_format=audio_format,
                cookies_browser=args.cookies,
                cookie_file=args.cookie_file,
                custom_format=chosen_format,
                custom_resolution=chosen_resolution,
                allow_playlist=args.playlist or bool(args.playlist_items),
                playlist_items=args.playlist_items,
                no_cookies=args.no_cookies,
                subtitles=args.subtitles,
                clean=args.clean,
                compress=args.compress,
                sleep_interval=args.sleep_interval,
                verbose=args.verbose,
                no_history=args.no_history,
                time_range=args.time_range,
                organize=args.organize,
                notify=args.notify,
                ratelimit=args.ratelimit,
                sponsorblock=args.sponsorblock,
                split_chapters=args.split_chapters
            )
    else:
        print(f"{Colors.WARNING}[!]{Colors.ENDC} No valid URLs to process.")
