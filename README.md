# Media Grabber

<p align="center">
  <b>Una herramienta CLI robusta, modular y altamente configurable para descargas multimedia en Python.</b>
</p>

<p align="center">
  <a href="#-características-principales">Características</a> •
  <a href="#-requisitos-previos">Requisitos</a> •
  <a href="#-instalación">Instalación</a> •
  <a href="#%EF%B8%8F-configuraci%C3%B3n-del-entorno">Configuración</a> •
  <a href="#-uso-y-opciones-de-la-línea-de-comandos">Uso</a>
</p>

---

**Media Grabber** es una potente herramienta de interfaz de línea de comandos (CLI) impulsada por `yt-dlp` y `FFmpeg`. Permite simplificar la descarga de videos (YouTube, Facebook, Instagram, etc.), listas de reproducción y transmisiones de audio, ofreciendo funciones avanzadas como subtítulos selectivos incrustados, eliminación automática de patrocinadores (SponsorBlock), división por capítulos, compresión de video y caché de sesión inteligente.

---

## 🚀 Características Principales

- **Descargas Flexibles**: Soporte para URLs individuales, listas de reproducción completas (`-p`) y procesamiento por lotes mediante archivos de texto (`-f`).
- **Subtítulos Avanzados**: Descarga y selección de idiomas preferidos (`es`, `en`, `pt`, `all`) con opción de limpieza automática de archivos sin subtítulos (`--clean`).
- **Integración con SponsorBlock (`-sb`)**: Elimina automáticamente segmentos de patrocinio, auto-promociones e interacciones en plataformas compatibles.
- **División por Capítulos (`-sc`)**: Divide automáticamente el contenido multimedia en archivos independientes según los capítulos del video.
- **Post-Procesamiento con FFmpeg**: Fusión de streams, incrustación de carátulas (miniaturas), extracción de audio (`mp3`, `m4a`, `wav`, `flac`, `aac`, `opus`) y compresión inteligente de video (`--compress`).
- **Gestión Inteligente de Sesión**: Guarda en caché las descargas interrumpidas para reanudarlas más tarde, registra historial y genera un archivo de auditoría `failed_urls.txt` para enlaces fallidos.
- **Control de Velocidad (`-r`)**: Limita el ancho de banda para evitar saturar la conexión o sufrir bloqueos del servidor.
- **Notificaciones de Escritorio**: Envía alertas nativas del sistema operativo al finalizar las tareas (`-n`).

---

## 🌐 Plataformas Soportadas

**Media Grabber** está respaldado por el motor de **yt-dlp**, lo que le otorga compatibilidad nativa con una enorme variedad de servicios de streaming y redes sociales. Las plataformas principales probadas y soportadas incluyen:

*   **YouTube**: Videos individuales, listas de reproducción completas (`-p`), selección de elementos específicos (`-pi`), división por capítulos (`-sc`) y extracción/incrustación de subtítulos (`-s`).
*   **Facebook**: Videos públicos y Reels.
*   **Instagram**: Reels, videos e historias públicas (compatible con autenticación mediante cookies `-c` o `-cf` para contenido restringido).
*   **Otras plataformas compatibles (vía yt-dlp)**:
    *   **TikTok** *(sujeto a restricciones y actualizaciones de seguridad de la plataforma)*.
    *   **Twitch** (videos y clips).
    *   **Vimeo** y **Dailymotion**.
    *   **X (Twitter)**.
    *   **SoundCloud** (ideal para descargas de audio masivas).
    *   *¡Y más de 1,000 sitios web soportados por el ecosistema de yt-dlp!*

---

## 📋 Requisitos Previos

Antes de ejecutar el script, asegúrate de tener instalado en tu sistema:
1. **Python 3.14.0 o superior**
2. **FFmpeg** (debe estar añadido al PATH del sistema o configurado en tu archivo `.env`).

---

## 📦 Instalación

