# AudioLocal

AudioLocal 1.0.0 — Mac con Apple Silicon

Descarga enlaces individuales de YouTube y convierte el audio a MP3 en tu Mac.

REQUISITOS

• Mac con chip Apple M1, M2, M3, M4 o posterior.
• macOS Ventura 13.5 o posterior.
• Conexión a internet y espacio para el audio original y el MP3.
• La app ocupa aproximadamente 180 MB una vez descomprimida.

Esta versión incluye Python, Tcl/Tk, yt-dlp, Node y FFmpeg. No tienes que instalar
Python, Node, FFmpeg ni Homebrew. No se incluye una versión para Mac Intel o Windows.

INSTALAR Y ABRIR

1. Descomprime el ZIP.
2. Arrastra AudioLocal.app a Aplicaciones.
3. Abre AudioLocal.

La app tiene firma ad hoc y no está notarizada por Apple. macOS puede pedirte
autorizar su primera apertura en Ajustes del Sistema → Privacidad y seguridad.
Consulta la guía oficial: https://support.apple.com/es-cl/102445

USAR

1. Pega uno o varios enlaces de vídeos individuales de YouTube, uno por línea.
2. Elige 128, 192 o 320 kb/s y la carpeta de salida.
3. Pulsa Descargar MP3. Puedes cancelar; se conservan los archivos ya terminados.

La carpeta inicial es Descargas/AudioLocal. Puedes abrirla desde la app.
Las descargas se procesan una por una. Los archivos existentes no se sobrescriben.
La calidad final depende del audio del vídeo; 320 kb/s no añade detalles ausentes.

ALCANCE Y PRIVACIDAD

Esta versión descarga vídeos individuales; no descarga listas ni recorta frases.
No copia cookies del navegador, no inicia sesión en tu cuenta ni envía tus audios
a Guía Estudio. Se conecta a YouTube y a los servidores que entregan sus archivos.
Los archivos se guardan en la carpeta elegida y el temporal se limpia al terminar.
Algunos vídeos privados, restringidos o que exijan sesión pueden fallar.
YouTube puede cambiar su funcionamiento; las correcciones se entregarán en nuevas
versiones de AudioLocal. Usa contenidos que tengas autorización para descargar.

ACTUALIZACIONES, CÓDIGO Y LICENCIAS

https://github.com/franciscorrandom/AudioLocal/releases
https://github.com/franciscorrandom/AudioLocal

La carpeta Licencias conserva los avisos de los componentes incluidos.
La release contiene AudioLocal-1.0.0-Fuentes-dependencias.zip con las fuentes
correspondientes de FFmpeg 7.1, LAME 3.100, yt-dlp 2026.08.19 y Mutagen 1.47.0,
además del código propio y las instrucciones de compilación.

AudioLocal contiene código propio. La referencia original para el flujo de
descarga y conversión fue https://github.com/Szaturnusz/YTDownMp3;
no se incorpora código de ese repositorio.

VERIFICACIÓN

Se comprobó la app con PATH mínimo, sin depender del Python o Node del sistema:
inicio de la ventana, validación de enlaces vacíos, conversión a 128/192/320 kb/s,
cancelación normal y forzada, y descarga pública Creative Commons de Blender
(WebM/Opus → MP3 192 kb/s). Las 15 pruebas existentes también pasaron.
Se verificó la firma ad hoc. La prueba se realizó en un Mac Apple Silicon;
no representa una prueba independiente en todas las versiones de macOS compatibles.
