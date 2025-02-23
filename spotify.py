import asyncio
import logging
import subprocess
import json
import shlex
import traceback

async def play_spotify_track(query: str) -> dict:
    """
    Search for a track on Spotify using spotify-player and start playback.
    
    Args:
        query (str): Plain English search query for the track
        
    Returns:
        dict: Track data including id, name, artist, etc. or error information
    """
    try:
        # First, run the search command and capture its output
        search_cmd = f'/home/teak/.cargo/bin/spotify_player search "{query}"'
        logging.info(f"Running search command: {search_cmd}")
        search_proc = await asyncio.create_subprocess_exec(
            *shlex.split(search_cmd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await search_proc.communicate()
        
        if search_proc.returncode != 0:
            return {"error": f"Search failed: {stderr.decode()}"}
            
        # Parse the JSON output and get the first track's data
        track_data = json.loads(stdout.decode())
        if not track_data.get('tracks'):
            return {"error": f"No tracks found for query: {query}"}
            
        track = track_data['tracks'][0]
        
        logging.info(f"Track data: {track}")
        # Start playback with the track ID
        play_cmd = f'/home/teak/.cargo/bin/spotify_player playback start radio track --id {track["id"]}'
        print(f"Running play command: {play_cmd}")
        play_proc = await asyncio.create_subprocess_exec(
            *shlex.split(play_cmd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        play_stdout, play_stderr = await play_proc.communicate()
        print("finished playing")
        if play_proc.returncode != 0:
            error_string = play_stderr.decode()
            print(f"Playback failed: {error_string}")
            return {"error": f"Playback failed: {error_string}"}
        
        print(f"Played track: {play_stdout.decode()}")      

        logging.info(f"Playback started for track: {track['name']}")
        
        return {
            "success": True,
            "track": track
        }
        
    except json.JSONDecodeError as e:
        traceback.print_exc()
        logging.error(f"Error parsing search results: {e}")
        return {"error": f"Error parsing search results: {e}"}
    except Exception as e:
        traceback.print_exc()
        logging.error(f"Unexpected error: {e}")
        return {"error": f"Unexpected error: {e}"}

# Example usage:
# async def main():
#     result = await play_spotify_track("Sweet Child O' Mine")
#     print(result)
# 
# asyncio.run(main())