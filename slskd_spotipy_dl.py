#! /usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "slskd-api",
#     "spotipy",
#     "mutagen",
#     "python-dotenv",
# ]
# ///

"""
Spotify Liked Songs to Slskd Downloader
Downloads liked songs from Spotify using slskd with quality profile matching
Uses mutagen for direct tagging and Lidarr-like organization
"""

import os
import re
import shutil
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import slskd_api
import spotipy
from dotenv import load_dotenv
from mutagen import File as MutagenFile
from mutagen.flac import FLAC
from mutagen.id3 import ID3, TALB, TCON, TDRC, TIT2, TPE1, TPE2, TRCK
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.oggvorbis import OggVorbis
from spotipy.oauth2 import SpotifyOAuth

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
    album_artist: Optional[str] = None
    track_number: Optional[int] = None
    year: Optional[int] = None
    genre: Optional[str] = None


class MutagenTagger:
    """Handles audio file tagging using Mutagen directly"""

    def __init__(self, music_root: str):
        self.music_root = Path(music_root).expanduser()
        self.downloads_dir = self.music_root / "slskd_downloads"
        self.incomplete_dir = self.music_root / "incomplete"

        # Create directories if they don't exist
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self.incomplete_dir.mkdir(parents=True, exist_ok=True)

    def tag_file(self, file_path: Path, track: Track) -> bool:
        """Tag audio file with track metadata using Mutagen"""
        try:
            print(f"    Tagging {file_path.suffix.upper()} file with metadata...")

            audio = MutagenFile(file_path)
            if audio is None:
                print(f"    ⚠️  Could not load file for tagging: {file_path}")
                return False

            # Common tag mappings for different formats
            if isinstance(audio, FLAC) or file_path.suffix.lower() == ".flac":
                self._tag_flac(audio, track)
            elif isinstance(audio, (MP3, ID3)) or file_path.suffix.lower() == ".mp3":
                self._tag_mp3(audio, track)
            elif isinstance(audio, MP4) or file_path.suffix.lower() in [".m4a", ".mp4"]:
                self._tag_mp4(audio, track)
            elif isinstance(audio, OggVorbis) or file_path.suffix.lower() == ".ogg":
                self._tag_ogg(audio, track)
            else:
                # Generic tagging for other formats
                self._tag_generic(audio, track)

            audio.save()
            print("    ✓ File tagged successfully")
            return True

        except Exception as e:
            print(f"    ❌ Error tagging file: {e}")
            return False

    def _tag_flac(self, audio: FLAC, track: Track):
        """Tag FLAC files (Vorbis comments)"""
        audio.clear()
        audio["title"] = [track.name]
        audio["artist"] = [track.artist]
        audio["album"] = [track.album]

        if track.album_artist:
            audio["albumartist"] = [track.album_artist]
        if track.track_number:
            audio["tracknumber"] = [str(track.track_number)]
        if track.year:
            audio["date"] = [str(track.year)]
        if track.genre:
            audio["genre"] = [track.genre]

    def _tag_mp3(self, audio, track: Track):
        """Tag MP3 files (ID3 tags)"""
        # Ensure ID3 tags are present
        if not audio.tags:
            audio.add_tags()

        audio.tags.add(TIT2(encoding=3, text=track.name))
        audio.tags.add(TPE1(encoding=3, text=track.artist))
        audio.tags.add(TALB(encoding=3, text=track.album))

        if track.album_artist:
            audio.tags.add(TPE2(encoding=3, text=track.album_artist))
        if track.track_number:
            audio.tags.add(TRCK(encoding=3, text=str(track.track_number)))
        if track.year:
            audio.tags.add(TDRC(encoding=3, text=str(track.year)))
        if track.genre:
            audio.tags.add(TCON(encoding=3, text=track.genre))

    def _tag_mp4(self, audio: MP4, track: Track):
        """Tag MP4/M4A files"""
        audio.clear()
        audio["\xa9nam"] = [track.name]  # Title
        audio["\xa9ART"] = [track.artist]  # Artist
        audio["\xa9alb"] = [track.album]  # Album

        if track.album_artist:
            audio["aART"] = [track.album_artist]  # Album Artist
        if track.track_number:
            audio["trkn"] = [(track.track_number, 0)]  # Track number
        if track.year:
            audio["\xa9day"] = [str(track.year)]  # Year
        if track.genre:
            audio["\xa9gen"] = [track.genre]  # Genre

    def _tag_ogg(self, audio: OggVorbis, track: Track):
        """Tag OGG Vorbis files"""
        audio.clear()
        audio["title"] = [track.name]
        audio["artist"] = [track.artist]
        audio["album"] = [track.album]

        if track.album_artist:
            audio["albumartist"] = [track.album_artist]
        if track.track_number:
            audio["tracknumber"] = [str(track.track_number)]
        if track.year:
            audio["date"] = [str(track.year)]
        if track.genre:
            audio["genre"] = [track.genre]

    def _tag_generic(self, audio, track: Track):
        """Generic tagging for other formats"""
        try:
            if hasattr(audio, "tags") and audio.tags is not None:
                if hasattr(audio, "title"):
                    audio["title"] = track.name
                if hasattr(audio, "artist"):
                    audio["artist"] = track.artist
                if hasattr(audio, "album"):
                    audio["album"] = track.album
        except Exception as e:
            print(f"    ⚠️  Generic tagging limited: {e}")

    def organize_file(self, file_path: Path, track: Track) -> Optional[Path]:
        """Organize file into Lidarr-like directory structure"""
        print('    Organizing file into library structure...')

        # Clean and normalize names
        def clean_name(name: str) -> str:
            # Remove invalid characters for filenames
            cleaned = re.sub(r'[<>:"/\\|?*]', "", name)
            # Replace multiple spaces with single space
            cleaned = re.sub(r"\s+", " ", cleaned)
            return cleaned.strip()

        artist = clean_name(track.artist.split(",")[0].split("&")[0].strip())
        album = clean_name(track.album)
        title = clean_name(track.name)

        # Remove (feat. ...) from title for filename
        title_clean = re.sub(r"\s*\(feat\..*?\)|\s*\(ft\..*?\)", "", title)

        # Create directory structure: Artist/Album/
        album_dir = self.music_root / artist / album
        album_dir.mkdir(parents=True, exist_ok=True)

        # Determine file extension
        ext = file_path.suffix.lower()

        # Create filename: TrackNumber - Title.ext
        # For now, we'll use just the title since we don't have track number from Spotify
        new_filename = f"{title_clean}{ext}"
        new_path = album_dir / new_filename

        # Move and rename file
        if file_path != new_path:
            if new_path.exists():
                # Add timestamp if file exists
                timestamp = int(time.time())
                new_filename = f"{title_clean}_{timestamp}{ext}"
                new_path = album_dir / new_filename

            shutil.move(str(file_path), str(new_path))
            print(f"    ✓ Organized: {artist}/{album}/{new_filename}")

        return new_path

    def process_downloaded_file(self, file_path: Path, track: Track) -> Optional[Path]:
        """Process a downloaded file with tagging and organization"""
        if not file_path.exists():
            print(f"    ❌ File not found: {file_path}")
            return None

        print(f"    Processing downloaded file: {file_path.name}")

        # Tag the file with metadata
        tagging_success = self.tag_file(file_path, track)

        if not tagging_success:
            print("    ⚠️  Tagging failed, continuing with organization...")

        # Organize into library structure
        return self.organize_file(file_path, track)


