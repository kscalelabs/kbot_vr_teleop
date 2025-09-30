import React, { useRef, useEffect, useState } from 'react';

export interface SideBySideVideoProps {
  streams: MediaStream[];
}

export default function SideBySideVideo({ streams }: SideBySideVideoProps) {
  const videoRefs = useRef<(HTMLVideoElement | null)[]>([]);
  const [status, setStatus] = useState('');
  const [videosReady, setVideosReady] = useState(false);
  const [resolutions, setResolutions] = useState<string[]>([]);
  
  useEffect(() => {
    // Update video elements when streams change
    streams.forEach((stream, index) => {
      if (videoRefs.current[index] && stream) {
        const video = videoRefs.current[index];
        if (video) {
          video.srcObject = stream;
          
          // Add resolution logging
          const logResolution = () => {
            if (video.videoWidth > 0 && video.videoHeight > 0) {
              const resolution = `${video.videoWidth} x ${video.videoHeight}`;
              console.log(`📺 Stream ${index} Resolution: ${resolution}`);
              setResolutions(prev => {
                const newResolutions = [...prev];
                newResolutions[index] = resolution;
                return newResolutions;
              });
              video.removeEventListener('loadedmetadata', logResolution);
            }
          };
          
          video.addEventListener('loadedmetadata', logResolution);
          video.play().catch(console.warn);
        }
      }
    });
  }, [streams]);

  const updateStatus = (msg: string) => {
    console.log(msg);
    setStatus(msg);
  };

  const startSideBySide = async () => {
    updateStatus('Starting side-by-side video...');
    
    if (streams.length === 0) {
      updateStatus('No streams available');
      return;
    }

    try {
      updateStatus('Videos loaded, starting playback...');
      updateStatus(`Videos playing in side-by-side mode - ${streams.length} stream(s)`);
      setVideosReady(true);
    } catch (err) {
      updateStatus(`Video error: ${err}`);
      console.error('Video play failed', err);
      return;
    }
  };

  return (
    <div style={{ padding: '20px', fontFamily: 'Arial, sans-serif' }}>
      
      {status && (
        <div style={{ 
          padding: '10px', 
          backgroundColor: '#f8f9fa', 
          border: '1px solid #dee2e6', 
          borderRadius: '5px',
          marginBottom: '10px',
          fontSize: '14px'
        }}>
          Status: {status}
        </div>
      )}
      
      <div style={{ 
        display: 'flex', 
        gap: '20px', 
        justifyContent: 'center',
        flexWrap: 'wrap'
      }}>
        {streams.map((stream, index) => {
          const colors = ['#007bff', '#28a745', '#dc3545', '#ffc107', '#6f42c1'];
          return (
            <div key={index} style={{ textAlign: 'center' }}>
              <h3 style={{ margin: '0 0 5px 0', color: '#333' }}>Camera {index}</h3>
              {resolutions[index] && (
                <div style={{ 
                  fontSize: '12px', 
                  color: '#666', 
                  marginBottom: '5px',
                  fontWeight: 'bold'
                }}>
                  📺 {resolutions[index]}
                </div>
              )}
              <video
                ref={(el) => {
                  if (videoRefs.current) {
                    videoRefs.current[index] = el;
                  }
                }}
                crossOrigin="anonymous"
                style={{ 
                  width: '400px',
                  height: '300px',
                  border: `2px solid ${colors[index % colors.length]}`,
                  borderRadius: '8px',
                  backgroundColor: '#000'
                }}
                muted
                playsInline
                controls
              />
            </div>
          );
        })}
        
        {streams.length === 0 && (
          <div style={{ 
            textAlign: 'center', 
            color: '#666', 
            fontSize: '18px',
            padding: '40px'
          }}>
            No camera streams available. Select cameras and connect.
          </div>
        )}
      </div>
    </div>
  );
}
