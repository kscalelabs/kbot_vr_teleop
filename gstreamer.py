import asyncio
import json
import ssl
import websockets
import os
import argparse

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstWebRTC', '1.0')
gi.require_version('GstSdp', '1.0')
from gi.repository import Gst, GstWebRTC, GstSdp, GLib

Gst.init(None)

# WebSocket configuration
# HOST_URL= "wss://c47174bc6ce1.ngrok-free.app"
HOST_URL= "ws://10.33.13.51:8013"
PIPELINE_DESC = '''
webrtcbin name=sendrecv bundle-policy=max-bundle stun-server=stun://stun.l.google.com:19302
'''

VIDEO_SOURCES = [
    "/base/axi/pcie@1000120000/rp1/i2c@80000/ov5647@36",
    "/base/axi/pcie@1000120000/rp1/i2c@88000/ov5647@36"
]


async def glib_main_loop_iteration():
    while True:
        # Process all pending GLib events without blocking
        while GLib.main_context_default().iteration(False):
            pass
        # Yield control back to asyncio, adjust delay as needed
        await asyncio.sleep(0.01)

class WebRTCClient:
    def __init__(self, loop, flip_video=False, left_mp4=None, right_mp4=None):
        self.pipe = None
        self.webrtc = None
        self.ws = None  # WebSocket connection
        self.loop = loop
        self.added_data_channel = False
        self.flip_video = flip_video
        self.left_mp4 = left_mp4
        self.right_mp4 = right_mp4

    def start_pipeline(self, active_cameras):
        print("Starting pipeline")
        self.pipe = Gst.Pipeline.new("pipeline")
        webrtc = Gst.parse_launch(PIPELINE_DESC)
        self.pipe.add(webrtc)
        print(self.pipe)
        bus = self.pipe.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_bus_message)
        self.webrtc = self.pipe.get_by_name("sendrecv")
        self.webrtc.set_property("latency", 200)
        self.webrtc.connect("on-ice-candidate", self.send_ice_candidate_message)

        # Determine sources: MP4 files or cameras
        sources = []
        if self.left_mp4 or self.right_mp4:
            # Use MP4 files if provided
            if self.left_mp4:
                sources.append({'type': 'mp4', 'path': self.left_mp4})
            if self.right_mp4:
                sources.append({'type': 'mp4', 'path': self.right_mp4})
        else:
            # Use camera sources
            for i in range(len(active_cameras)):
                sources.append({'type': 'camera', 'path': VIDEO_SOURCES[active_cameras[i]]})

        for i, src_info in enumerate(sources):
            if src_info['type'] == 'mp4':
                src = Gst.ElementFactory.make("filesrc", f"filesrc{i}")
                src.set_property("location", src_info['path'])
                demux = Gst.ElementFactory.make("qtdemux", f"demux{i}")
                decode = Gst.ElementFactory.make("decodebin", f"decode{i}")
                conv = Gst.ElementFactory.make("videoconvert", f"conv{i}")
                caps = Gst.Caps.from_string("video/x-raw,format=I420, framerate=30/1")
                capsfilter = Gst.ElementFactory.make("capsfilter", f"caps{i}")
                capsfilter.set_property("caps", caps)
                queue = Gst.ElementFactory.make("queue", f"queue{i}")
                queue.set_property("leaky", 1)
                queue.set_property("max-size-buffers", 1)
                vp8enc = Gst.ElementFactory.make("vp8enc", f"vp8enc{i}")
                vp8enc.set_property("deadline", 1)
                pay = Gst.ElementFactory.make("rtpvp8pay", f"pay{i}")
                pay.set_property("pt", 96+i)
                self.pipe.add(src)
                self.pipe.add(demux)
                self.pipe.add(decode)
                self.pipe.add(conv)
                self.pipe.add(capsfilter)
                self.pipe.add(queue)
                self.pipe.add(vp8enc)
                self.pipe.add(pay)
                src.link(demux)
                demux.connect("pad-added", lambda demux, pad: pad.link(decode.get_static_pad("sink")))
                decode.connect("pad-added", lambda decode, pad: pad.link(conv.get_static_pad("sink")))
                conv.link(capsfilter)
                capsfilter.link(queue)
                queue.link(vp8enc)
                vp8enc.link(pay)
                # Add transceiver
                src_pad = pay.get_static_pad("src")
                sink_pad = webrtc.get_request_pad(f"sink_{i}")
                if not sink_pad:
                    print(f"Failed to get sink pad for stream {i}")
                else:
                    ret = src_pad.link(sink_pad)
                    print("Pad link result", ret)
            else:
                # Camera source (original logic)
                src = Gst.ElementFactory.make("libcamerasrc", f"libcamerasrc{i}")
                src.set_property("camera-name", src_info['path'])
                print("camera-name", src.get_property("camera-name"))
                caps = Gst.Caps.from_string("video/x-raw,format=YUY2, framerate=30/1")
                capsfilter = Gst.ElementFactory.make("capsfilter", f"caps{i}")
                capsfilter.set_property("caps", caps)
                conv = Gst.ElementFactory.make("videoconvert", f"conv{i}")
                if self.flip_video:
                    flip = Gst.ElementFactory.make("videoflip", f"flip{i}")
                    flip.set_property("method", 5)
                    self.pipe.add(flip)
                queue = Gst.ElementFactory.make("queue", f"queue{i}")
                queue.set_property("leaky", 1)
                queue.set_property("max-size-buffers", 1)
                vp8enc = Gst.ElementFactory.make("vp8enc", f"vp8enc{i}")
                vp8enc.set_property("deadline", 1)
                pay = Gst.ElementFactory.make("rtpvp8pay", f"pay{i}")
                pay.set_property("pt", 96+i)
                self.pipe.add(src)
                self.pipe.add(capsfilter)
                self.pipe.add(conv)
                self.pipe.add(queue)
                self.pipe.add(vp8enc)
                self.pipe.add(pay)
                src.link(capsfilter)
                capsfilter.link(conv)
                if self.flip_video:
                    conv.link(flip)
                    flip.link(queue)
                else:
                    conv.link(queue)
                queue.link(vp8enc)
                vp8enc.link(pay)
                src_pad = pay.get_static_pad("src")
                sink_pad = webrtc.get_request_pad(f"sink_{i}")
                if not sink_pad:
                    print(f"Failed to get sink pad for stream {i}")
                else:
                    ret = src_pad.link(sink_pad)
                    print("Pad link result", ret)

        self.webrtc.connect("on-negotiation-needed", self.on_negotiation_needed)
        self.pipe.set_state(Gst.State.PLAYING)
        print("Pipeline started")

    def on_bus_message(self, bus, message):
        """Handle messages from the GStreamer bus, specifically for latency."""
        t = message.type
        if t == Gst.MessageType.LATENCY:
            print("Received a LATENCY message. Recalculating latency.")
            self.pipe.recalculate_latency()

        return GLib.SOURCE_CONTINUE
    def close_pipeline(self):
        self.added_data_channel = False
        if self.pipe:
            self.pipe.set_state(Gst.State.NULL)
            self.pipe = None
            self.webrtc = None

    def on_message_string(self, channel, message):
        print("Received:", message)

    def on_negotiation_needed(self, element):
        print("Negotiation needed")
        if self.added_data_channel:
            print("Data channel already added")
            return
        self.added_data_channel = True
        
        promise = Gst.Promise.new_with_change_func(self.on_offer_created, element, None)
        self.webrtc.emit("create-offer", None, promise)

    def on_offer_created(self, promise, _, __):
        print("on offer created")
        promise.wait()
        reply = promise.get_reply()
        offer = reply.get_value("offer")
        print("offer:", offer)
        self.webrtc.emit("set-local-description", offer, Gst.Promise.new())
        text = offer.sdp.as_text()
        print("offertext:", text)
        message = json.dumps({'sdp': {'type': 'offer', 'sdp': text}})
        asyncio.run_coroutine_threadsafe(self.ws.send(message), self.loop)

    def send_ice_candidate_message(self, _, mlineindex, candidate):
        message = json.dumps({
            'ice': {'candidate': candidate, 'sdpMLineIndex': mlineindex}
        })
        asyncio.run_coroutine_threadsafe(self.ws.send(message), self.loop)

    def handle_client_message(self, message):
        print("Handling client message")
        print(message)
        msg = json.loads(message)
        cameras = msg.get("cameras", [])
        if(msg.get("type") == "HELLO"):
            if(self.pipe):
                self.close_pipeline()
           
            self.start_pipeline(cameras)
       
            return
        if 'sdp' in msg and msg['sdp']['type'] == 'answer':
            sdp = msg['sdp']['sdp']
            res, sdpmsg = GstSdp.SDPMessage.new()
            GstSdp.sdp_message_parse_buffer(sdp.encode(), sdpmsg)
            answer = GstWebRTC.WebRTCSessionDescription.new(GstWebRTC.WebRTCSDPType.ANSWER, sdpmsg)
            self.webrtc.emit("set-remote-description", answer, Gst.Promise.new())
        elif 'ice' in msg:
            ice = msg['ice']
            self.webrtc.emit("add-ice-candidate", ice['sdpMLineIndex'], ice['candidate'])

    async def connect_websocket(self):
        """Connect to WebSocket server and handle messages"""
        try:
            print(f"Connecting to {HOST_URL}...")
            async with websockets.connect(HOST_URL) as websocket:
                print("Connected to WebSocket server")
                self.ws = websocket
                
                # Send initial HELLO message to start pipeline
                await websocket.send(json.dumps({"role": "robot", "robot_id": "box"}))
                
                async for message in websocket:
                    self.handle_client_message(message)
                    
        except websockets.exceptions.ConnectionClosed:
            print("WebSocket connection closed")
        except Exception as e:
            print(f"WebSocket error: {e}")
        finally:
            if self.pipe:
                self.pipe.set_state(Gst.State.NULL)

async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='WebRTC Video Streaming Client')
    parser.add_argument('--flip', action='store_true', help='Vertically flip the video stream')
    parser.add_argument('--left-mp4', type=str, default=None, help='Path to left eye MP4 file')
    parser.add_argument('--right-mp4', type=str, default=None, help='Path to right eye MP4 file')
    args = parser.parse_args()

    loop = asyncio.get_running_loop()
    client = WebRTCClient(loop, flip_video=args.flip, left_mp4=args.left_mp4, right_mp4=args.right_mp4)

    # Start the GLib main loop iteration task
    asyncio.create_task(glib_main_loop_iteration())

    # Connect to the WebSocket server
    await client.connect_websocket()

if __name__ == "__main__":
    asyncio.run(main())
