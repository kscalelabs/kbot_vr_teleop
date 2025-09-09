// VideoScreenWeb.tsx
import { useEffect, useRef, useCallback } from 'react';

const configuration = {
  iceServers: [{ urls: 'stun:stun.l.google.com:19302' }],
};

interface VideoProps {
  setStreams: (streams: MediaStream[]) => void;
  vector: { x: number; y: number; z: number };
  setIsConnected: (isConnected: boolean) => void;
  setLocalStream: (stream: MediaStream) => void;
  call: boolean;
  url: string;
  signalingUrl: string;
  activeCameras: number[];
}

export default function VideoScreenWeb({
  setStreams,
  vector,
  setIsConnected,
  call,
  signalingUrl,
  url,
  activeCameras,
}: VideoProps) {
  const pc = useRef<RTCPeerConnection | null>(null);
  const ws = useRef<WebSocket | null>(null);
  const dataChannel = useRef<RTCDataChannel | null>(null);
  const streamsAdded = useRef(0);
  const currentStreams = useRef<MediaStream[]>([]);


  const setupPeerConnection = useCallback(
    async () => {
      pc.current = new RTCPeerConnection(configuration);

      pc.current.ontrack = (event) => {
        console.log('ontrack', event);
        const videoTrack = event.track;
        if (videoTrack.kind !== 'video') return;

        const newStream = new MediaStream();
        newStream.addTrack(videoTrack);

        console.log(`Adding track to stream ${streamsAdded.current}`);
        currentStreams.current[streamsAdded.current] = newStream;
        setStreams([...currentStreams.current]);
        streamsAdded.current++;
      };

      pc.current.onicecandidate = (event) => {
        if (event.candidate && ws.current) {
          ws.current.send(
            JSON.stringify({
              ice: {
                candidate: event.candidate.candidate,
                sdpMLineIndex: event.candidate.sdpMLineIndex,
              },
            })
          );
        }
      };

      pc.current.ondatachannel = (event) => {
        console.log('Data channel received:', event.channel.label);
        dataChannel.current = event.channel;

        dataChannel.current.onmessage = (msg) => {
          console.log('Message from robot:', msg.data);
        };
        dataChannel.current.onopen = () => console.log('Data channel opened');
        dataChannel.current.onclose = () => console.log('Data channel closed');
      };
    },
    [setStreams]
  );

  const setupWebSocket = useCallback(() => {
    ws.current = new WebSocket(url);

    ws.current.onopen = () => {
      console.log('WebSocket connected');
      setIsConnected(true);
      ws.current?.send(JSON.stringify({
        role: "app",
        robot_id: "box"
      }));
    };

    ws.current.onmessage = async (event) => {
      const message = JSON.parse(event.data);
      console.log('message', message);
      if(message.type === "robot_available"){ 
        console.log("sending HELLO with cameras:", activeCameras);
        const message = {
          type: "HELLO",
          cameras: activeCameras,
        };
        ws.current?.send(JSON.stringify(message));
     }
      if (message.sdp?.type === 'offer') {
        console.log('Received offer');
        const offerDesc = new RTCSessionDescription(message.sdp);
        await pc.current?.setRemoteDescription(offerDesc);
        const answer = await pc.current?.createAnswer();
        await pc.current?.setLocalDescription(answer);

        ws.current?.send(
          JSON.stringify({
            sdp: answer,
          })
        );
      }

      if (message.ice) {
        try {
          await pc.current?.addIceCandidate(message.ice);
        } catch (err) {
          console.warn('Error adding ICE candidate:', err);
        }
      }
    };

    ws.current.onerror = () => setIsConnected(false);
    ws.current.onclose = () => setIsConnected(false);
  }, [setIsConnected, signalingUrl]);

  const cleanup = useCallback(() => {
    console.log('Cleaning up WebRTC connection');
    dataChannel.current?.close();
    pc.current?.getSenders().forEach((sender) => sender.track?.stop());
    pc.current?.close();
    dataChannel.current = null;
    pc.current = null;
    streamsAdded.current = 0;
    currentStreams.current = [];
    setStreams([]);
  }, [setStreams]);

  const renegotiate = useCallback(async () => {
    cleanup();
    await setupPeerConnection();

    if (!ws.current) {
      setupWebSocket();
    } else if (ws.current.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({ type: "HELLO", cameras: activeCameras }));
    } else {
      console.log('WebSocket not open yet, will send HELLO later');
    }
  }, [cleanup, setupPeerConnection, setupWebSocket, activeCameras]);

  useEffect(() => {
    console.log('Renegotiating');
    renegotiate();
    return cleanup;
  }, []);

  useEffect(() => {
    if (dataChannel.current?.readyState === 'open') {
      dataChannel.current.send(JSON.stringify(vector));
    } else {
      console.log('Data channel not open');
    }
  }, [vector]);

  return null;
}
