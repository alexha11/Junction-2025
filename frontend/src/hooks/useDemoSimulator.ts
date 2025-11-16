/**
 * React hook for connecting to demo simulator WebSocket.
 * 
 * Usage:
 *   const { connect, disconnect, isConnected, messages } = useDemoSimulator();
 *   
 *   useEffect(() => {
 *     connect({ speed_multiplier: 10 });
 *     return () => disconnect();
 *   }, []);
 */

import { useState, useEffect, useRef, useCallback } from 'react';

interface SimulatorOptions {
  speed_multiplier?: number;
  start_time?: string;
  end_time?: string;
  data_file?: string;
}

interface SimulatorMessage {
  type: 'simulation_start' | 'simulation_step' | 'simulation_summary' | 'error';
  [key: string]: any;
}

export function useDemoSimulator() {
  const [isConnected, setIsConnected] = useState(false);
  const [messages, setMessages] = useState<SimulatorMessage[]>([]);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const connect = useCallback((options: SimulatorOptions = {}) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      console.warn('WebSocket already connected');
      return;
    }

    // Build WebSocket URL
    const baseUrl = import.meta.env.VITE_API_URL || 'ws://localhost:8000';
    const params = new URLSearchParams();
    
    if (options.speed_multiplier) {
      params.append('speed_multiplier', options.speed_multiplier.toString());
    }
    if (options.start_time) {
      params.append('start_time', options.start_time);
    }
    if (options.end_time) {
      params.append('end_time', options.end_time);
    }
    if (options.data_file) {
      params.append('data_file', options.data_file);
    }

    const url = `${baseUrl}/system/demo/simulate${params.toString() ? '?' + params.toString() : ''}`;
    
    console.log('Connecting to:', url);
    
    try {
      const ws = new WebSocket(url);
      
      ws.onopen = () => {
        console.log('WebSocket connected');
        setIsConnected(true);
        setError(null);
      };
      
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setMessages((prev) => [...prev, data]);
          
          // Handle different message types
          if (data.type === 'simulation_start') {
            console.log('Simulation started:', data);
          } else if (data.type === 'simulation_step') {
            console.log(`Step ${data.step + 1}/${data.total_steps}:`, data);
          } else if (data.type === 'simulation_summary') {
            console.log('Simulation completed:', data);
          } else if (data.type === 'error') {
            console.error('Simulation error:', data.message);
            setError(data.message);
          }
        } catch (e) {
          console.error('Failed to parse message:', e);
        }
      };
      
      ws.onerror = (event) => {
        console.error('WebSocket error:', event);
        setError('WebSocket connection error');
      };
      
      ws.onclose = () => {
        console.log('WebSocket disconnected');
        setIsConnected(false);
        wsRef.current = null;
      };
      
      wsRef.current = ws;
    } catch (e) {
      console.error('Failed to create WebSocket:', e);
      setError('Failed to connect');
    }
  }, []);

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
      setIsConnected(false);
    }
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  return {
    connect,
    disconnect,
    isConnected,
    messages,
    error,
    lastMessage: messages[messages.length - 1] || null,
  };
}

