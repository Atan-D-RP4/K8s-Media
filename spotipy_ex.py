from typing import Callable, Iterable
import os
import json
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth

# Read Spotify credentials from a secure location or environment variables
load_dotenv()  # Adjust the path as necessary

# Read Spotify credentials from a secure location or environment variables
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

sp = spotipy.Spotify(
    auth_manager=SpotifyOAuth(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        redirect_uri="http://localhost:8888/callback",
        scope="user-library-read user-follow-read user-read-private playlist-read-private playlist-read-collaborative",
    )
)


# Take a function as an argument
def get_list(func: Callable) -> Iterable:
    offset = 0
    limit = 50
    while True:
        try:
            results = func(limit=limit, offset=offset)
        except Exception as e:
            print(f"An error occurred: {e}")
            break
        if not results["items"]:
            break
        try:
            for item in results["items"]:
                yield item
        except Exception as e:
            print(f"An error occurred: {e}")
            break

        offset += limit


def search(
    query: str,
    types: list[str] = ["track", "album", "artist", "playlist"],
    limit: int = 10,
) -> dict:
    type = ",".join(types)
    results = sp.search(q=query, type=type, limit=limit)
    return results


def display_results(results: dict) -> None:
    for category, items in results.items():
        if not items:
            continue
        print(f"\n{category.capitalize()} Results:")
        for i, item in enumerate(items["items"]):
            try:
                if category == "tracks":
                    print(f"{i + 1}. {item['name']} - {item['artists'][0]['name']}")
                elif category == "albums":
                    print(f"{i + 1}. {item['name']} by {item['artists'][0]['name']}")
                elif category == "artists":
                    print(f"{i + 1}. {item['name']}")
                elif category == "playlists":
                    print(f"{i + 1}. {item['name']} by {item['owner']['display_name']}")
            except Exception as e:
                print(f"An error occurred: {e}")


display_results(search(input("Enter your search query: ").strip()))

# print(f"User: {sp.current_user()['display_name']}")

# print("Featured Playlists:")
# for i, item in enumerate(sp.featured_playlists(limit=5)):
#     try:
#         print(f"{i + 1}. {item}")
#     except Exception as e:
#         print(f"An error occurred: {e}")


# print("Playlists:")
# for i, item in enumerate(get_list(sp.current_user_playlists)):
#     try:
#         print(f"{i + 1}. {item['name']} - {item['tracks']['total']}")
#     except Exception as e:
#         print(f"An error occurred: {e}")

# print("Saved Albums:")
# for i, item in enumerate(get_list(sp.current_user_saved_albums)):
#     try:
#         album = item["album"]
#         print(f"{i + 1}. {album['artists'][0]['name']} - {album['name']}")
#     except Exception as e:
#         print(f"An error occurred: {e}")

# print("Liked Songs:")
# for i, item in enumerate(get_list(sp.current_user_saved_tracks)):
#     try:
#         track = item["track"]
#         print(f"{i + 1}. {track['artists'][0]['name']} - {track['name']}")
#     except Exception as e:
#         print(f"An error occurred: {e}")

# print("Followed Artists:")
# limit = 50
# offset = 0
# after = None
# while True:
#     try:
#         results = sp.current_user_followed_artists(limit=limit, after=after)
#     except Exception as e:
#         print(f"An error occurred: {e}")
#         break
#     if not results["artists"]["items"]:
#         break
#     try:
#         for item in results["artists"]["items"]:
#             print(f"{offset + 1}. {item['name']}")
#             offset += 1
#     except Exception as e:
#         print(f"An error occurred: {e}")
#         break

#     after = results["artists"]["cursors"]["after"]
#     if after is None:
#         break
