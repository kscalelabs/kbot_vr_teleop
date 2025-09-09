import React, { useState } from 'react';
import VideoScreenWeb from './Video.tsx';
import SideBySideVideo from './SideBySideVideo.tsx';
import Billboard from './Billboard.tsx';

function App() {
  const portString = window.location.port ? `:${window.location.port}` : '';
  const [url, setUrl] = useState(`wss://${window.location.hostname}${portString}/service2`);
  const [viewMode, setViewMode] = useState("browser"); // "browser", "vr", or "billboard"
  const [isConnected, setIsConnected] = useState(false);
  const [streams, setStreams] = useState([]); // Array of MediaStreams
  const [activeCameras, setActiveCameras] = useState([0]); // Camera 0 starts active

  const handleConnect = () => {
    setIsConnected(true);
  };

  const handleDisconnect = () => {
    setIsConnected(false);
    setStreams([]);
  };

  const toggleCamera = (cameraIndex) => {
    setActiveCameras(prev => {
      if (prev.includes(cameraIndex)) {
        // Remove camera if it's already active
        return prev.filter(cam => cam !== cameraIndex);
      } else {
        // Add camera if it's not active
        return [...prev, cameraIndex].sort();
      }
    });
  };

  return (
    <div style={{ 
      padding: '20px', 
      fontFamily: 'Arial, sans-serif',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      minHeight: '100vh'
    }}>
      <div style={{ 
        marginBottom: '20px', 
        display: 'flex', 
        flexDirection: 'column', 
        gap: '10px', 
        maxWidth: '400px',
        width: '100%'
      }}>
        <h2>VR Stream Controller</h2>
        
        <div>
          <label htmlFor="url-input" style={{ display: 'block', marginBottom: '5px' }}>
            WebSocket URL:
          </label>
          <input
            id="url-input"
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            disabled={isConnected}
            style={{
              width: '100%',
              padding: '8px',
              border: '1px solid #ccc',
              borderRadius: '4px',
              fontSize: '14px'
            }}
            placeholder="Enter WebSocket URL"
          />
        </div>

        <div>
          <label htmlFor="view-mode" style={{ display: 'block', marginBottom: '5px' }}>
            View Mode:
          </label>
          <select
            id="view-mode"
            value={viewMode}
            onChange={(e) => setViewMode(e.target.value)}
            disabled={isConnected}
            style={{
              width: '100%',
              padding: '8px',
              border: '1px solid #ccc',
              borderRadius: '4px',
              fontSize: '14px'
            }}
          >
            <option value="browser">Browser View</option>
            {/* <option value="vr">VR View</option> */}
            <option value="billboard">Billboard</option>
          </select>
        </div>

        <div>
          <label style={{ display: 'block', marginBottom: '5px' }}>
            Active Cameras:
          </label>
          <div style={{ display: 'flex', gap: '10px', marginBottom: '10px' }}>
            <button
              onClick={() => toggleCamera(0)}
              style={{
                padding: '8px 16px',
                backgroundColor: activeCameras.includes(0) ? '#28a745' : '#6c757d',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                fontSize: '14px'
              }}
            >
              Camera 0 {activeCameras.includes(0) ? '✓' : ''}
            </button>
            <button
              onClick={() => toggleCamera(1)}
              style={{
                padding: '8px 16px',
                backgroundColor: activeCameras.includes(1) ? '#28a745' : '#6c757d',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                fontSize: '14px'
              }}
            >
              Camera 1 {activeCameras.includes(1) ? '✓' : ''}
            </button>
          </div>
          <div style={{ 
            fontSize: '12px', 
            color: '#666', 
            marginBottom: '10px' 
          }}>
            Active: [{activeCameras.join(', ')}]
          </div>
        </div>

        <div style={{ display: 'flex', gap: '10px' }}>
          <button
            onClick={handleConnect}
            disabled={isConnected}
            style={{
              padding: '10px 20px',
              backgroundColor: isConnected ? '#ccc' : '#007bff',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: isConnected ? 'not-allowed' : 'pointer',
              fontSize: '14px'
            }}
          >
            {isConnected ? 'Connected' : 'Connect'}
          </button>
          
          <button
            onClick={handleDisconnect}
            disabled={!isConnected}
            style={{
              padding: '10px 20px',
              backgroundColor: !isConnected ? '#ccc' : '#dc3545',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: !isConnected ? 'not-allowed' : 'pointer',
              fontSize: '14px'
            }}
          >
            Disconnect
          </button>
        </div>

        {isConnected && (
          <div style={{ padding: '10px', backgroundColor: '#d4edda', border: '1px solid #c3e6cb', borderRadius: '4px', color: '#155724' }}>
            Connected in {viewMode === 'vr' ? 'VR' : viewMode === 'billboard' ? 'Billboard' : 'Browser'} mode
          </div>
        )}
      </div>

      {isConnected && (
        <div style={{ width: '100%', maxWidth: '1200px' }}>
          {/* Always mount VideoScreenWeb when connected - it provides the streams */}
          <VideoScreenWeb
            setStreams={setStreams}
            setIsConnected={() => {}}
            setLocalStream={() => {}}
            vector={{ x: 0, y: 0, z: 0 }}
            call={true}
            url={url}
            signalingUrl="10.33.13.62"
            activeCameras={activeCameras}
          />

          {/* Conditionally mount the view component based on selected mode */}
          {viewMode === 'vr' ? (
            <></>
            // <StereoVR 
            //   streamLeft={streams[0] || null} 
            //   streamRight={streams[1] || null} 
            //   url={url}
            // />
          ) : viewMode === 'billboard' ? (
            <Billboard 
              stream={streams[0] || null}
              url={url}
            />
          ) : (
            <SideBySideVideo 
              streams={streams}
            />
          )}
        </div>
      )}
    </div>
  );
}

export default App;