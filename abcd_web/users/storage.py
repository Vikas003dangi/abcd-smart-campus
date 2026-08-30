import os
from cloudinary_storage.storage import MediaCloudinaryStorage


class SmartMediaCloudinaryStorage(MediaCloudinaryStorage):
    """
    Universal Cloudinary Storage for Django:
    Automatically selects the correct Cloudinary resource_type based on file extension:
    - Images (.jpg, .png, .webp, .svg, .gif, .ico) -> 'image'
    - Videos & Audio (.mp4, .mov, .avi, .mkv, .webm, .mp3, .wav, .ogg, .m4a) -> 'video'
    - Documents & Archives (.pdf, .doc, .docx, .zip, .xlsx, .pptx, .txt, .csv) -> 'raw'
    """
    def _get_resource_type(self, name):
        ext = os.path.splitext(name or '')[1].lower()
        if ext in ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.mp3', '.wav', '.ogg', '.m4a']:
            return 'video'
        elif ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg', '.tiff', '.ico']:
            return 'image'
        else:
            return 'raw'
