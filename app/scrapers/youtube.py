from datetime import datetime, timedelta, timezone
from typing import List, Optional
import os
import feedparser
from pydantic import BaseModel
from dotenv import load_dotenv
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound
from youtube_transcript_api.proxies import WebshareProxyConfig

# Load environment variables from .env file
load_dotenv()


class Transcript(BaseModel):
    text: str


class ChannelVideo(BaseModel):
    title: str
    url: str
    video_id: str
    published_at: datetime
    description: str
    transcript: Optional[str] = None


class YoutubeScraper:
    """
    Scraper for YouTube channel videos and transcripts.

    Purpose: Fetches video metadata from YouTube RSS feeds and retrieves transcripts
    for each video. Uses proxy configuration to avoid rate limiting when making
    multiple API requests.
    """

    def __init__(self):
        """
        Initialize the scraper with optional proxy configuration.

        Why needed: YouTube rate limits requests, so using a proxy service (like Webshare)
        allows us to rotate IP addresses and avoid getting blocked. The proxy config
        is optional - if not provided, requests will use the default IP.

        What it does: Reads PROXY_USERNAME and PROXY_PASSWORD from environment variables,
        creates a WebshareProxyConfig if both are present, and initializes the
        YouTubeTranscriptApi with the proxy configuration.
        """
        proxy_config = None
        proxy_username = os.getenv("PROXY_USERNAME")
        proxy_password = os.getenv("PROXY_PASSWORD")

        if proxy_username and proxy_password:
            proxy_config = WebshareProxyConfig(
                proxy_username=proxy_username, proxy_password=proxy_password
            )
            print("Proxy configuration loaded successfully")
        else:
            print(
                "No proxy configuration found. Set PROXY_USERNAME and PROXY_PASSWORD environment variables to use a proxy."
            )

        self.transcrip_api = YouTubeTranscriptApi(proxy_config=proxy_config)

    def _get_rss_url(self, channel_id: str) -> str:
        """
        Construct the RSS feed URL for a YouTube channel.

        Why needed: YouTube provides RSS feeds for channels which are free to access
        (no API key required) and contain video metadata. This is more reliable than
        scraping HTML or using the official API which has quotas.

        What it does: Takes a channel ID and returns the RSS feed URL that contains
        all videos from that channel.
        """
        return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

    def _extract_video_id(self, video_url: str) -> str:
        """
        Extract the video ID from various YouTube URL formats.

        Why needed: YouTube URLs come in multiple formats (watch, shorts, youtu.be),
        but the transcript API only needs the video ID. We need to normalize these
        different formats to extract just the ID.

        What it does: Parses different YouTube URL patterns:
        - youtube.com/watch?v=VIDEO_ID -> extracts VIDEO_ID
        - youtube.com/shorts/VIDEO_ID -> extracts VIDEO_ID
        - youtu.be/VIDEO_ID -> extracts VIDEO_ID

        Tricky bit: The split operations handle URL parameters and query strings.
        For example, "v=VIDEO_ID&t=123" splits on "v=", takes [1] (everything after),
        then splits on "&" and takes [0] (just the video ID before any parameters).
        """
        if "youtube.com/watch?v=" in video_url:
            return video_url.split("v=")[1].split("&")[0]

        if "youtube.com/shorts" in video_url:
            return video_url.split("shorts/")[1].split("?")[0]

        if "youtu.be/" in video_url:
            return video_url.split("youtu.be/")[1].split("?")[0]

        return video_url

    def get_transcript(self, video_id: str) -> Optional[Transcript]:
        """
        Fetch the transcript for a YouTube video.

        Why needed: Transcripts provide the actual spoken content of videos, which is
        essential for content analysis, summarization, or search. Not all videos have
        transcripts (they may be disabled or auto-generated captions may not exist).

        What it does: Uses the youtube-transcript-api to fetch transcript snippets,
        joins them into a single text string, and returns a Transcript object.
        Returns None if transcript is unavailable or if an error occurs.

        Tricky bit: The transcript API returns snippets (time-stamped text segments).
        We join them with spaces to create continuous text. We catch specific exceptions
        (TranscriptsDisabled, NoTranscriptFound) separately from general exceptions
        to handle different failure modes appropriately.
        """
        try:
            transcript = self.transcrip_api.fetch(video_id)
            text = " ".join([snippet.text for snippet in transcript.snippets])
            return Transcript(text=text)

        except (TranscriptsDisabled, NoTranscriptFound):
            return None
        except Exception:
            return None

    def get_latest_videos(self, channel_id: str, hours: int = 24) -> list[ChannelVideo]:
        """
        Fetch videos from a channel published within the specified time window.

        Why needed: Channels have many videos, but we typically only want recent ones.
        This method filters videos by publication date and excludes YouTube Shorts
        (which often don't have transcripts or aren't relevant for news aggregation).

        What it does: Parses the RSS feed, filters videos by publication time,
        skips Shorts, extracts video metadata, and returns a list of ChannelVideo objects.

        Tricky bit: entry.published_parsed is a 9-tuple (year, month, day, hour, minute,
        second, weekday, yearday, isdst). We unpack only the first 6 elements (*entry.published_parsed[:6])
        to create a datetime object. The timezone.utc ensures all times are in UTC for
        consistent comparison. We skip Shorts because they're typically <60 seconds and
        may not have transcripts.
        """
        feed = feedparser.parse(self._get_rss_url(channel_id))

        if not feed.entries:
            return []

        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)

        videos = []

        for entry in feed.entries:
            if "/shorts/" in entry.link:
                continue
            published_time = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

            if published_time >= cutoff_time:
                video_id = self._extract_video_id(entry.link)
                videos.append(
                    ChannelVideo(
                        title=entry.title,
                        url=entry.link,
                        video_id=video_id,
                        published_at=published_time,
                        description=entry.get("summary", ""),
                    )
                )

        return videos

    def scrape_channel(self, channel_id: str, hours: int = 150) -> list[ChannelVideo]:
        """
        Main method: Fetch videos and their transcripts from a channel.

        Why needed: This combines video metadata fetching with transcript retrieval.
        It's the primary entry point for scraping a channel - gets the videos first,
        then fetches transcripts for each one.

        What it does: Gets latest videos from the channel, then for each video,
        fetches its transcript and adds it to the ChannelVideo object. Returns
        complete video objects with transcripts included.

        Tricky bit: video.model_copy(update={...}) creates a new ChannelVideo instance
        with updated fields. This is needed because ChannelVideo is immutable (Pydantic model),
        so we can't modify the transcript field directly. The update dictionary allows
        us to set the transcript field while keeping all other fields unchanged.
        """
        videos = self.get_latest_videos(channel_id, hours)

        result = []

        for video in videos:
            transcript = self.get_transcript(video.video_id)
            result.append(
                video.model_copy(
                    update={"transcript": transcript.text if transcript else None}
                )
            )

        return result


if __name__ == "__main__":
    scraper = YoutubeScraper()
    transcript: Transcript = scraper.get_transcript("jqd6_bbjhS8")
    if transcript.text:
        print(transcript.text)
    else:
        print("Transcript not available for this video")
    channel_videos: List[ChannelVideo] = scraper.scrape_channel(
        "UCn8ujwUInbJkBhffxqAPBVQ", hours=200
    )
