import React, { useState, useEffect, useRef } from 'react';
import { Activity, Terminal, Cpu, Database, Send, CheckCircle2 } from 'lucide-react';
import './index.css';

function App() {
  const [messages, setMessages] = useState([]);
  const [metrics, setMetrics] = useState({ cpu: "0.0%", memory: "0.0 GB" });
  const [input, setInput] = useState('');
  const [ws, setWs] = useState(null);
  const [status, setStatus] = useState(null);
  const chatEndRef = useRef(null);

  useEffect(() => {
    // 1. 상태 가져오기
    fetch('http://localhost:8000/api/status')
      .then(res => res.json())
      .then(data => setStatus(data))
      .catch(err => console.error("API Error", err));

    let socket;
    let reconnectTimer;
    
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
        if (msg.type === "metric") {
            setMetrics({ cpu: msg.cpu, memory: msg.memory });
        } else {
            setMessages(prev => [...prev, msg]);
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
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = (e) => {
    e.preventDefault();
    if (!input.trim() || !ws) return;
    ws.send(input);
    setInput('');
  };

  return (
    <div className="app-container">
      {/* 좌측 60%: 인프라 모니터링 패널 */}
      <div className="metrics-panel glass-panel">
        <header style={{ marginBottom: '1.5rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <Activity size={24} color="var(--accent-blue)" />
            <h2 style={{ margin: 0 }}>Aegis-Chaos Observability</h2>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-muted)', fontSize: '0.9rem', marginTop: '0.75rem' }}>
            <CheckCircle2 size={16} color="var(--success)" />
            <span>System Status: <span style={{ color: 'var(--text-main)', fontWeight: 500 }}>Active</span></span>
            {status && <span style={{ marginLeft: '0.5rem', paddingLeft: '0.5rem', borderLeft: '1px solid var(--border-color)' }}>Env: <span className="mono-text" style={{ color: 'var(--text-main)' }}>{status.environment.toUpperCase()}</span></span>}
          </div>
        </header>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', flex: 1 }}>
           <div className="glass-panel" style={{ padding: '1.2rem', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
             <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-muted)', marginBottom: '1rem' }}>
               <Cpu size={18} />
               <h3 style={{ margin: 0, fontSize: '0.9rem', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.05em' }}>CPU Usage (Target)</h3>
             </div>
             <div className="mono-text" style={{fontSize: '2.5rem', fontWeight: 700, color: 'var(--accent-blue)'}}>{metrics.cpu}</div>
          </div>
          <div className="glass-panel" style={{ padding: '1.2rem', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
             <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-muted)', marginBottom: '1rem' }}>
               <Database size={18} />
               <h3 style={{ margin: 0, fontSize: '0.9rem', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Memory (Target)</h3>
             </div>
             <div className="mono-text" style={{fontSize: '2.5rem', fontWeight: 700, color: 'var(--warning)'}}>{metrics.memory}</div>
          </div>
          <div className="glass-panel" style={{ padding: '1rem', gridColumn: '1 / -1', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', borderStyle: 'dashed' }}>
             [여기에 Grafana 시계열 차트 또는 OpenSearch 대시보드가 임베딩됩니다]
          </div>
        </div>
      </div>

      {/* 우측 40%: AI 에이전트 채팅 패널 */}
      <div className="chat-panel glass-panel">
        <header style={{ marginBottom: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <Terminal size={24} color="var(--accent-blue)" />
            <h2 style={{ margin: 0 }}>Agent Command Center</h2>
          </div>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginTop: '0.5rem' }}>Secure shell & orchestration interface</p>
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
              maxWidth: '85%',
              border: msg.sender !== 'user' ? '1px solid var(--border-color)' : 'none',
              boxShadow: '0 2px 10px rgba(0,0,0,0.1)'
            }}>
              <div style={{ fontSize: '0.75rem', opacity: 0.7, marginBottom: '0.3rem', textTransform: 'uppercase', fontWeight: 600 }}>
                {msg.sender === 'user' ? 'You' : msg.sender}
              </div>
              <div style={{ lineHeight: '1.5', fontSize: '0.95rem' }}>{msg.text}</div>
            </div>
          ))}
          <div ref={chatEndRef} />
        </div>

        <form onSubmit={handleSend} style={{ display: 'flex', gap: '0.5rem' }}>
          <input 
            type="text" 
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="명령어 입력 (예: VPC1 타겟 상태 확인해줘)"
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
  );
}

export default App;
