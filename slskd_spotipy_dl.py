#! /usr/bin/env uv run
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "slskd-api",
#     "spotipy",
# ]
# ///
"""
Spotify Liked Songs to Slskd Downloader
Downloads liked songs from Spotify using slskd with quality profile matching
"""

import os
import time
import re
from typing import List, Dict, Optional
from dataclasses import dataclass
from enum import Enum
from dotenv import load_dotenv

import spotipy
from spotipy.oauth2 import SpotifyOAuth
import slskd_api

load_dotenv()


class QualityProfile(Enum):
    """Quality profiles similar to Lidarr"""

    LOSSLESS = {
        "name": "Lossless",
        "formats": ["flac", "ape", "alac", "wav"],
        "min_bitrate": 900,
        "preferred_bitrate": 1411,
        "score_weight": 1.0,
    }
    HIGH = {
        "name": "High Quality",
        "formats": ["mp3", "flac", "ogg", "m4a"],
        "min_bitrate": 256,
        "preferred_bitrate": 320,
        "score_weight": 0.8,
    }
    STANDARD = {
        "name": "Standard",
        "formats": ["mp3", "ogg", "m4a", "wma"],
        "min_bitrate": 192,
        "preferred_bitrate": 256,
        "score_weight": 0.6,
    }
    ANY = {
        "name": "Any",
        "formats": ["mp3", "flac", "ogg", "m4a", "ape", "alac", "wav", "wma"],
        "min_bitrate": 128,
        "preferred_bitrate": 320,
        "score_weight": 0.4,
    }


@dataclass
class Track:
    """Spotify track information"""

    name: str
    artist: str
    album: str
    spotify_id: str
    duration_ms: int


class QualityMatcher:
    """Matches search results to quality profiles"""

    def __init__(self, profile: QualityProfile):
        self.profile = profile.value

    def extract_metadata(self, filename: str) -> Dict:
        """Extract format and bitrate from filename"""
        filename_lower = filename.lower()

        # Extract file extension
        ext_match = re.search(r"\.(flac|mp3|ape|alac|wav|ogg|m4a|wma)$", filename_lower)
        file_format = ext_match.group(1) if ext_match else None

        # Extract bitrate
        bitrate_match = re.search(r"(\d{3,4})\s*k?bps?", filename_lower)
        if not bitrate_match:
            bitrate_match = re.search(r"(\d{3,4})k", filename_lower)

        bitrate = int(bitrate_match.group(1)) if bitrate_match else None

        # Check for lossless indicators
        is_lossless = any(
            word in filename_lower
            for word in ["flac", "lossless", "ape", "alac", "wav"]
        )
        if is_lossless and not bitrate:
            bitrate = 1411  # Assume CD quality for lossless

        return {"format": file_format, "bitrate": bitrate, "is_lossless": is_lossless}

    def score_file(self, file_data: Dict, track: Track) -> float:
        """Score a file based on quality profile and metadata match"""
        filename = file_data.get("filename", "").lower()
        file_size = file_data.get("size", 0)

        metadata = self.extract_metadata(filename)
        score = 0.0

        # Format score
        if metadata["format"] in self.profile["formats"]:
            score += 30
            # Bonus for preferred formats
            if metadata["format"] in ["flac", "mp3"][:2]:
                score += 10
        else:
            return 0.0  # Invalid format

        # Bitrate score
        if metadata["bitrate"]:
            if metadata["bitrate"] >= self.profile["min_bitrate"]:
                score += 25
                # Closer to preferred bitrate = higher score
                bitrate_diff = abs(
                    metadata["bitrate"] - self.profile["preferred_bitrate"]
                )
                score += max(0, 15 - (bitrate_diff / 50))
            else:
                return 0.0  # Below minimum bitrate

        # Metadata matching
        track_name_clean = re.sub(r"[^\w\s]", "", track.name.lower())
        artist_clean = re.sub(r"[^\w\s]", "", track.artist.lower())
        album_clean = re.sub(r"[^\w\s]", "", track.album.lower())

        if track_name_clean in filename:
            score += 15
        if artist_clean in filename:
            score += 10
        if album_clean in filename:
            score += 5

        # File size reasonableness check (avoid broken files)
        expected_size = (
            (track.duration_ms / 1000) * (metadata["bitrate"] or 320) * 1000 / 8
        )
        if file_size > expected_size * 0.5 and file_size < expected_size * 2:
            score += 5

        return score * self.profile["score_weight"]

    def find_best_match(self, search_results: Dict, track: Track) -> Optional[Dict]:
        """Find the best matching file from search results"""
        best_score = 0
        best_match = None

        # search_results is the response from slskd API
        responses = search_results

        for response in responses:
            username = response.get("username")
            files = response.get("files", [])

            for file_data in files:
                score = self.score_file(file_data, track)

                if score > best_score:
                    best_score = score
                    best_match = {
                        "username": username,
                        "file": file_data,
                        "score": score,
                    }

        # Only return if score is reasonable
        if best_match and best_match["score"] >= 40:
            return best_match

        return None


