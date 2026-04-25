import React, { useMemo } from 'react';
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

// 더미 노드 데이터
const initialNodes = [
  {
    id: 'ingress',
    type: 'input',
    data: { label: 'Ingress Controller' },
    position: { x: 250, y: 0 },
    style: { background: '#1e293b', color: '#fff', border: '1px solid #3b82f6', borderRadius: '8px' },
  },
  {
    id: 'api-gateway',
    data: { label: 'API Gateway' },
    position: { x: 250, y: 100 },
    style: { background: '#1e293b', color: '#fff', border: '1px solid #3b82f6', borderRadius: '8px' },
  },
  {
    id: 'auth-service',
    data: { label: 'Auth Service' },
    position: { x: 100, y: 200 },
    style: { background: '#1e293b', color: '#fff', border: '1px solid #10b981', borderRadius: '8px' },
  },
  {
    id: 'payment-service',
    data: { label: 'Payment Service\n(CPU 85% Warning)' },
    position: { x: 400, y: 200 },
    style: { background: '#1e293b', color: '#fff', border: '1px solid #ef4444', borderRadius: '8px', boxShadow: '0 0 10px rgba(239, 68, 68, 0.5)' },
  },
  {
    id: 'user-db',
    type: 'output',
    data: { label: 'User Database' },
    position: { x: 100, y: 300 },
    style: { background: '#1e293b', color: '#fff', border: '1px solid #8b5cf6', borderRadius: '8px' },
  },
  {
    id: 'payment-db',
    type: 'output',
    data: { label: 'Payment Database' },
    position: { x: 400, y: 300 },
    style: { background: '#1e293b', color: '#fff', border: '1px solid #8b5cf6', borderRadius: '8px' },
  }
];

// 더미 엣지 데이터
const initialEdges = [
  { id: 'e1-2', source: 'ingress', target: 'api-gateway', animated: true, style: { stroke: '#94a3b8' }, markerEnd: { type: MarkerType.ArrowClosed, color: '#94a3b8' } },
  { id: 'e2-3', source: 'api-gateway', target: 'auth-service', animated: true, style: { stroke: '#10b981' }, markerEnd: { type: MarkerType.ArrowClosed, color: '#10b981' } },
  { id: 'e2-4', source: 'api-gateway', target: 'payment-service', animated: true, style: { stroke: '#ef4444' }, markerEnd: { type: MarkerType.ArrowClosed, color: '#ef4444' } },
  { id: 'e3-5', source: 'auth-service', target: 'user-db', style: { stroke: '#94a3b8' }, markerEnd: { type: MarkerType.ArrowClosed, color: '#94a3b8' } },
  { id: 'e4-6', source: 'payment-service', target: 'payment-db', style: { stroke: '#94a3b8' }, markerEnd: { type: MarkerType.ArrowClosed, color: '#94a3b8' } },
];

export default function ServiceMap({ clusterId }) {
  // 나중에 clusterId에 따라 노드/엣지 데이터를 동적으로 로드하는 로직이 여기에 추가됩니다.
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // 클러스터 아이디 변경 시 더미 데이터를 조금씩 바꿔주는 효과 (데모용)
  React.useEffect(() => {
    if (clusterId === 'vpc2') {
       setNodes((nds) => nds.map((node) => {
         if (node.id === 'payment-service') {
           return { ...node, data: { label: 'Payment Service\n(Normal)' }, style: { ...node.style, border: '1px solid #10b981', boxShadow: 'none' } };
         }
         return node;
       }));
       setEdges((eds) => eds.map((edge) => {
         if (edge.id === 'e2-4') {
             return { ...edge, style: { stroke: '#10b981' }, markerEnd: { type: MarkerType.ArrowClosed, color: '#10b981' } };
         }
         return edge;
       }));
    } else {
       // vpc1
       setNodes(initialNodes);
       setEdges(initialEdges);
    }
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
