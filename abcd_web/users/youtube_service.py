# users/youtube_service.py

from django.conf import settings
from googleapiclient.discovery import build


def get_youtube_client():
    api_key = getattr(settings, "YOUTUBE_API_KEY", "")
    if not api_key:
        raise RuntimeError("YOUTUBE_API_KEY is not configured in .env or environment variables.")
    return build(
        "youtube",
        "v3",
        developerKey=api_key
    )


def fetch_playlists(channel_id):
    if not channel_id:
        raise ValueError("YOUTUBE_CHANNEL_ID is missing or not configured.")
    yt = get_youtube_client()
    response = yt.playlists().list(
        part="snippet",
        channelId=channel_id,
        maxResults=50
    ).execute()

    return response.get("items", [])


def fetch_playlist_videos(playlist_id, max_results=None):
    """Fetch all videos from a playlist using pagination."""
    if not playlist_id:
        raise ValueError("playlist_id is required.")
    yt = get_youtube_client()
    all_items = []
    next_page = None

    while True:
        response = yt.playlistItems().list(
            part="snippet",
            playlistId=playlist_id,
            maxResults=50,
            pageToken=next_page
        ).execute()

        all_items.extend(response.get("items", []))
        next_page = response.get("nextPageToken")

        if not next_page:
            break
        if max_results and len(all_items) >= max_results:
            break

    return all_items[:max_results] if max_results else all_items


def fetch_channel_videos(channel_id, max_results=None):
    """
    Fetch all uploaded videos from a YouTube channel.
    Uses the channel's 'uploads' playlist with full pagination.
    """
    if not channel_id:
        raise ValueError("YOUTUBE_CHANNEL_ID is missing or not configured.")
    yt = get_youtube_client()

    try:
        ch_response = yt.channels().list(
            part="contentDetails",
            id=channel_id
        ).execute()
        items = ch_response.get("items", [])
        if items:
            uploads_playlist_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
            return fetch_playlist_videos(uploads_playlist_id, max_results=max_results)
    except Exception:
        pass

    # Fallback to search (expensive quota)
    all_videos = []
    next_page = None
    limit = max_results or 500

    while True:
        response = yt.search().list(
            part="snippet",
            channelId=channel_id,
            type="video",
            order="date",
            maxResults=min(limit - len(all_videos), 50),
            pageToken=next_page
        ).execute()

        all_videos.extend(response.get("items", []))
        next_page = response.get("nextPageToken")

        if not next_page or len(all_videos) >= limit:
            break

    return all_videos[:limit]

