import asyncio
import json
import websockets
import threading
import time

import gi
gi.require_version("Gst", "1.0")
gi.require_version("GstWebRTC", "1.0")
gi.require_version("GstSdp", "1.0")
from gi.repository import Gst, GstWebRTC, GstSdp, GLib

Gst.init(None)

import numpy as np # If these run before Gst.init(), it segfaults
import cv2

WS_HOST = "0.0.0.0"
WS_PORT = 8013
STUN_SERVER = "stun://stun.l.google.com:19302"

class OneRecvPeer:
    """
    One peer connection that only RECEIVES a single video track and displays it.
    """
    def __init__(self):
        self.pipe = None
        self.webrtc = None
        self.latest_frame = None
        self.ws = None
        self.thread = threading.Thread(target=self.async_loop_thread)
        self.thread.start()

    async def glib_pump(self):
        ctx = GLib.MainContext.default()
        while True:
            while ctx.pending():
                ctx.iteration(False)
            await asyncio.sleep(0.01)

    # --- GStreamer wiring ---
    def _on_decodebin_pad_added(self, decodebin, pad, convert):
        sink = convert.get_static_pad("sink")
        if not sink.is_linked():
            pad.link(sink)

    def _on_webrtc_pad_added(self, webrtc, pad):
        if pad.get_direction() != Gst.PadDirection.SRC:
            return
        queue = Gst.ElementFactory.make("queue")
        decodebin = Gst.ElementFactory.make("decodebin")
        convert = Gst.ElementFactory.make("videoconvert")
        caps = Gst.Caps.from_string("video/x-raw,format=BGR")
        appsink = Gst.ElementFactory.make("appsink")
        appsink.set_property("emit-signals", True)
        appsink.set_property("caps", caps)
        appsink.set_property("sync", False)

        self.pipe.add(queue); self.pipe.add(decodebin); self.pipe.add(convert); self.pipe.add(appsink)
        for e in (queue, decodebin, convert, appsink):
            e.sync_state_with_parent()

        # webrtc:srcpad -> queue:sink
        q_sink = queue.get_static_pad("sink")
        pad.link(q_sink)

        # queue -> decodebin (dynamic) -> convert -> appsink
        if not queue.link(decodebin):
            print("queue->decodebin link failed")
        if not convert.link(appsink):
            print("videoconvert->appsink link failed")

        decodebin.connect("pad-added", self._on_decodebin_pad_added, convert)

        def on_new_sample(sink):
            sample = sink.emit("pull-sample")
            buf = sample.get_buffer()
            caps = sample.get_caps()
            arr = None
            try:
                # Get video info
                structure = caps.get_structure(0)
                width = structure.get_value('width')
                height = structure.get_value('height')
                # Extract buffer data
                success, mapinfo = buf.map(Gst.MapFlags.READ)
                if not success:
                    return Gst.FlowReturn.ERROR
                frame = np.frombuffer(mapinfo.data, dtype=np.uint8)
                frame = frame.reshape((height, width, 3))
                buf.unmap(mapinfo)
                # Now frame is a BGR image (OpenCV format)
                # Example: show with OpenCV (remove for headless)
                self.latest_frame = frame
            except Exception as e:
                print(f"Error in on_new_sample: {e}")
            return Gst.FlowReturn.OK

        appsink.connect("new-sample", on_new_sample)

    async def _send_json(self, obj):
        if self.ws:
            await self.ws.send(json.dumps(obj))

    def _send_json_threadsafe(self, obj):
        # Schedule the coroutine on the captured asyncio loop from any GI/GStreamer thread
        asyncio.run_coroutine_threadsafe(self._send_json(obj), self.loop)

    def _on_ice_candidate(self, webrtc, mline, candidate):
        # Called from a GI thread → must hop into asyncio loop
        self._send_json_threadsafe({"ice": {"candidate": candidate, "sdpMLineIndex": int(mline)}})

    def build_pipeline(self):
        self.pipe = Gst.Pipeline.new("recv-pipe")
        self.webrtc = Gst.ElementFactory.make("webrtcbin", "webrtcbin")
        self.webrtc.set_property("stun-server", STUN_SERVER)
        self.webrtc.set_property("latency", 300)
        self.pipe.add(self.webrtc)
        self.webrtc.connect("pad-added", self._on_webrtc_pad_added)
        self.webrtc.connect("on-ice-candidate", self._on_ice_candidate)

        # (Optional) prefer VP8 without using add-transceiver; remote offer usually drives codec

        self.pipe.set_state(Gst.State.PLAYING)

    # --- SDP / ICE handling ---
    async def handle_offer(self, sdp_text: str):
        res, sdpmsg = GstSdp.SDPMessage.new()
        GstSdp.sdp_message_parse_buffer(sdp_text.encode("utf-8"), sdpmsg)
        offer = GstWebRTC.WebRTCSessionDescription.new(GstWebRTC.WebRTCSDPType.OFFER, sdpmsg)
        self.webrtc.emit("set-remote-description", offer, Gst.Promise.new())

        # Create local answer (callback happens on GI thread)
        promise = Gst.Promise.new_with_change_func(self._on_answer_created, None, None)
        self.webrtc.emit("create-answer", None, promise)

    def _on_answer_created(self, promise, *_):
        promise.wait()
        reply = promise.get_reply()
        answer = reply.get_value("answer")
        self.webrtc.emit("set-local-description", answer, Gst.Promise.new())
        text = answer.sdp.as_text()
        # GI thread → hop to asyncio loop
        self._send_json_threadsafe({"sdp": {"type": "answer", "sdp": text}})

    def add_remote_ice(self, mlineindex: int, candidate: str):
        self.webrtc.emit("add-ice-candidate", int(mlineindex), candidate)
    
    def get_latest_frame(self):
        return self.latest_frame

    def close(self):
        if self.pipe:
            self.pipe.set_state(Gst.State.NULL)
        self.pipe = None
        self.webrtc = None

    async def handler(self, websocket):
        self.ws = websocket
        print("Client connected")
        try:
            # Kick the client to start one camera
            await websocket.send(json.dumps({"type": "HELLO", "cameras": [0]}))

            # Build our receive-only pipeline
            self.build_pipeline()

            async for msg in websocket:
                data = json.loads(msg)

                # ignore initial role message
                if "role" in data:
                    print("Role:", data["role"])
                    continue

                if "sdp" in data and data["sdp"]["type"] == "offer":
                    await self.handle_offer(data["sdp"]["sdp"])
                elif "ice" in data:
                    ice = data["ice"]
                    self.add_remote_ice(ice["sdpMLineIndex"], ice["candidate"])
        except websockets.exceptions.ConnectionClosed:
            print("Client disconnected")
        finally:
            self.close()

    async def async_loop(self):
        self.loop = asyncio.get_running_loop()              # <-- keep a handle to the main asyncio loop
        asyncio.create_task(self.glib_pump())
        async with websockets.serve(self.handler, WS_HOST, WS_PORT, ping_interval=20, ping_timeout=20):
            print(f"WebSocket server listening on ws://{WS_HOST}:{WS_PORT}")
            await asyncio.Future() # run forever
    
    def async_loop_thread(self):
        asyncio.run(self.async_loop())

if __name__ == "__main__":
    peer = OneRecvPeer()
    while True:
        frame = peer.get_latest_frame()
        if frame is not None:
            cv2.imshow("Received Video", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        time.sleep(1/30)
