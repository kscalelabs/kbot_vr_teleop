import { useState } from 'react';
import VideoScreenWeb from './Video';
import SideBySideVideo from './SideBySideVideo';
import VRViewer from './URDFViewer';

type DisplayMode = 'vr' | 'browser';

function App() {
  // Utility functions for URL parameters
  const getUrlParam = (name, defaultValue) => {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get(name) || defaultValue;
  };

  const updateUrlParam = (name, value) => {
    const url = new URL(window.location.toString());
    url.searchParams.set(name, value);
    window.history.replaceState({}, '', url);
  };

  const portString = window.location.port ? `:${window.location.port}` : '';
  const [url, setUrl] = useState(`wss://${window.location.hostname}${portString}/service2`);
  const [viewMode, setViewMode] = useState<DisplayMode>("vr");
  const [isConnected, setIsConnected] = useState(false);
  const [streams, setStreams] = useState([]); // Array of MediaStreams
  const [activeCameras, setActiveCameras] = useState([0]); // Camera 0 starts active
  const [udpHost, setUdpHost] = useState(getUrlParam('udpHost', '10.33.13.62'));

  const handleConnect = async () => {
    // Update URL parameter with current UDP host value
    updateUrlParam('udpHost', udpHost);
    
    let tempViewMode: DisplayMode = 'vr';
    if (!navigator.xr) {
      tempViewMode = 'browser';
    }

    const isVRSupported = await navigator.xr.isSessionSupported('immersive-vr');
    if (!isVRSupported) {
      tempViewMode = 'browser';
    }
    setViewMode(tempViewMode);
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
      padding: '0',
      margin: '0',
      fontFamily: 'Arial, sans-serif',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      height: '100vh',
      backgroundColor: '#000000',
      color: '#ffffff',
      overflow: 'hidden'
    }}>
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100%',
        width: '100%',
        gap: '20px'
      }}>
        <h1 style={{
          textAlign: 'center',
          color: '#ffffff',
          fontSize: '48px',
          fontWeight: 'bold',
          margin: '0'
        }}>
          K-Scale
        </h1>
        {!isConnected && (
          <>
            {/* Active Camera Selection */}
            <div style={{ textAlign: 'center', width: '100%', maxWidth: '600px' }}>
              <label style={{ display: 'block', marginBottom: '15px', color: '#ffffff', fontSize: '24px' }}>
                Active Cameras:
              </label>
              <div style={{ display: 'flex', gap: '20px', marginBottom: '20px', justifyContent: 'center' }}>
                <button
                  onClick={() => toggleCamera(0)}
                  style={{
                    padding: '20px 40px',
                    backgroundColor: activeCameras.includes(0) ? '#28a745' : '#6c757d',
                    color: 'white',
                    border: 'none',
                    borderRadius: '8px',
                    cursor: 'pointer',
                    fontSize: '24px',
                    fontWeight: 'bold',
                    minWidth: '200px'
                  }}
                >
                  Camera 0 {activeCameras.includes(0) ? '✓' : ''}
                </button>
                <button
                  onClick={() => toggleCamera(1)}
                  style={{
                    padding: '20px 40px',
                    backgroundColor: activeCameras.includes(1) ? '#28a745' : '#6c757d',
                    color: 'white',
                    border: 'none',
                    borderRadius: '8px',
                    cursor: 'pointer',
                    fontSize: '24px',
                    fontWeight: 'bold',
                    minWidth: '200px'
                  }}
                >
                  Camera 1 {activeCameras.includes(1) ? '✓' : ''}
                </button>
              </div>
            </div>
            {/* UDP Host Selection */}
            <div style={{ textAlign: 'center', width: '100%', maxWidth: '600px' }}>
              <label style={{ display: 'block', marginBottom: '15px', color: '#ffffff', fontSize: '24px' }}>
                UDP Host:
              </label>
              <input 
                type="text" 
                value={udpHost} 
                onChange={(e) => setUdpHost(e.target.value)} 
                style={{ 
                  width: '100%', 
                  padding: '20px', 
                  border: '2px solid #555', 
                  borderRadius: '8px', 
                  fontSize: '24px', 
                  backgroundColor: '#222222', 
                  color: '#ffffff',
                  textAlign: 'center'
                }} 
              />
            </div>
            {/* Connect Button */}
            <div style={{ display: 'flex', gap: '20px', justifyContent: 'center', width: '100%', maxWidth: '600px' }}>
              <button
                onClick={handleConnect}
                disabled={isConnected}
                style={{
                  padding: '25px 50px',
                  backgroundColor: isConnected ? '#ccc' : 'orange',
                  color: 'white',
                  border: 'none',
                  borderRadius: '8px',
                  cursor: isConnected ? 'not-allowed' : 'pointer',
                  fontSize: '28px',
                  fontWeight: 'bold',
                  width: '100%'
                }}
              >
                Connect
              </button>
            </div>
          </>
        )}


        {isConnected && (
          <>
            <div style={{ width: '100%', height: '70vh', display: 'flex', flexDirection: 'column' }}>
              {/* Always mount VideoScreenWeb when connected - it provides the streams */}
              <VideoScreenWeb
                setStreams={setStreams}
                setIsConnected={() => { }}
                url={url}
                signalingUrl="10.33.13.62"
                activeCameras={activeCameras}
              />

              {/* Conditionally mount the view component based on selected mode */}
              {viewMode === 'vr' ? (
                <VRViewer
                  stream={streams[0] || null}
                  url={url}
                  udpHost={udpHost}
                />
              ) : (
                <SideBySideVideo
                  streams={streams}
                />
              )}
            </div>
            <button
                onClick={handleDisconnect}
                disabled={!isConnected}
                style={{
                  padding: '15px 30px',
                  backgroundColor: !isConnected ? '#ccc' : '#dc3545',
                  color: 'white',
                  border: 'none',
                  borderRadius: '8px',
                  cursor: !isConnected ? 'not-allowed' : 'pointer',
                  fontSize: '20px',
                  fontWeight: 'bold',
                  marginTop: '10px'
                }}
              >
                Disconnect
              </button>
          </>
        )}

      </div>
    </div>
  );
}

export default App;