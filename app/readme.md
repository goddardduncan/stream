Searches OMDB for */media/* movie information and converts the output into the banner style streaming library.
Caches movie data in *metadata_cache.json*

App banner displays movies in */media/* folder and converts them into 10 second .ts files */tmp_hls/$MOVIE* for HLS streaming when a movie is teed up.  Displays a green flag when movie is ready to stream. 

Plays movies when "green flagged" movie selected from library in an HLS player on the page.

Server.py in the *chromecast* folder of this repo does much the same thing but uses CATT and pychromecast to control a chromecast while streaming media.
