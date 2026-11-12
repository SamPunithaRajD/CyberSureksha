import React, { useState, useEffect, useRef } from 'react';
import { ZoomIn, ZoomOut, Maximize, RotateCcw, ChevronLeft, ChevronRight } from 'lucide-react';

const DocumentViewer = ({ 
  fileUrl, 
  fileType, 
  fileName, 
  documentId, 
  pageCount = 1, 
  currentPage = 1, 
  onPageChange,
  detectedIssues = [], 
  selectedIssueIndex = null 
}) => {
  const [zoom, setZoom] = useState(100);
  const containerRef = useRef(null);
  const imageRef = useRef(null);

  const handleZoomIn = () => setZoom(z => Math.min(z + 20, 300));
  const handleZoomOut = () => setZoom(z => Math.max(z - 20, 50));
  const handleReset = () => setZoom(100);

  const getBboxCoords = (bbox) => {
    if (!bbox) return null;
    if (Array.isArray(bbox) && bbox.length === 4) {
      return bbox;
    }
    if (typeof bbox === 'object') {
      const x = bbox.x !== undefined ? bbox.x : bbox.left;
      const y = bbox.y !== undefined ? bbox.y : bbox.top;
      const w = bbox.width !== undefined ? bbox.width : bbox.w;
      const h = bbox.height !== undefined ? bbox.height : bbox.h;
      if (x !== undefined && y !== undefined && w !== undefined && h !== undefined) {
        return [x, y, w, h];
      }
    }
    return null;
  };

  // Reusable smooth scroll focus helper
  const scrollToSelectedIssue = () => {
    if (selectedIssueIndex === null || selectedIssueIndex === undefined || !detectedIssues.length || !containerRef.current || !imageRef.current) return;
    
    const issue = detectedIssues[selectedIssueIndex];
    const issuePage = issue.page !== undefined ? issue.page : 1;
    if (issuePage !== currentPage) return;

    const coords = getBboxCoords(issue?.bbox);
    if (!coords) return;
    
    const img = imageRef.current;
    const container = containerRef.current;
    
    const rect = img.getBoundingClientRect();
    const containerRect = container.getBoundingClientRect();
    
    if (rect.width === 0 || rect.height === 0) return;
    
    const leftPct = coords[0];
    const topPct = coords[1];
    const widthPct = coords[2];
    const heightPct = coords[3];
    
    const scrollTargetX = (leftPct + widthPct / 2) / 100 * rect.width - containerRect.width / 2;
    const scrollTargetY = (topPct + heightPct / 2) / 100 * rect.height - containerRect.height / 2;
    
    container.scrollTo({
      left: Math.max(0, scrollTargetX),
      top: Math.max(0, scrollTargetY),
      behavior: 'smooth'
    });
  };

  // Smooth-scrolling focus on selected issue on parameter changes
  useEffect(() => {
    scrollToSelectedIssue();
    const timer = setTimeout(scrollToSelectedIssue, 50);
    return () => clearTimeout(timer);
  }, [selectedIssueIndex, detectedIssues, currentPage]);

  const isPdf = fileName?.toLowerCase()?.endsWith('.pdf') || fileType?.includes('pdf') || pageCount > 1;

  // Determine current image URL
  const currentImageUrl = (isPdf && documentId)
    ? `http://localhost:8000/api/v1/documents/${documentId}/page/${currentPage}`
    : fileUrl;

  return (
    <div className="document-viewer" style={{ display: 'flex', flexDirection: 'column', height: '100%', background: '#09090b', overflow: 'hidden' }}>
      {/* Viewer Toolbar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', borderBottom: '1px solid #27272a', background: 'rgba(255,255,255,0.02)', zIndex: 5 }}>
        <div style={{ color: '#a1a1aa', fontSize: '13px', fontWeight: 500, display: 'flex', alignItems: 'center' }}>
          Original Upload: {fileName}
        </div>
        
        {/* Page controls if multi-page document */}
        {pageCount > 1 && onPageChange && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <button 
              onClick={() => onPageChange(Math.max(1, currentPage - 1))}
              disabled={currentPage <= 1}
              className="icon-btn" 
              title="Previous Page"
              style={{ opacity: currentPage <= 1 ? 0.4 : 1, cursor: currentPage <= 1 ? 'not-allowed' : 'pointer' }}
            >
              <ChevronLeft size={16} />
            </button>
            <div style={{ color: '#fff', fontSize: '13px', fontWeight: 500 }}>
              Page {currentPage} of {pageCount}
            </div>
            <button 
              onClick={() => onPageChange(Math.min(pageCount, currentPage + 1))}
              disabled={currentPage >= pageCount}
              className="icon-btn" 
              title="Next Page"
              style={{ opacity: currentPage >= pageCount ? 0.4 : 1, cursor: currentPage >= pageCount ? 'not-allowed' : 'pointer' }}
            >
              <ChevronRight size={16} />
            </button>
          </div>
        )}

        <div style={{ display: 'flex', gap: '8px' }}>
          <button onClick={handleZoomOut} className="icon-btn" title="Zoom Out"><ZoomOut size={16} /></button>
          <div style={{ color: '#fff', fontSize: '12px', minWidth: '40px', textAlign: 'center', lineHeight: '28px' }}>{zoom}%</div>
          <button onClick={handleZoomIn} className="icon-btn" title="Zoom In"><ZoomIn size={16} /></button>
          <button onClick={handleReset} className="icon-btn" title="Reset Zoom" style={{ marginLeft: '8px' }}><RotateCcw size={16} /></button>
        </div>
      </div>

      {/* Viewer Canvas Container */}
      <div 
        ref={containerRef}
        style={{ flex: 1, overflow: 'auto', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px', position: 'relative' }}
      >
        {currentImageUrl ? (
          <div style={{ 
            position: 'relative',
            transition: 'transform 0.2s ease',
            transform: `scale(${zoom / 100})`,
            transformOrigin: 'center center',
            display: 'inline-block'
          }}>
            <img 
              ref={imageRef}
              src={currentImageUrl} 
              alt="Document Preview" 
              onLoad={scrollToSelectedIssue}
              style={{ 
                maxWidth: '100%', 
                maxHeight: '80vh', 
                boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
                borderRadius: '4px',
                border: '1px solid #27272a',
                display: 'block'
              }} 
            />
            
            {/* Render Bounding Box Highlights */}
            {detectedIssues.map((issue, idx) => {
              const issuePage = issue.page !== undefined ? issue.page : 1;
              if (issuePage !== currentPage) return null;

              const coords = getBboxCoords(issue.bbox);
              if (!coords) return null;
              
              const isSelected = selectedIssueIndex === idx;
              const sev = issue.severity?.toLowerCase() || 'medium';
              const sevColor = sev === 'critical' || sev === 'high' ? '#f43f5e' : sev === 'medium' ? '#f97316' : '#eab308';
              
              return (
                <div 
                  key={idx}
                  style={{
                    position: 'absolute',
                    left: `${coords[0]}%`,
                    top: `${coords[1]}%`,
                    width: `${coords[2]}%`,
                    height: `${coords[3]}%`,
                    border: isSelected ? `2.5px solid ${sevColor}` : `1.5px dashed ${sevColor}bb`,
                    background: isSelected ? `rgba(${parseInt(sevColor.slice(1,3), 16)}, ${parseInt(sevColor.slice(3,5), 16)}, ${parseInt(sevColor.slice(5,7), 16)}, 0.12)` : 'rgba(255,255,255,0.01)',
                    borderRadius: '2px',
                    boxShadow: isSelected ? `0 0 10px ${sevColor}, inset 0 0 5px ${sevColor}80` : 'none',
                    pointerEvents: 'none',
                    transition: 'all 0.15s ease',
                    zIndex: isSelected ? 10 : 2
                  }}
                />
              );
            })}
          </div>
        ) : (
          <div style={{ color: '#52525b', textAlign: 'center' }}>
            <Maximize size={48} style={{ opacity: 0.2, marginBottom: '16px' }} />
            <div>No document preview available</div>
          </div>
        )}
      </div>
    </div>
  );
};

export default DocumentViewer;