1. Clona el repositorio o descarga el script:
   ```bash
   git clone https://github.com/Synist3rX/Media-Grabber.git
   cd Media-Grabber
   ```

2. Instala las dependencias de Python requeridas:
   ```bash
   pip install -r requirements.txt
   ```

## 🛠️ Instalación y Configuración de FFmpeg

Media Grabber requiere que **FFmpeg** esté instalado en tu sistema y accesible para procesar los flujos multimedia correctamente.

### 1. Instalación según tu Sistema Operativo

* **Windows:**
  * La forma más rápida es utilizando **WinGet** desde la terminal:
    ```bash
    winget install Gyan.FFmpeg
    ```
  * O bien, descárgalo manualmente desde el [sitio oficial de FFmpeg](https://ffmpeg.org/download.html), descomprímelo en una ruta fija (por ejemplo, `C:\ffmpeg\bin`) y añade dicha ruta a las Variables de Entorno del Sistema (`PATH`).
<br>

* **Linux (Ubuntu / Debian / Arch):**
  ```bash
  sudo apt update && sudo apt install ffmpeg
  
  # O en Arch Linux:
  sudo pacman -S ffmpeg
  ```

---

## ⚙️ Configuración del Entorno

Crea un archivo llamado `.env` en la raíz del proyecto para definir los comportamientos y rutas por defecto. Puedes utilizar la siguiente plantilla:

```env
# ==============================================================================
# CONFIGURACIÓN GENERAL DE RUTAS Y ALMACENAMIENTO
# ==============================================================================

# Carpeta principal donde se guardarán los archivos descargados y los historiales
OUTPUT_FOLDER=downloads

# Nombre del archivo temporal de caché para reanudar descargas interrumpidas
CACHE_FILE=.last_download

# ==============================================================================
# RUTA DE EJECUTABLE FFMPEG (Requerido para fusión de formatos y conversión de audio)
# ==============================================================================

# En Windows (ruta directa después de instalación: winget install Gyan.FFmpeg):
FFMPEG_LOCATION=C:\Users\username\AppData\Local\Microsoft\WinGet\Links\ffmpeg.exe

# En Linux / macOS (si está instalado globalmente en el sistema, puedes usar 'ffmpeg'):
# FFMPEG_LOCATION=ffmpeg

# ==============================================================================
# FORMATOS Y CONTENEDORES POR DEFECTO
# ==============================================================================

# Contenedor por defecto para videos descargados que requieren fusión (mp4, mkv, webm)
MERGE_OUTPUT_FORMAT=mp4

# Contenedor por defecto para audios descargados que requieren fusión (mp3, m4a, flac)
AUDIO_OUTPUT_FORMAT=mp3

# Codificador de video por defecto para compresión con FFmpeg
VIDEO_ENCODER=libx264

# Tasa de bits de audio por defecto para compresión o conversiones
AUDIO_BITRATE=128k

# Preset de codificación de FFmpeg (ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow)
ENCODE_PRESET=medium

# ==============================================================================
# INTERVALO DE ESPERA ENTRE DESCARGAS (en segundos)
# ==============================================================================

# Este valor define el tiempo de espera entre descargas para evitar sobrecargar el servidor.
SLEEP_INTERVAL_DEFAULT=3

# ==============================================================================
# PARÁMETROS AVANZADOS Y RENDIMIENTO
# ==============================================================================

# Límite de velocidad de descarga por defecto (ej. 10M, 500k)
DEFAULT_RATELIMIT=10M

# Nivel de compresión de video CRF para FFmpeg (valores recomendados entre 23 y 30)
COMPRESS_CRF=28

# Número de reintentos máximos para fragmentos y conexiones
DOWNLOAD_RETRIES=3

# Número de descargas de fragmentos concurrentes
CONCURRENT_FRAGMENTS=4

# Límite máximo de caracteres permitidos para los nombres de archivo
MAX_FILENAME_LENGTH=120

# Idiomas prioritarios por defecto para la descarga de subtítulos (separados por comas)
DEFAULT_SUBTITLE_LANGS=es,en,pt
```

---

## 💻 Uso y Opciones de la Línea de Comandos

Ejecuta el script utilizando Python seguido de la URL multimedia o tus banderas de configuración:

```bash
python grabber.py "URL_AQUÍ" [OPCIONES]
```

### Argumentos y Banderas Principales

| Bandera Corta | Bandera Larga | Descripción |
| :---: | :--- | :--- |
| *(Ninguna)* | `url` | URL directa del video o audio a descargar. |
| `-q` | `--quality` | Formato de resolución o menú interactivo. |
| `-f` | `--file` | Ruta a un archivo de texto con una lista de URLs para procesamiento por lotes. |
| `-a` | `--audio` | Descargar solo audio (soporta `mp3`, `m4a`, `wav`, `flac`, `aac`, `opus`). |
| `-s` | `--subtitles` | Descargar e incrustar subtítulos. Predeterminado a `es` o especifica idiomas como `en`, `pt`, `es,en`, `all`. |
| *(Ninguna)* | `--clean` | Elimina el video sin subtítulos tras generar la copia subtitulada (requiere `-s`). |
| *(Ninguna)* | `--compress` | Comprime el video resultante con FFmpeg (`libx264`) para reducir el tamaño del archivo. |
| `-sb` | `--sponsorblock` | Eliminar segmentos de SponsorBlock (patrocinios, autopro, interacciones) automáticamente. |
| `-sc` | `--split-chapters`| Dividir el video automáticamente en archivos independientes basados en los capítulos. |
| `-p` | `--playlist` | Permitir la descarga de listas de reproducción completas. |
| `-pi` | `--playlist-items`| Elementos específicos de la playlist a descargar (ej. `1-5`, `1,3,7`). |
| `-tr` | `--time-range` | Rango de tiempo para recortes (ej. `20-30`, `01:00-02:30`, `01:00-` o `-02:30`). |
| `-r` | `--ratelimit` | Tasa máxima de descarga (ej. valor por defecto `10M`, o especifica como `500k`, `2m`). |
| `-o` | `--organize` | Organizar automáticamente las descargas en subcarpetas de categorías (`Video`, `Audio`, `Playlists`). |
| `-n` | `--notify` | Enviar una notificación nativa de escritorio al completar la tarea. |
| `-si` | `--sleep-interval`| Segundos mínimos de pausa entre descargas. |
| `-c` | `--cookies` | Extraer cookies del navegador (por defecto: `chrome`). |
| `-cf` | `--cookie-file` | Ruta a un archivo de texto `cookies.txt`. |
| `-nc` | `--no-cookies` | Omitir la detección automática de cookies. |
| `-nh` | `--no-history` | Omitir el registro del historial de descargas en archivos de archivo (*archive*). |
| *(Ninguna)* | `--no-cache` | Omitir la verificación de caché y el guardado de sesión. |
| `-b` | `--best` | Modo automático: activa subtítulos (`-s`), limpieza (`--clean`), notificación (`-n`), sin caché (`--no-cache`), límite de tasa (`-r`), e intervalo de espera (`-si 5`). |
| `-v` | `--verbose` | Mostrar la salida de registros nativos de `yt-dlp`. |

### Ejemplos de Uso

* **Descargar la mejor calidad de video con subtítulos en español y eliminar el archivo crudo:**
  ```bash
  python grabber.py "https://www.youtube.com/watch?v=..." -s --clean
  ```

* **Descargar únicamente audio en formato FLAC con metadatos y carátula:**
  ```bash
  python grabber.py "https://www.youtube.com/watch?v=..." -a flac
  ```

* **Descarga masiva desde un archivo de texto aplicando SponsorBlock y división por capítulos:**
  ```bash
  python grabber.py -f urls.txt -sb -sc -o
  ```

* **Utilizar el modo automático preestablecido `--best`:**
  ```bash
  python grabber.py "https://www.youtube.com/watch?v=..." -b
  ```