class LocalMusicScanner:
    """Scans local music directories to check if tracks already exist"""

    AUDIO_EXTENSIONS = {
        ".mp3",
        ".flac",
        ".m4a",
        ".ogg",
        ".opus",
        ".ape",
        ".wma",
        ".alac",
        ".wav",
    }

    def __init__(self, music_dirs: List[str]):
        self.music_dirs = [Path(d).expanduser() for d in music_dirs]
        self.scanned_tracks: Set[str] = set()
        self._scan_directories()

    def _normalize_string(self, s: str) -> str:
        """Normalize string for comparison - remove special chars, lowercase"""
        # Remove everything except alphanumeric and spaces
        normalized = re.sub(r"[^\w\s]", "", s.lower())
        # Collapse multiple spaces
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def _remove_the_prefix(self, s: str) -> str:
        """Remove 'the ' prefix for better matching"""
        return re.sub(r"^the\s+", "", s)

    def _parse_from_filename(self, filename: str) -> Dict[str, str]:
        """Parse artist and title from filename patterns"""
        # Common patterns: "Artist - Title", "Artist-Title", "Title - Artist"
        patterns = [
            r"^(.*?)\s*[-–—]\s*(.*?)$",  # Artist - Title
            r"^(.*?)\s*[\(\[]\s*(.*?)\s*[\)\]]$",  # Artist (Title) or Title (Artist)
        ]

        for pattern in patterns:
            match = re.match(pattern, filename)
            if match:
                # Try to determine which is artist vs title
                group1, group2 = match.groups()
                # Heuristic: artist usually comes first and might be shorter
                if len(group1) < len(group2) or " - " in filename:
                    return {
                        "artist": self._normalize_string(group1),
                        "title": self._normalize_string(group2),
                    }
                else:
                    return {
                        "artist": self._normalize_string(group2),
                        "title": self._normalize_string(group1),
                    }

        # Fallback: use entire filename as title
        return {"artist": "unknown", "title": self._normalize_string(filename)}

    def _extract_metadata_from_file(self, filepath: Path) -> Optional[Dict[str, str]]:
        """Extract artist and title from audio file metadata with better fallbacks"""
        try:
            audio = MutagenFile(filepath)
            if audio is None:
                return self._parse_from_filename(filepath.stem)

            # Try different metadata tag formats
            metadata_sources = [
                # EasyID3 tags
                lambda: (
                    audio.get("artist", [None])[0]
                    if isinstance(audio.get("artist"), list)
                    else audio.get("artist"),
                    audio.get("title", [None])[0]
                    if isinstance(audio.get("title"), list)
                    else audio.get("title"),
                ),
                # Common tag fields
                lambda: (audio.get("artist"), audio.get("title")),
                lambda: (audio.get("ARTIST"), audio.get("TITLE")),
                # ID3 specific
                lambda: (
                    getattr(audio, "artist", [None])[0]
                    if hasattr(audio, "artist")
                    else None,
                    getattr(audio, "title", [None])[0]
                    if hasattr(audio, "title")
                    else None,
                ),
            ]

            artist, title = None, None
            for source in metadata_sources:
                try:
                    artist, title = source()
                    if artist and title:
                        break
                except (AttributeError, IndexError, KeyError, TypeError):
                    continue

            # Final fallback to filename parsing
            if not artist or not title:
                return self._parse_from_filename(filepath.stem)

            return {
                "artist": self._normalize_string(artist),
                "title": self._normalize_string(title),
            }
        except Exception as e:
            print(f"  ⚠️  Metadata extraction failed for {filepath.name}: {e}")
            return self._parse_from_filename(filepath.stem)

    def _scan_directories(self):
        """Scan all music directories with progress reporting"""
        print("\n🔍 Scanning local music directories...")

        total_files = 0
        processed_files = 0

        # Count total files first for progress reporting
        for music_dir in self.music_dirs:
            if music_dir.exists():
                total_files += sum(
                    1
                    for _ in music_dir.rglob("*")
                    if _.suffix.lower() in self.AUDIO_EXTENSIONS
                )

        if total_files == 0:
            print("  ⚠️  No audio files found in specified directories")
            return

        for music_dir in self.music_dirs:
            if not music_dir.exists():
                print(f"  ⚠️  Directory not found: {music_dir}")
                continue

            print(f"  Scanning: {music_dir}")

            for filepath in music_dir.rglob("*"):
                if filepath.suffix.lower() in self.AUDIO_EXTENSIONS:
                    processed_files += 1

                    if processed_files % 100 == 0:
                        print(
                            f"  Progress: {processed_files}/{total_files} files "
                            f"({processed_files / total_files * 100:.1f}%)"
                        )

                    # Try to extract metadata
                    metadata = self._extract_metadata_from_file(filepath)
                    if metadata:
                        # Create a normalized key: "artist|title"
                        key = f"{metadata['artist']}|{metadata['title']}"
                        self.scanned_tracks.add(key)

                    # Also add filename-based key as fallback
                    filename = filepath.stem
                    normalized_filename = self._normalize_string(filename)
                    self.scanned_tracks.add(normalized_filename)

        print(f"  ✓ Scanned {processed_files} audio files")
        print(f"  ✓ Indexed {len(self.scanned_tracks)} unique track signatures\n")

    def track_exists(self, track: Track) -> bool:
        """Check if a track already exists locally with multiple strategies"""
        artist_norm = self._normalize_string(track.artist)
        title_norm = self._normalize_string(track.name)

        # Split multiple artists (common in Spotify)
        primary_artist = artist_norm.split(",")[0].split("&")[0].strip()

        check_patterns = [
            # Exact metadata match
            f"{artist_norm}|{title_norm}",
            f"{primary_artist}|{title_norm}",
            # Filename patterns
            f"{artist_norm} {title_norm}",
            f"{primary_artist} {title_norm}",
            f"{title_norm} {artist_norm}",
            # Without "the" prefix
            self._remove_the_prefix(f"{artist_norm} {title_norm}"),
            self._remove_the_prefix(f"{primary_artist} {title_norm}"),
            # Just title (risky but common for popular songs)
            title_norm,
        ]

        # Also check variations without featured artists
        base_title = re.sub(r"\(feat\..*?\)|\(ft\..*?\)", "", title_norm).strip()
        if base_title != title_norm:
            check_patterns.extend(
                [
                    f"{artist_norm}|{base_title}",
                    f"{primary_artist}|{base_title}",
                    f"{artist_norm} {base_title}",
                ]
            )

        return any(
            pattern in self.scanned_tracks for pattern in check_patterns if pattern
        )

    def find_potential_duplicates(self) -> Dict[str, List[str]]:
        """Find potential duplicate tracks in the library"""
        duplicates = {}
        track_keys = list(self.scanned_tracks)

        for i, key1 in enumerate(track_keys):
            for key2 in track_keys[i + 1 :]:
                if self._are_similar_tracks(key1, key2):
                    if key1 not in duplicates:
                        duplicates[key1] = []
                    duplicates[key1].append(key2)

        return duplicates

    def _are_similar_tracks(self, key1: str, key2: str, threshold: float = 0.8) -> bool:
        """Check if two track keys are similar using fuzzy matching"""
        # If they share the same normalized artist|title format
        if "|" in key1 and "|" in key2:
            artist1, title1 = key1.split("|", 1)
            artist2, title2 = key2.split("|", 1)

            artist_similarity = SequenceMatcher(None, artist1, artist2).ratio()
            title_similarity = SequenceMatcher(None, title1, title2).ratio()

            return artist_similarity > threshold and title_similarity > threshold

        # For filename-based keys
        return SequenceMatcher(None, key1, key2).ratio() > threshold


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
    """Main application class with direct mutagen tagging"""

    def __init__(
        self,
        spotify_config: Dict,
        slskd_host: str,
        slskd_api_key: str,
        quality_profile: QualityProfile,
        music_root: str,
        slskd_url_base: str = "/",
    ):
        self.sp = spotipy.Spotify(auth_manager=SpotifyOAuth(**spotify_config))
        self.slskd = slskd_api.SlskdClient(slskd_host, slskd_api_key, slskd_url_base)
        self.matcher = QualityMatcher(quality_profile)
        self.quality_profile = quality_profile

        # Initialize mutagen tagger and directory structure
        self.tagger = MutagenTagger(music_root)

        # Scanner should only check the main music library, not intermediate directories
        self.scanner = LocalMusicScanner([music_root])

        # Track downloads for post-processing
        self.pending_downloads: List[Tuple[str, Track]] = []

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
                # Extract additional metadata if available
                album_artist=track_data["album"]["artists"][0]["name"]
                if track_data["album"]["artists"]
                else None,
                track_number=track_data.get("track_number"),
                year=int(track_data["album"]["release_date"][:4])
                if track_data["album"]["release_date"]
                else None,
            )
            tracks.append(track)

        return tracks

    def create_search_query(self, track: Track) -> str:
        """Create optimized search query"""
        # Remove featured artist info for cleaner search
        base_title = re.sub(r"\s*\(feat\..*?\)|\s*\(ft\..*?\)", "", track.name)
        return f"{track.artist} {base_title}"

    def wait_for_search_results(self, search_id: int, timeout: int = 15) -> Dict:
        """Wait for search to complete and return results"""
        start_time = time.time()

        while time.time() - start_time < timeout:
            print("    Checking search status...")
            try:
                # Check if search is complete or has enough results
                if self.slskd.searches.state(search_id, False).get("isComplete"):
                    return self.slskd.searches.search_responses(search_id)

                time.sleep(1)
            except Exception as e:
                print(f"    Error checking search status: {e}")
                time.sleep(1)

        # Return whatever we have after timeout
        try:
            return self.slskd.searches.search_responses(search_id)
        except Exception as e:
            print("    Error fetching final search results:", e)
            return []

    def monitor_download_completion(
        self, username: str, filename: str, track: Track, timeout: int = 300
    ) -> bool:
        """Monitor download progress and return True when complete"""
        print(f"    Monitoring download: {filename}")
        start_time = time.time()

        # Extract just the filename without path for matching
        simple_filename = Path(filename).name

        while time.time() - start_time < timeout:
            try:
                # Check transfer status
                transfers = self.slskd.transfers.get_all_downloads()

                for transfer in transfers:
                    transfer_file = Path(transfer.get("filename", "")).name
                    if (
                        transfer.get("user", "") == username
                        and transfer_file == simple_filename
                        and transfer.get("state") == "Completed"
                    ):
                        print("    ✓ Download completed")

                        # File should be in incomplete directory
                        expected_path = self.tagger.incomplete_dir / simple_filename
                        if expected_path.exists():
                            # Process with mutagen tagging
                            final_path = self.tagger.process_downloaded_file(
                                expected_path, track
                            )
                            if final_path:
                                print(
                                    f"    ✓ Successfully processed and organized: {final_path}"
                                )
                                return True
                            else:
                                print("    ❌ Failed to process downloaded file")
                                return False
                        else:
                            print(
                                f"    ❌ Downloaded file not found at: {expected_path}"
                            )
                            return False

                # Check if file exists in incomplete directory (direct filesystem check)
                for file_path in self.tagger.incomplete_dir.glob(
                    f"*{simple_filename}*"
                ):
                    if file_path.exists():
                        print(
                            f"    ✓ File found in incomplete directory: {file_path.name}"
                        )
                        final_path = self.tagger.process_downloaded_file(
                            file_path, track
                        )
                        if final_path:
                            print(
                                f"    ✓ Successfully processed and organized: {final_path}"
                            )
                            return True

                time.sleep(5)  # Check every 5 seconds

            except Exception as e:
                print(f"    Error monitoring download: {e}")
                time.sleep(5)

        print("    ❌ Download monitoring timeout")
        return False

    def download_track(self, track: Track) -> bool:
        """Search and download a track"""
        print(f"\n{'=' * 60}")
        print(f"Processing: {track.artist} - {track.name}")
        print(f"Album: {track.album}")
        print(f"Quality Profile: {self.quality_profile.value['name']}")
        print(f"{'=' * 60}")

        # Check if track already exists locally
        if self.scanner.track_exists(track):
            print("✓ Track already exists in local library - skipping")
            return True

        query = self.create_search_query(track)
        print(f"Searching for: {query}")

        try:
            # Check if the search is already in the queue
            existing_searches = self.slskd.searches.get_all()
            search = None
            for curr_search in existing_searches:
                if curr_search.get("searchText", "").lower() == query.lower():
                    search = curr_search
                    print("    Found existing search in queue")
                    break

            if search is None:
                # Initiate search
                print("    Starting new search...")
                search_response = self.slskd.searches.search_text(query)
                search = search_response

            if not search:
                print("❌ Failed to initiate search")
                return False

            # Wait for results
            print("    Waiting for search results...")
            search_results = self.wait_for_search_results(search.get("id"))

            if not search_results:
                print("❌ No results found")
                print(search_results)
                return False

            print(f"    Found {len(search_results)} users with results")

            best_match = self.matcher.find_best_match(search_results, track)

            if not best_match:
                print("❌ No suitable match found for quality profile")
                return False

            file_data = best_match["file"]
            username = best_match["username"]
            filename = file_data["filename"]

            print(f"\n    ✓ Best match (score: {best_match['score']:.1f}):")
            print(f"      User: {username}")
            print(f"      File: {filename}")
            print(f"      Size: {file_data['size'] / 1024 / 1024:.2f} MB")

            metadata = self.matcher.extract_metadata(filename)
            print(f"      Format: {metadata['format']}")
            print(
                f"      Bitrate: {metadata['bitrate']} kbps"
                if metadata["bitrate"]
                else "      Bitrate: Unknown"
            )

            print("\n    Initiating download...")

            # Use the slskd API to download
            self.slskd.transfers.enqueue(username=username, files=[file_data])

            print("    ✓ Download enqueued successfully")

            # Monitor download completion and process with mutagen tagging
            return self.monitor_download_completion(username, filename, track)

        except Exception as e:
            print(f"❌ Error during download: {e}")
            return False

    def run(self, track_limit: int = 10):
        """Main execution flow"""
        print(f"\n{'#' * 60}")
        print("Spotify to Slskd Downloader with Mutagen Tagging")
        print(f"Library: {self.tagger.music_root}")
        print(f"Downloads: {self.tagger.downloads_dir}")
        print(f"Incomplete: {self.tagger.incomplete_dir}")
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

        # Check for duplicates in local library
        duplicates = self.scanner.find_potential_duplicates()
        if duplicates:
            print(
                f"⚠️  Found {len(duplicates)} potential duplicate tracks in local library"
            )
            if input("Show duplicates? (y/N): ").lower() == "y":
                for key, dupes in list(duplicates.items())[:5]:  # Show first 5
                    print(f"  {key} -> {dupes[:3]}")  # Show first 3 duplicates

        print("\nFetching liked tracks from Spotify...")
        tracks = self.get_liked_tracks(limit=track_limit)

        print(f"\nFound {len(tracks)} tracks to download\n")

        successful = 0
        failed = 0
        skipped = 0

        for i, track in enumerate(tracks, 1):
            print(f"\n[{i}/{len(tracks)}]")

            result = self.download_track(track)

            # Check if track was skipped (already exists)
            if result and self.scanner.track_exists(track):
                skipped += 1
            elif result:
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
        print(f"Already in library (skipped): {skipped}")
        print(f"New downloads: {successful}")
        print(f"Failed: {failed}")
        print(f"{'=' * 60}\n")


