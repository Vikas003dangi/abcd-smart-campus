# users/youtube_service.py

from django.conf import settings
from googleapiclient.discovery import build


def get_youtube_client():
    api_key = getattr(settings, "YOUTUBE_API_KEY", None)
    if not api_key or api_key == "YOUR_API_KEY_HERE":
        raise RuntimeError("YOUTUBE_API_KEY not configured correctly in .env")

    return build(
        "youtube",
        "v3",
        developerKey=api_key
    )


def fetch_playlists(channel_id):
    yt = get_youtube_client()
    response = yt.playlists().list(
        part="snippet",
        channelId=channel_id,
        maxResults=50
    ).execute()

    return response.get("items", [])


def fetch_playlist_videos(playlist_id, max_results=50):
    yt = get_youtube_client()
    response = yt.playlistItems().list(
        part="snippet",
        playlistId=playlist_id,
        maxResults=max_results
    ).execute()

    return response.get("items", [])


def fetch_channel_videos(channel_id, max_results=50):
    """
    Fetch all uploaded videos from a YouTube channel.
    Uses the 'search' endpoint to list videos by date.
    """
    yt = get_youtube_client()
    all_videos = []
    next_page = None

    while True:
        response = yt.search().list(
            part="snippet",
            channelId=channel_id,
            type="video",
            order="date",
            maxResults=min(max_results - len(all_videos), 50),
            pageToken=next_page
        ).execute()

        all_videos.extend(response.get("items", []))
        next_page = response.get("nextPageToken")

        if not next_page or len(all_videos) >= max_results:
            break

    return all_videos[:max_results]
