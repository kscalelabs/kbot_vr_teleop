import React, { useState } from 'react';
import VideoScreenWeb from './Video.tsx';
import SideBySideVideo from './SideBySideVideo.tsx';
import Billboard from './Billboard.tsx';
import Sphere from './Sphere.tsx';
import URDFViewer from './URDFViewer.tsx';

function App() {
  const portString = window.location.port ? `:${window.location.port}` : '';
  const [url, setUrl] = useState(`wss://${window.location.hostname}${portString}/service2`);
  const [viewMode, setViewMode] = useState("browser"); // "browser", "vr", "billboard", "sphere", or "urdf"
  const [isConnected, setIsConnected] = useState(false);
  const [streams, setStreams] = useState([]); // Array of MediaStreams
  const [activeCameras, setActiveCameras] = useState([0]); // Camera 0 starts active
  const [hands, setHands] = useState(true);
  
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
      minHeight: '100vh',
      backgroundColor: '#000000',
      color: '#ffffff'
    }}>
      <div style={{ 
        marginBottom: '20px', 
        display: 'flex', 
        flexDirection: 'column', 
        gap: '10px', 
        maxWidth: '400px',
        width: '100%'
      }}>
        <h1 style={{ 
          textAlign: 'center', 
          color: '#ffffff', 
          marginBottom: '20px',
          fontSize: '28px',
          fontWeight: 'bold'
        }}>
          K-Scale
        </h1>

        {/* Tracking Mode Toggle */}
        <div style={{ marginBottom: '20px', textAlign: 'center' }}>
          <label style={{ display: 'block', marginBottom: '10px', color: '#ffffff', fontSize: '16px' }}>
            Tracking Mode:
          </label>
          <div style={{ display: 'flex', gap: '0px', border: '2px solid #333', borderRadius: '8px', overflow: 'hidden' }}>
            <button
              onClick={() => setHands(false)}
              disabled={isConnected}
              style={{
                flex: 1,
                padding: '12px 20px',
                backgroundColor: !hands ? '#007bff' : '#333333',
                color: !hands ? '#ffffff' : '#cccccc',
                border: 'none',
                cursor: isConnected ? 'not-allowed' : 'pointer',
                fontSize: '14px',
                fontWeight: !hands ? 'bold' : 'normal',
                transition: 'all 0.2s ease'
              }}
            >
              Controller
            </button>
            <button
              onClick={() => setHands(true)}
              disabled={isConnected}
              style={{
                flex: 1,
                padding: '12px 20px',
                backgroundColor: hands ? '#007bff' : '#333333',
                color: hands ? '#ffffff' : '#cccccc',
                border: 'none',
                cursor: isConnected ? 'not-allowed' : 'pointer',
                fontSize: '14px',
                fontWeight: hands ? 'bold' : 'normal',
                transition: 'all 0.2s ease'
              }}
            >
              Hands
            </button>
          </div>
        </div>
        
        <div style={{ textAlign: 'center' }}>
          <label htmlFor="url-input" style={{ display: 'block', marginBottom: '5px', color: '#ffffff' }}>
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
              border: '1px solid #555',
              borderRadius: '4px',
              fontSize: '14px',
              backgroundColor: '#222222',
              color: '#ffffff'
            }}
            placeholder="Enter WebSocket URL"
          />
        </div>

        <div style={{ marginBottom: '20px', textAlign: 'center' }}>
          <label style={{ display: 'block', marginBottom: '10px', color: '#ffffff', fontSize: '16px' }}>
            View Mode:
          </label>
          <div style={{ display: 'flex', gap: '0px', border: '2px solid #333', borderRadius: '8px', overflow: 'hidden' }}>
            <button
              onClick={() => setViewMode('browser')}
              disabled={isConnected}
              style={{
                flex: 1,
                padding: '12px 16px',
                backgroundColor: viewMode === 'browser' ? '#007bff' : '#333333',
                color: viewMode === 'browser' ? '#ffffff' : '#cccccc',
                border: 'none',
                cursor: isConnected ? 'not-allowed' : 'pointer',
                fontSize: '14px',
                fontWeight: viewMode === 'browser' ? 'bold' : 'normal',
                transition: 'all 0.2s ease'
              }}
            >
              Browser
            </button>
            <button
              onClick={() => setViewMode('billboard')}
              disabled={isConnected}
              style={{
                flex: 1,
                padding: '12px 16px',
                backgroundColor: viewMode === 'billboard' ? '#007bff' : '#333333',
                color: viewMode === 'billboard' ? '#ffffff' : '#cccccc',
                border: 'none',
                cursor: isConnected ? 'not-allowed' : 'pointer',
                fontSize: '14px',
                fontWeight: viewMode === 'billboard' ? 'bold' : 'normal',
                transition: 'all 0.2s ease'
              }}
            >
              Billboard
            </button>
            <button
              onClick={() => setViewMode('sphere')}
              disabled={isConnected}
              style={{
                flex: 1,
                padding: '12px 16px',
                backgroundColor: viewMode === 'sphere' ? '#007bff' : '#333333',
                color: viewMode === 'sphere' ? '#ffffff' : '#cccccc',
                border: 'none',
                cursor: isConnected ? 'not-allowed' : 'pointer',
                fontSize: '14px',
                fontWeight: viewMode === 'sphere' ? 'bold' : 'normal',
                transition: 'all 0.2s ease'
              }}
            >
              Sphere
            </button>
            <button
              onClick={() => setViewMode('urdf')}
              disabled={isConnected}
              style={{
                flex: 1,
                padding: '12px 16px',
                backgroundColor: viewMode === 'urdf' ? '#007bff' : '#333333',
                color: viewMode === 'urdf' ? '#ffffff' : '#cccccc',
                border: 'none',
                cursor: isConnected ? 'not-allowed' : 'pointer',
                fontSize: '14px',
                fontWeight: viewMode === 'urdf' ? 'bold' : 'normal',
                transition: 'all 0.2s ease'
              }}
            >
              URDF
            </button>
          </div>
        </div>

        <div style={{ textAlign: 'center' }}>
          <label style={{ display: 'block', marginBottom: '5px', color: '#ffffff' }}>
            Active Cameras:
          </label>
          <div style={{ display: 'flex', gap: '10px', marginBottom: '10px', justifyContent: 'center' }}>
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
            color: '#cccccc', 
            marginBottom: '10px' 
          }}>
            Active: [{activeCameras.join(', ')}]
          </div>
        </div>

        <div style={{ display: 'flex', gap: '10px', justifyContent: 'center' }}>
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
          <div style={{ padding: '10px', backgroundColor: '#d4edda', border: '1px solid #c3e6cb', borderRadius: '4px', color: '#155724', textAlign: 'center' }}>
            Connected in {viewMode === 'vr' ? 'VR' : viewMode === 'billboard' ? 'Billboard' : viewMode === 'sphere' ? 'Sphere' : viewMode === 'urdf' ? 'URDF' : 'Browser'} mode
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
          { viewMode === 'billboard' ? (
       
              <Billboard 
                stream={streams[0] || null}
                url={url}
                hands={hands}
              />
          ) : viewMode === 'sphere' ? (
            <Sphere
              stream1={streams[0] || null}
              stream2={streams[1] || null}
              url={url}
            />
          ) : viewMode === 'urdf' ? (
            <URDFViewer
              stream={streams[0] || null}
              url={url}
              hands={hands}
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