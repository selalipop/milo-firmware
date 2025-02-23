import subprocess
import json
import shlex

def play_spotify_track(query: str) -> None:
    """
    Search for a track on Spotify using spotify-player and start playback.
    
    Args:
        query (str): Plain English search query for the track
    """
    try:
        # First, run the search command and capture its output
        search_cmd = f'spotify_player search "{query}"'
        search_result = subprocess.check_output(shlex.split(search_cmd), text=True)
        
        # Parse the JSON output and get the first track's ID
        track_data = json.loads(search_result)
        track_id = track_data['tracks'][0]['id']
        
        # Start playback with the track ID
        play_cmd = f'spotify_player playback start track --id {track_id}'
        subprocess.run(shlex.split(play_cmd))
        
    except subprocess.CalledProcessError as e:
        print(f"Error running spotify-player: {e}")
    except json.JSONDecodeError as e:
        print(f"Error parsing search results: {e}")
    except (KeyError, IndexError) as e:
        print(f"No tracks found for query: {query}")
    except Exception as e:
        print(f"Unexpected error: {e}")

# Example usage:
# play_spotify_track("Sweet Child O' Mine")