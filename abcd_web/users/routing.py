from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/guidy/chat/(?P<chat_type>direct|guidance|group)/(?P<session_id>\d+)/$', consumers.GuidyChatConsumer.as_asgi()),
    re_path(r'ws/guidy/notifications/$', consumers.NotificationConsumer.as_asgi()),
]