def main():
    """Main function with configuration"""
    # Configuration from environment variables with fallbacks
    SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
    SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
    SLSKD_API_KEY = os.getenv("SLSKD_API_KEY")

    # Spotify API Configuration
    spotify_config = {
        "client_id": SPOTIFY_CLIENT_ID or "YOUR_SPOTIFY_CLIENT_ID",
        "client_secret": SPOTIFY_CLIENT_SECRET or "YOUR_SPOTIFY_CLIENT_SECRET",
        "redirect_uri": "http://localhost:8888/callback",
        "scope": "user-library-read",
    }

    # Slskd Configuration
    SLSKD_HOST = os.getenv("SLSKD_HOST", "http://localhost:5030")
    SLSKD_URL_BASE = os.getenv("SLSKD_URL_BASE", "/")

    # Music root directory
    MUSIC_ROOT = os.getenv("MUSIC_ROOT", "~/Media/music")

    # Quality profile selection
    profile_name = os.getenv("QUALITY_PROFILE", "LOSSLESS").upper()
    try:
        quality_profile = QualityProfile[profile_name]
    except KeyError:
        print(f"⚠️  Unknown quality profile: {profile_name}, using LOSSLESS")
        quality_profile = QualityProfile.LOSSLESS

    # Track limit
    track_limit = int(os.getenv("TRACK_LIMIT", "10"))

    # Validate configuration
    if (
        spotify_config["client_id"] == "YOUR_SPOTIFY_CLIENT_ID"
        or spotify_config["client_secret"] == "YOUR_SPOTIFY_CLIENT_SECRET"
    ):
        print(
            "❌ Please set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET environment variables"
        )
        return

    if SLSKD_API_KEY == "YOUR_SLSKD_API_KEY" or not SLSKD_API_KEY:
        print("❌ Please set SLSKD_API_KEY environment variable")
        return

    # Initialize and run
    downloader = SpotifySlskdDownloader(
        spotify_config=spotify_config,
        slskd_host=SLSKD_HOST,
        slskd_api_key=SLSKD_API_KEY,
        quality_profile=quality_profile,
        music_root=MUSIC_ROOT,
        slskd_url_base=SLSKD_URL_BASE,
    )

    downloader.run(track_limit=track_limit)


if __name__ == "__main__":
    main()
