import React, { useEffect } from 'react';
import {
  ReactFlow,
  MiniMap,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  MarkerType,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

export default function ServiceMap({ clusterId }) {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  useEffect(() => {
    let isMounted = true;
    
    const fetchTopology = async () => {
      try {
        const res = await fetch(`http://localhost:8000/api/topology/${clusterId}`);
        const data = await res.json();
        
        if (isMounted) {
          const formattedEdges = (data.edges || []).map(edge => ({
             ...edge,
             markerEnd: { type: MarkerType.ArrowClosed, color: edge.style?.stroke || '#94a3b8' }
          }));
          
          setNodes(data.nodes || []);
          setEdges(formattedEdges);
        }
      } catch (err) {
        console.error("Failed to fetch topology:", err);
      }
    };

    fetchTopology();
    
    // 5초마다 실시간 갱신 폴링
    const intervalId = setInterval(fetchTopology, 5000);

    return () => {
      isMounted = false;
      clearInterval(intervalId);
    };
  }, [clusterId, setNodes, setEdges]);

  return (
    <div style={{ width: '100%', height: '100%', borderRadius: '12px', overflow: 'hidden' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        fitView
        attributionPosition="bottom-left"
      >
        <Controls style={{ background: 'var(--panel-bg)', borderColor: 'var(--border-color)', fill: 'white' }} />
        <MiniMap 
            nodeStrokeColor={(n) => {
                if (n.style?.background) return n.style.background;
                return '#fff';
            }}
            nodeColor={(n) => {
                if (n.style?.background) return n.style.background;
                return '#1e293b';
            }}
            maskColor="rgba(15, 23, 42, 0.7)"
            style={{ background: 'var(--bg-dark)' }}
        />
        <Background color="var(--border-color)" gap={16} />
      </ReactFlow>
    </div>
  );
}
