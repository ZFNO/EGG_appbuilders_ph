import sys
import os
import yt_dlp
from PySide6.QtWidgets import QApplication, QInputDialog
from PySide6.QtCore import Qt

def get_base_path():
    """Get base path from YOUTUBE_DL env var or use CWD"""
    env_path = os.getenv('YOUTUBE_DL')
    if env_path and os.path.isdir(env_path):
        return env_path
    return os.getcwd()

def get_url_from_user():
    """Open PySide dialog to get URL from user"""
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    url, ok = QInputDialog.getText(
        None,
        "YouTube URL",
        "Enter YouTube video URL:",
        flags=Qt.WindowStaysOnTopHint
    )

    if ok and url:
        return url
    return None

def get_video_info(url):
    """Extract video info without downloading"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get('title', 'video'), info.get('id', 'unknown')
    except Exception as e:
        print(f"Error getting video info: {e}")
        return None, None

def download_youtube_content(url, download_type='both'):
    """Download YouTube content based on type"""

    base_path = get_base_path()
    video_dir = os.path.join(base_path, 'video')
    audio_dir = os.path.join(base_path, 'audio')

    # Get video title for consistent filenames
    video_title, video_id = get_video_info(url)
    if not video_title:
        video_title = f"video_{video_id}" if video_id else "video"

    # Clean filename for safe filesystem use
    safe_title = "".join(c for c in video_title if c.isalnum() or c in (' ', '-', '_')).rstrip()

    if download_type in ['both', 'video']:
        os.makedirs(video_dir, exist_ok=True)
    if download_type in ['both', 'audio']:
        os.makedirs(audio_dir, exist_ok=True)

    if download_type == 'video':
        # Video only
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': os.path.join(video_dir, f'{safe_title}.%(ext)s'),
            'merge_output_format': 'mp4',
            'quiet': False,
            'no_warnings': False,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        print(f"Video saved to: {video_dir}")

    elif download_type == 'audio':
        # Audio only
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(audio_dir, f'{safe_title}.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': False,
            'no_warnings': False,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        print(f"Audio saved to: {audio_dir}")

    else:
        # Both - download video with audio merged
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': os.path.join(video_dir, f'{safe_title}.%(ext)s'),
            'merge_output_format': 'mp4',
            'quiet': False,
            'no_warnings': False,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # Then extract audio from the same video
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(audio_dir, f'{safe_title}.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': False,
            'no_warnings': False,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        print(f"Video saved to: {video_dir}")
        print(f"Audio saved to: {audio_dir}")

def main():
    url = None
    download_type = 'both'

    if len(sys.argv) > 1:
        if sys.argv[1].startswith('--'):
            if sys.argv[1] == '--v':
                download_type = 'video'
            elif sys.argv[1] == '--a':
                download_type = 'audio'
        else:
            url = sys.argv[1]
            if len(sys.argv) > 2:
                if '--v' in sys.argv:
                    download_type = 'video'
                elif '--a' in sys.argv:
                    download_type = 'audio'

    if not url:
        url = get_url_from_user()

    if not url or ('youtube.com' not in url and 'youtu.be' not in url):
        print("Error: Invalid or no YouTube URL provided")
        return

    download_youtube_content(url, download_type)

if __name__ == "__main__":
    try:
        import yt_dlp
        from PySide6.QtWidgets import QApplication
    except ImportError as e:
        print(f"Error: Required module not found - {e}")
        print("Install required packages with: pip install yt-dlp PySide6")
        sys.exit(1)

    main()