class SpotifySlskdDownloader:
    """Main application class"""

    def __init__(
        self,
        spotify_config: Dict,
        slskd_host: str,
        slskd_api_key: str,
        quality_profile: QualityProfile,
        slskd_url_base: str = "/",
    ):
        self.sp = spotipy.Spotify(auth_manager=SpotifyOAuth(**spotify_config))
        self.slskd = slskd_api.SlskdClient(slskd_host, slskd_api_key, slskd_url_base)
        self.matcher = QualityMatcher(quality_profile)
        self.quality_profile = quality_profile

    def get_liked_tracks(self, limit: int = 10) -> List[Track]:
        """Retrieve user's liked tracks from Spotify"""
        results = self.sp.current_user_saved_tracks(limit=limit)
        tracks = []

        for item in results["items"]:
            track_data = item["track"]
            track = Track(
                name=track_data["name"],
                artist=", ".join([artist["name"] for artist in track_data["artists"]]),
                album=track_data["album"]["name"],
                spotify_id=track_data["id"],
                duration_ms=track_data["duration_ms"],
            )
            tracks.append(track)

        return tracks

    def create_search_query(self, track: Track) -> str:
        """Create optimized search query"""
        return f"{track.artist} {track.name}"

    def wait_for_search_results(self, search_id: int, timeout: int = 15) -> Dict:
        """Wait for search to complete and return results"""
        start_time = time.time()

        while time.time() - start_time < timeout:
            print("Checking search status...")
            try:
                # Check if search is complete or has enough results
                if self.slskd.searches.state(search_id, False).get("isComplete"):
                    return self.slskd.searches.search_responses(search_id)

                time.sleep(1)
            except Exception as e:
                print(f"Error checking search status: {e}")
                time.sleep(1)

        # Return whatever we have after timeout
        try:
            return self.slskd.searches.search_responses(search_id)
        except Exception as e:
            print("Error fetching final search results:", e)
            return {"responses": []}

    def download_track(self, track: Track) -> bool:
        """Search and download a track"""
        print(f"\n{'=' * 60}")
        print(f"Processing: {track.artist} - {track.name}")
        print(f"Album: {track.album}")
        print(f"Quality Profile: {self.quality_profile.value['name']}")
        print(f"{'=' * 60}")

        query = self.create_search_query(track)
        print(f"Searching for: {query}")

        try:
            # Check if the search is already in the queue
            existing_searches = self.slskd.searches.get_all()
            search = None
            for curr_search in existing_searches:
                if curr_search.get("searchText", "").lower() == query.lower():
                    search = curr_search
                    print("Found existing search in queue")
                    break
            if search is None:
                # Initiate search
                search_response = self.slskd.searches.search_text(query)
                search = search_response

            if not search:
                print("❌ Failed to initiate search")
                return False

            # Wait for results
            print("Waiting for search results...")
            search_results = self.wait_for_search_results(search.get("id"))

            responses = search_results

            if not responses:
                print("❌ No results found")
                return False

            print(f"Found {len(responses)} users with results")

            best_match = self.matcher.find_best_match(search_results, track)

            if not best_match:
                print("❌ No suitable match found for quality profile")
                return False
            print(best_match)

            file_data = best_match["file"]
            username = best_match["username"]
            filename = file_data["filename"]

            print(f"\n✓ Best match (score: {best_match['score']:.1f}):")
            print(f"  User: {username}")
            print(f"  File: {filename}")
            print(f"  Size: {file_data['size'] / 1024 / 1024:.2f} MB")

            metadata = self.matcher.extract_metadata(filename)
            print(f"  Format: {metadata['format']}")
            print(
                f"  Bitrate: {metadata['bitrate']} kbps"
                if metadata["bitrate"]
                else "  Bitrate: Unknown"
            )

            print("\nInitiating download...")

            # Use the slskd API to download
            print(f"Enqueuing download from user '{username}' for file '{filename}'")
            self.slskd.transfers.enqueue(username=username, files=[file_data])

            print("✓ Download enqueued successfully")
            return True

        except Exception as e:
            print(f"❌ Error during download: {e}")
            return False

    def run(self, track_limit: int = 10):
        """Main execution flow"""
        print(f"\n{'#' * 60}")
        print("Spotify to Slskd Downloader")
        print(f"{'#' * 60}\n")

        try:
            # Test connection
            app_state = self.slskd.application.state()
            print(
                f"✓ Connected to slskd (version: {app_state.get('version', 'unknown')})"
            )
        except Exception as e:
            print(f"❌ Failed to connect to slskd: {e}")
            return

        print("\nFetching liked tracks from Spotify...")
        tracks = self.get_liked_tracks(limit=track_limit)

        print(f"\nFound {len(tracks)} tracks to download\n")

        successful = 0
        failed = 0

        for i, track in enumerate(tracks, 1):
            print(f"\n[{i}/{len(tracks)}]")

            if self.download_track(track):
                successful += 1
            else:
                failed += 1

            # Rate limiting between searches
            if i < len(tracks):
                time.sleep(2)

        print(f"\n{'=' * 60}")
        print("SUMMARY")
        print(f"{'=' * 60}")
        print(f"Total tracks: {len(tracks)}")
        print(f"Successful downloads: {successful}")
        print(f"Failed: {failed}")
        print(f"{'=' * 60}\n")


