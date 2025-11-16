/// <reference types="vite/client" />

/**
 * React hook for demo simulator using REST API polling.
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

interface SimulationStatus {
  status: 'idle' | 'running' | 'completed' | 'error';
  current_step: number | null;
  total_steps: number | null;
  last_message: SimulatorMessage | null;
  messages: SimulatorMessage[] | null;
  error: string | null;
}

export function useDemoSimulator() {
  const [isConnected, setIsConnected] = useState(false);
  const [messages, setMessages] = useState<SimulatorMessage[]>([]);
  const [error, setError] = useState<string | null>(null);
  const pollingIntervalRef = useRef<number | null>(null);
  const lastOptionsRef = useRef<SimulatorOptions>({});
  const lastMessageIdRef = useRef<string | null>(null);

  const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';

  const clearMessages = useCallback(() => {
    setMessages([]);
    setError(null);
    lastMessageIdRef.current = null;
  }, []);

  const startPolling = useCallback(() => {
    // Clear any existing polling
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
    }

    // Poll every 5 seconds
    pollingIntervalRef.current = window.setInterval(async () => {
      try {
        const response = await fetch(`${apiUrl}/system/demo/simulate/status`);
        if (!response.ok) {
          throw new Error(`Status check failed: ${response.statusText}`);
        }

        const status: SimulationStatus = await response.json();
        
        // Update connection state
        setIsConnected(status.status === 'running' || status.status === 'completed');

        // Handle errors
        if (status.error) {
          setError(status.error);
          if (status.status === 'error') {
            setIsConnected(false);
            if (pollingIntervalRef.current) {
              clearInterval(pollingIntervalRef.current);
              pollingIntervalRef.current = null;
            }
          }
        } else {
          setError(null);
        }

        // Update messages from server (use all messages if available, otherwise just last_message)
        if (status.messages && status.messages.length > 0) {
          // Use all messages from server - this ensures we get all updates
          setMessages((prev) => {
            // Only update if we have new messages
            if (status.messages!.length > prev.length) {
              console.log(`📊 Updating messages: ${prev.length} -> ${status.messages!.length}`);
              return status.messages!;
            }
            return prev;
          });
          
          // Log the latest message
          const latestMsg = status.messages[status.messages.length - 1];
          if (latestMsg) {
            if (latestMsg.type === 'simulation_start') {
              console.log('✅ Simulation started:', latestMsg);
            } else if (latestMsg.type === 'simulation_step') {
              console.log(`📈 Step ${latestMsg.step + 1}/${latestMsg.total_steps}:`, latestMsg);
            } else if (latestMsg.type === 'simulation_summary') {
              console.log('✅ Simulation completed:', latestMsg);
            } else if (latestMsg.type === 'error') {
              console.error('❌ Simulation error:', latestMsg.message);
            }
          }
        } else if (status.last_message) {
          // Fallback: if messages array is not available, use last_message
          const messageId = `${status.last_message.type}-${status.last_message.step || status.last_message.timestamp || Date.now()}`;
          
          if (messageId !== lastMessageIdRef.current) {
            lastMessageIdRef.current = messageId;
            
            setMessages((prev) => {
              // Check if this message already exists
              const exists = prev.some(msg => {
                const msgId = `${msg.type}-${msg.step || msg.timestamp || ''}`;
                return msgId === messageId;
              });
              
              if (!exists) {
                const updated = [...prev, status.last_message!];
                console.log(`📊 Total messages: ${updated.length}`);
                return updated;
              }
              
              return prev;
            });

            // Log message
            const msg = status.last_message;
            if (msg.type === 'simulation_start') {
              console.log('✅ Simulation started:', msg);
            } else if (msg.type === 'simulation_step') {
              console.log(`📈 Step ${msg.step + 1}/${msg.total_steps}:`, msg);
            } else if (msg.type === 'simulation_summary') {
              console.log('✅ Simulation completed:', msg);
            } else if (msg.type === 'error') {
              console.error('❌ Simulation error:', msg.message);
            }
          }
        }

        // Stop polling if simulation is completed or error
        if (status.status === 'completed' || status.status === 'error') {
          if (pollingIntervalRef.current) {
            clearInterval(pollingIntervalRef.current);
            pollingIntervalRef.current = null;
          }
          setIsConnected(false);
        }
      } catch (e) {
        console.error('❌ Failed to poll status:', e);
        setError(`Failed to poll status: ${e instanceof Error ? e.message : 'Unknown error'}`);
      }
    }, 5000); // Poll every 5 seconds
  }, [apiUrl]);

  const connect = useCallback(async (options: SimulatorOptions = {}) => {
    // Save options for restart
    lastOptionsRef.current = options;

    try {
      // Start simulation
      const response = await fetch(`${apiUrl}/system/demo/simulate/start`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          speed_multiplier: options.speed_multiplier || 1.0,
          start_time: options.start_time,
          end_time: options.end_time,
          data_file: options.data_file || 'Hackathon_HSY_data.xlsx',
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(errorData.detail || `Failed to start simulation: ${response.statusText}`);
      }

      const result = await response.json();
      console.log('✅ Simulation started:', result);
      
      setIsConnected(true);
      setError(null);
      clearMessages();
      
      // Poll immediately, then start regular polling
      const pollStatus = async () => {
        try {
          const response = await fetch(`${apiUrl}/system/demo/simulate/status`);
          if (!response.ok) {
            throw new Error(`Status check failed: ${response.statusText}`);
          }
          const status: SimulationStatus = await response.json();
          
          if (status.messages && status.messages.length > 0) {
            setMessages(status.messages);
            const latestMsg = status.messages[status.messages.length - 1];
            if (latestMsg) {
              const messageId = `${latestMsg.type}-${latestMsg.step || latestMsg.timestamp || Date.now()}`;
              lastMessageIdRef.current = messageId;
            }
          } else if (status.last_message) {
            const messageId = `${status.last_message.type}-${status.last_message.step || status.last_message.timestamp || Date.now()}`;
            lastMessageIdRef.current = messageId;
            setMessages([status.last_message]);
          }
        } catch (e) {
          console.error('Failed to poll immediately:', e);
        }
      };
      
      await pollStatus();
      
      // Start polling for status
      startPolling();
    } catch (e) {
      console.error('❌ Failed to start simulation:', e);
      setError(e instanceof Error ? e.message : 'Failed to start simulation');
      setIsConnected(false);
    }
  }, [apiUrl, startPolling, clearMessages]);

  const disconnect = useCallback(async () => {
    // Stop polling
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }

    // Stop simulation on server
    try {
      await fetch(`${apiUrl}/system/demo/simulate/stop`, {
        method: 'POST',
      });
    } catch (e) {
      console.error('Failed to stop simulation:', e);
    }

    setIsConnected(false);
  }, [apiUrl]);

  const restart = useCallback(() => {
    console.log('Restarting simulation...');
    // Disconnect first
    disconnect();
    // Clear messages
    clearMessages();
    // Wait a bit, then reconnect
    setTimeout(() => {
      connect(lastOptionsRef.current);
    }, 500);
  }, [connect, disconnect, clearMessages]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
      }
      disconnect();
    };
  }, [disconnect]);

  return {
    connect,
    disconnect,
    restart,
    clearMessages,
    isConnected,
    messages,
    error,
    lastMessage: messages[messages.length - 1] || null,
  };
}

