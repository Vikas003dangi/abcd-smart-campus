import os
import cloudinary
from cloudinary_storage.storage import MediaCloudinaryStorage
from django.core.files.uploadedfile import UploadedFile


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

        # 1. Direct extension matching (always takes priority)
        if ext in ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.mp3', '.wav', '.ogg', '.m4a']:
            return 'video'
        if ext in ['.pdf', '.doc', '.docx', '.zip', '.xlsx', '.xls', '.pptx', '.ppt', '.txt', '.csv', '.json', '.xml', '.apk']:
            return 'raw'
        if ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg', '.tiff', '.ico', '.heic', '.avif']:
            return 'image'

        # 2. Path/folder context heuristics (for Cloudinary public_ids stored without extension)
        video_markers = ['video', 'recordings', 'broadcast_videos', 'audio', 'voice']
        if any(marker in name_str for marker in video_markers):
            return 'video'

        raw_markers = ['documents', 'notes', 'pdfs', 'broadcast_files']
        if any(marker in name_str for marker in raw_markers):
            return 'raw'

        image_markers = [
            'student_photos', 'complaints', 'achievements', 'teacher_photos',
            'group_photos', 'course_thumbnails', 'material_thumbnails',
            'broadcast_banners', 'broadcast_attachments', 'avatars', 'photos', 'profiles',
            'guidy_temp'
        ]
        if any(marker in name_str for marker in image_markers):
            return 'image'

        # 3. Default fallback for standard media in Django is 'image' (MediaCloudinaryStorage default)
        return 'image'

    def _save(self, name, content):
        name = self._normalise_name(name)
        name = self._prepend_prefix(name)
        content = UploadedFile(content, name)
        response = self._upload(name, content)
        public_id = response['public_id']
        rtype = response.get('resource_type')
        fmt = response.get('format')
        # If Cloudinary stripped the extension for video/audio, preserve format
        # so direct extension matching will always work permanently.
        if rtype == 'video' and fmt and not os.path.splitext(public_id)[1]:
            public_id = f"{public_id}.{fmt}"
        return public_id

    def delete(self, name):
        if not name:
            return True
        try:
            name_str = str(name)
            rtype = self._get_resource_type(name_str)
            clean_name = name_str
            if rtype in ['image', 'video']:
                # Cloudinary destroy expects public_id without extension for images and videos
                clean_name = os.path.splitext(name_str)[0]
            response = cloudinary.uploader.destroy(clean_name, invalidate=True, resource_type=rtype)
            return response.get('result') in ['ok', 'not found']
        except Exception:
            return False

    def _get_url(self, name):
        name = self._prepend_prefix(name)
        rtype = self._get_resource_type(name)
        cloudinary_resource = cloudinary.CloudinaryResource(name, default_resource_type=rtype)
        # Automatic format & quality optimization for images:
        # f_auto: delivers WebP / AVIF based on browser support
        # q_auto: smart compression saving 60-80% of Cloudinary free credit bandwidth
        if rtype == 'image':
            return cloudinary_resource.build_url(fetch_format='auto', quality='auto')
        return cloudinary_resource.url

    def url(self, name):
        if not name:
            return ''
        name_str = str(name)
        if name_str.startswith(('http://', 'https://', '//')):
            return name_str
        return self._get_url(name)