def main():
    """Example configuration and usage"""

    # Read Spotify credentials from a secure location or environment variables
    SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
    SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

    # Spotify API Configuration
    # Get credentials from https://developer.spotify.com/dashboard
    spotify_config = {
        "client_id": SPOTIFY_CLIENT_ID or "YOUR_SPOTIFY_CLIENT_ID",
        "client_secret": SPOTIFY_CLIENT_SECRET or "YOUR_SPOTIFY_CLIENT_SECRET",
        "redirect_uri": "http://localhost:8888/callback",
        "scope": "user-library-read",
    }

    # Slskd Configuration
    # Get API key from slskd settings
    SLSKD_HOST = "http://localhost:5030"  # Your slskd host
    SLSKD_API_KEY = os.getenv("SLSKD_API_KEY") or "YOUR_SLSKD_API_KEY"
    SLSKD_URL_BASE = "/"  # Usually just '/', adjust if needed

    # Choose quality profile
    quality_profile = QualityProfile.LOSSLESS
    # Options: QualityProfile.LOSSLESS, QualityProfile.HIGH,
    #          QualityProfile.STANDARD, QualityProfile.ANY

    # Initialize and run
    downloader = SpotifySlskdDownloader(
        spotify_config=spotify_config,
        slskd_host=SLSKD_HOST,
        slskd_api_key=SLSKD_API_KEY,
        quality_profile=quality_profile,
        slskd_url_base=SLSKD_URL_BASE,
    )

    downloader.run(track_limit=10)


if __name__ == "__main__":
    main()
