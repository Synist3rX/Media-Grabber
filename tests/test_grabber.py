import os
import unittest
from unittest.mock import patch, MagicMock, mock_open

# Importamos las clases de tu script (asumiendo que se llama grabber.py)
# Si tu archivo se llama grabber_v1.1.0.py, cambia "grabber" por "grabber_v1_1_0"
from grabber import MediaGrabber, DownloadConfig, DEFAULT_AUDIO_FORMAT

class TestDownloadConfig(unittest.TestCase):
    def test_default_config(self):
        """Verifica que el DTO se inicialice con los valores seguros por defecto."""
        config = DownloadConfig()
        self.assertFalse(config.audio_only)
        self.assertEqual(config.audio_format, DEFAULT_AUDIO_FORMAT)
        self.assertFalse(config.sponsorblock)
        self.assertFalse(config.notify)
        self.assertIsNone(config.time_range)

class TestMediaGrabber(unittest.TestCase):
    def setUp(self):
        """Se ejecuta antes de cada prueba. Instancia un grabber limpio."""
        self.test_folder = "test_downloads_temp"
        self.grabber = MediaGrabber(output_folder=self.test_folder, cache_filename="test_cache.txt")

    def tearDown(self):
        """Limpieza después de cada prueba."""
        self.grabber.clear_cache()
        if os.path.exists(self.test_folder):
            try:
                import shutil
                shutil.rmtree(self.test_folder)
            except Exception:
                pass

    def test_format_bytes(self):
        """Verifica el formateo matemático estático de los bytes."""
        self.assertEqual(MediaGrabber.format_bytes(0), "")
        self.assertEqual(MediaGrabber.format_bytes(500), "500.00 B")
        self.assertEqual(MediaGrabber.format_bytes(1048576), "1.00 MiB")
        self.assertEqual(MediaGrabber.format_bytes(1073741824), "1.00 GiB")

    def test_get_target_directory_organized(self):
        """Verifica la lógica de subcarpetas cuando config.organize es True."""
        config = DownloadConfig(organize=True)
        
        # Prueba Audio
        config.audio_only = True
        self.assertTrue(self.grabber._get_target_directory(config).endswith("Audio"))
        
        # Prueba Playlists
        config.audio_only = False
        config.allow_playlist = True
        self.assertTrue(self.grabber._get_target_directory(config).endswith("Playlists"))
        
        # Prueba Video normal
        config.allow_playlist = False
        self.assertTrue(self.grabber._get_target_directory(config).endswith("Video"))

    def test_build_base_options_sponsorblock(self):
        """Verifica que SponsorBlock se inyecte correctamente en yt-dlp."""
        config = DownloadConfig(sponsorblock=True)
        opts = self.grabber._build_base_options(self.test_folder, config)
        
        self.assertIn('sponsorblock_remove', opts)
        self.assertEqual(opts['sponsorblock_remove'], ['sponsor', 'selfpromo', 'interaction', 'intro', 'outro'])

    def test_build_base_options_ratelimit(self):
        """Verifica que el límite de tasa (Rate Limit) se parsee matemáticamente a bytes."""
        config = DownloadConfig(ratelimit="2M") # 2 Megabytes
        opts = self.grabber._build_base_options(self.test_folder, config)
        
        self.assertIn('ratelimit', opts)
        self.assertEqual(opts['ratelimit'], 2 * 1024 * 1024)

    @patch('grabber.YoutubeDL')
    def test_select_video_format_automatic(self, mock_ytdl_class):
        """Simula una petición a yt-dlp para elegir la mejor resolución sin descargar nada."""
        # Preparamos la respuesta falsa del servidor
        mock_ydl_instance = MagicMock()
        mock_ydl_instance.extract_info.return_value = {
            'formats': [
                {'height': 1080, 'vcodec': 'avc1', 'ext': 'mp4', 'format_id': '137'},
                {'height': 720, 'vcodec': 'avc1', 'ext': 'mp4', 'format_id': '22'},
                {'height': 480, 'vcodec': 'avc1', 'ext': 'mp4', 'format_id': '135'}
            ]
        }
        mock_ytdl_class.return_value.__enter__.return_value = mock_ydl_instance

        config = DownloadConfig(custom_resolution="720p", verbose=True)
        
        format_str, res = self.grabber.select_video_format("https://fake-url.com", config)
        
        self.assertEqual(res, "720p")
        self.assertIn("720", format_str)

    @patch('grabber.MediaGrabber._run_system_command')
    @patch('os.path.exists', return_value=True)
    @patch('os.path.getsize', return_value=2048)  # Simulamos un tamaño de archivo válido
    @patch('os.remove')
    @patch('os.rename')
    def test_compress_video_calls_ffmpeg(self, mock_rename, mock_remove, mock_getsize, mock_exists, mock_run_cmd):
        """Asegura que el método de compresión arme el comando FFmpeg correctamente usando el DRY runner."""
        mock_run_cmd.return_value = True
        
        # Ejecutamos con un archivo simulado
        self.grabber._compress_video("dummy_video.mp4", crf=30)
        
        # Verificamos que el comando enviado a la consola contenía libx264 y el CRF esperado
        mock_run_cmd.assert_called_once()
        args, _ = mock_run_cmd.call_args
        cmd_list = args[0]
        
        self.assertIn("-c:v", cmd_list)
        self.assertIn("libx264", cmd_list)
        self.assertIn("-crf", cmd_list)
        self.assertIn("30", cmd_list)


if __name__ == '__main__':
    # python -m unittest -v
    unittest.main(verbosity=2)
