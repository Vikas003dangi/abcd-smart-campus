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


def fetch_playlist_videos(playlist_id, max_results=50):
    if not playlist_id:
        raise ValueError("playlist_id is required.")
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
    Retrieves the channel's 'uploads' playlist directly via channels.list(part='contentDetails').
    This uses playlistItems.list (costs 1 quota unit) instead of search.list (costs 100 quota units),
    reducing YouTube API quota consumption by 99%.
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
