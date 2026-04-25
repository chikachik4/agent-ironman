import React, { useState, useEffect, useRef } from 'react';
import { Activity, Terminal, Cpu, Database, Send, CheckCircle2, Server, Network, ShieldAlert, ChevronRight, ChevronLeft } from 'lucide-react';
import ServiceMap from './components/ServiceMap';
import './index.css';

function App() {
  const [messagesByCluster, setMessagesByCluster] = useState({});
  const [metrics, setMetrics] = useState({ cpu: "0.0%", memory: "0.0 GB" });
  const [input, setInput] = useState('');
  const [ws, setWs] = useState(null);
  const [status, setStatus] = useState(null);
  const [activeCluster, setActiveCluster] = useState('vpc1');
  const [isChatOpen, setIsChatOpen] = useState(true);
  const [toastMessage, setToastMessage] = useState(null);
  const chatEndRef = useRef(null);

  const messages = messagesByCluster[activeCluster] || [];

  useEffect(() => {
    fetch('http://localhost:8000/api/status')
      .then(res => res.json())
      .then(data => setStatus(data))
      .catch(err => console.error("API Error", err));

    let socket;
    let reconnectTimer;
    let toastTimer;
    
    const connect = () => {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = window.location.port === '5173' 
                    ? 'ws://localhost:8000/ws' 
                    : `${protocol}//${window.location.host}/ws`;
                    
      socket = new WebSocket(wsUrl);
      
      socket.onopen = () => {
        console.log("WebSocket Connected");
        setWs(socket);
      };
      
      socket.onmessage = (event) => {
        const msg = JSON.parse(event.data);

        // 시스템 연결 메시지 등은 팝업(Toast)으로 처리
        if (msg.sender === "system") {
            setToastMessage(msg.text);
            clearTimeout(toastTimer);
            toastTimer = setTimeout(() => setToastMessage(null), 3000);
            return;
        }

        // 클러스터 필터링: 메트릭은 현재 선택된 클러스터의 데이터만 표시
        if (msg.type === "metric") {
            // 메트릭은 상태를 덮어쓰므로 activeCluster일 때만 업데이트
            setMetrics(prev => {
               // msg.cluster가 없거나 현재 activeCluster와 일치할 때
               if (!msg.cluster || msg.cluster === activeCluster) {
                   return { cpu: msg.cpu, memory: msg.memory };
               }
               return prev;
            });
        } else {
            // 메시지는 해당 클러스터의 배열에 누적
            const targetCluster = msg.cluster_id || 'vpc1';
            setMessagesByCluster(prev => {
                const clusterMsgs = prev[targetCluster] || [];
                return { ...prev, [targetCluster]: [...clusterMsgs, msg] };
            });
        }
      };

      socket.onclose = () => {
        console.log("WebSocket Disconnected. Reconnecting in 3s...");
        setWs(null);
        reconnectTimer = setTimeout(connect, 3000);
      };
    };
    
    connect();

    return () => {
      clearTimeout(reconnectTimer);
      if (socket) {
        socket.onclose = null;
        socket.close();
      }
    };
  }, [activeCluster]); // activeCluster가 바뀔 때 ws를 다시 연결할 필요는 없지만, 의존성 배열 유지

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = (e) => {
    e.preventDefault();
    if (!input.trim() || !ws) return;
    
    // 클러스터 컨텍스트와 함께 전송
    const payload = JSON.stringify({
        cluster_id: activeCluster,
        text: input
    });
    
    ws.send(payload);
    setInput('');
  };

  return (
    <div className="app-container">
      {/* Toast Notification */}
      {toastMessage && (
        <div className="toast-notification glass-panel">
            <span style={{color: 'var(--accent-blue)', fontWeight: 'bold', fontSize: '0.85rem'}}>[SYSTEM]</span>
            <span style={{marginLeft: '0.5rem', whiteSpace: 'pre-line', fontSize: '0.85rem'}}>{toastMessage.replace('[SYSTEM] ', '')}</span>
        </div>
      )}

      {/* 1. 좌측 패널: 네비게이션 & 클러스터 선택기 (20%) */}
      <div className="nav-panel glass-panel">
         <div className="brand-header">
            <Activity size={28} color="var(--accent-blue)" />
            <h2>Aegis-Chaos</h2>
         </div>
         <div className="cluster-list">
             <h3 className="section-title">Environments</h3>
             
             <div 
                className={`cluster-item ${activeCluster === 'vpc1' ? 'active' : ''}`}
                onClick={() => setActiveCluster('vpc1')}
             >
                 <Server size={18} />
                 <div className="cluster-info">
                     <span className="cluster-name">VPC1 EKS</span>
                     <span className="cluster-desc">Production K8s</span>
                 </div>
                 {activeCluster === 'vpc1' && <div className="active-dot"></div>}
             </div>

             <div 
                className={`cluster-item ${activeCluster === 'vpc2' ? 'active' : ''}`}
                onClick={() => setActiveCluster('vpc2')}
             >
                 <Network size={18} />
                 <div className="cluster-info">
                     <span className="cluster-name">VPC2 On-Prem</span>
                     <span className="cluster-desc">Legacy K8s</span>
                 </div>
                 {activeCluster === 'vpc2' && <div className="active-dot"></div>}
             </div>
             
             <div className="cluster-item disabled">
                 <ShieldAlert size={18} color="var(--text-muted)" />
                 <div className="cluster-info">
                     <span className="cluster-name" style={{color: 'var(--text-muted)'}}>VPC3 Hub</span>
                     <span className="cluster-desc">Management</span>
                 </div>
             </div>
         </div>
      </div>

      {/* 2. 중앙 패널: 서비스맵 및 메트릭스 (가변적) */}
      <div className="main-panel">
         <div className="map-container glass-panel">
             <div className="panel-header">
                 <h3>Service Map - {activeCluster.toUpperCase()}</h3>
                 <span className="status-badge"><CheckCircle2 size={14}/> Active Monitoring</span>
             </div>
             <div className="map-view">
                 <ServiceMap clusterId={activeCluster} />
             </div>
         </div>

         <div className="metrics-row">
            <div className="glass-panel metric-card">
                 <div className="metric-header">
                   <Cpu size={18} />
                   <h3>CPU Usage</h3>
                 </div>
                 <div className="mono-text metric-value" style={{color: 'var(--accent-blue)'}}>{metrics.cpu}</div>
            </div>
            <div className="glass-panel metric-card">
                 <div className="metric-header">
                   <Database size={18} />
                   <h3>Memory</h3>
                 </div>
                 <div className="mono-text metric-value" style={{color: 'var(--warning)'}}>{metrics.memory}</div>
            </div>
         </div>
      </div>

      {/* 3. 우측 패널: AI 에이전트 채팅 (토글형) */}
      <div className={`chat-panel-container ${isChatOpen ? 'open' : 'closed'}`}>
          <button 
             className="chat-toggle-btn" 
             onClick={() => setIsChatOpen(!isChatOpen)}
          >
              {isChatOpen ? <ChevronRight size={20}/> : <ChevronLeft size={20}/>}
          </button>
          
          <div className="chat-panel glass-panel">
            <header style={{ marginBottom: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <Terminal size={24} color="var(--accent-blue)" />
                <h2 style={{ margin: 0 }}>Agent Hub</h2>
              </div>
              <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginTop: '0.5rem' }}>Context: {activeCluster.toUpperCase()}</p>
            </header>

            <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '1rem', paddingRight: '0.5rem', marginBottom: '1rem' }}>
              {messages.map((msg, idx) => (
                <div key={idx} style={{ 
                  alignSelf: msg.sender === 'user' ? 'flex-end' : 'flex-start',
                  background: msg.sender === 'user' ? 'var(--accent-blue)' : 'rgba(255,255,255,0.05)',
                  padding: '0.75rem 1rem',
                  borderRadius: '12px',
                  borderBottomRightRadius: msg.sender === 'user' ? '2px' : '12px',
                  borderBottomLeftRadius: msg.sender !== 'user' ? '2px' : '12px',
                  maxWidth: '90%',
                  border: msg.sender !== 'user' ? '1px solid var(--border-color)' : 'none',
                  boxShadow: '0 2px 10px rgba(0,0,0,0.1)'
                }}>
                  <div style={{ fontSize: '0.75rem', opacity: 0.7, marginBottom: '0.3rem', textTransform: 'uppercase', fontWeight: 600 }}>
                    {msg.sender === 'user' ? 'You' : msg.sender}
                  </div>
                  <div style={{ lineHeight: '1.5', fontSize: '0.95rem', whiteSpace: 'pre-wrap' }}>{msg.text}</div>
                </div>
              ))}
              <div ref={chatEndRef} />
            </div>

            <form onSubmit={handleSend} style={{ display: 'flex', gap: '0.5rem' }}>
              <input 
                type="text" 
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask about this cluster..."
                style={{ 
                  flex: 1, 
                  padding: '0.9rem 1rem', 
                  borderRadius: '8px',
                  background: 'rgba(0,0,0,0.2)',
                  border: '1px solid var(--border-color)',
                  color: 'white',
                  fontFamily: 'inherit',
                  outline: 'none',
                  fontSize: '0.95rem'
                }} 
              />
              <button type="submit" style={{
                 padding: '0 1.2rem',
                 borderRadius: '8px',
                 background: 'var(--accent-blue)',
                 color: 'white',
                 border: 'none',
                 cursor: 'pointer',
                 display: 'flex',
                 alignItems: 'center',
                 justifyContent: 'center',
                 transition: 'background 0.2s'
              }}>
                <Send size={18} />
              </button>
            </form>
          </div>
      </div>
    </div>
  );
}

export default App;
