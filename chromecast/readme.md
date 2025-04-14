App to read the SD card called EASYROMS "/Volumes/EASYROMS/movies" in my Macbook Pro 2013 side port and browse files in the folder to select and stream to chromecast.

Requires CATT (Cast All The Things) to be installed.
https://github.com/skorokithakis/catt

server.py runs an app that is specific to casting media from ROOT/media/ to chromecast that can be accessed through browser via phone computer etc.

server2.py runs an app that does the same, but is limited to less functions as it works with the computer that is attached to the same television as the chromecast (some polling events cause CEC source changes that are annoying in server.py for the TV computer.  When trying to choose a show, polling causes a CEC event and cannot choose unless change source again).
