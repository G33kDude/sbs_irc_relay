# sbs_irc_relay
IRC relay for the SmileBasicSource.com web chat


Dependencies
------------

* **Python 3** (apt-get `python3`)
* **websocket-client** (pip3 `websocket-client`, apt-get `python3-websocket`)
* **PIL/Pillow** (pip3 `pillow`, apt-get `python3-pillow`)


Connecting
----------

1. Modify `sbs.py` to point away from the dev site
   * Change `self.query_endpoint` to `https://smilebasicsource.com/query`
   * Change `self.chat_port` to `45695`
2. (Optional) Change the end of `decode_draw` in `decoders.py` to save
   images to a web root instead of showing directly to the screen. This is
   useful if you're running the bridge on a remote server.
3. Run `server.py` using Python 3.
4. Connect using an IRC client.
   * Set your nick to your SBS username
   * Set your pass to your SBS password
