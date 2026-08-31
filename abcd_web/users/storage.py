import os
import cloudinary
from cloudinary_storage.storage import MediaCloudinaryStorage


class SmartMediaCloudinaryStorage(MediaCloudinaryStorage):
    """
    Universal Intelligent Cloudinary Storage for Django:
    Accurately classifies resource_type ('image', 'video', 'raw') using both:
    1. Explicit file extensions when available.
    2. Path/folder context heuristics for public_ids where Cloudinary stripped extensions.
    3. Safe default fallback to 'image' for all media assets so ImageField URLs never generate broken /raw/ links.
    """

    def _get_resource_type(self, name):
        name_str = str(name or '').lower().replace('\\', '/')
        ext = os.path.splitext(name_str)[1]

        # 1. Direct extension matching
        if ext in ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.mp3', '.wav', '.ogg', '.m4a']:
            return 'video'
        if ext in ['.pdf', '.doc', '.docx', '.zip', '.xlsx', '.xls', '.pptx', '.ppt', '.txt', '.csv', '.json', '.xml', '.apk']:
            return 'raw'
        if ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg', '.tiff', '.ico', '.heic', '.avif']:
            return 'image'

        # 2. Path/folder context heuristics (crucial for Cloudinary public_ids stored without extension)
        video_markers = ['video', 'recordings', 'broadcast_videos']
        if any(marker in name_str for marker in video_markers):
            return 'video'

        raw_markers = ['documents', 'notes', 'pdfs', 'broadcast_files', 'guidy_temp']
        if any(marker in name_str for marker in raw_markers):
            return 'raw'

        image_markers = [
            'student_photos', 'complaints', 'achievements', 'teacher_photos',
            'group_photos', 'course_thumbnails', 'material_thumbnails',
            'broadcast_banners', 'broadcast_attachments', 'avatars', 'photos', 'profiles'
        ]
        if any(marker in name_str for marker in image_markers):
            return 'image'

        # 3. Default fallback for standard media in Django is 'image' (MediaCloudinaryStorage default)
        return 'image'

    def url(self, name):
        if not name:
            return ''
        name_str = str(name)
        if name_str.startswith(('http://', 'https://', '//')):
            return name_str
        return super().url(name)
