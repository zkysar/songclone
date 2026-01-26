/**
 * SSE subscription hook for real-time session events.
 * Per constitution X: Auto-play MUST be disabled by default.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import type { SSEEvent } from '../types/events';

interface UseSSEOptions {
  sessionId: string | null;
  onEvent?: (event: SSEEvent) => void;
  reconnectDelay?: number;
  maxReconnectAttempts?: number;
}

interface UseSSEResult {
  events: SSEEvent[];
  isConnected: boolean;
  error: string | null;
  clearEvents: () => void;
}

export function useSSE({
  sessionId,
  onEvent,
  reconnectDelay = 1000,
  maxReconnectAttempts = 5,
}: UseSSEOptions): UseSSEResult {
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<number | null>(null);

  const clearEvents = useCallback(() => {
    setEvents([]);
  }, []);

  useEffect(() => {
    if (!sessionId) {
      return;
    }

    const connect = () => {
      const url = `/api/sessions/${sessionId}/events`;
      const eventSource = new EventSource(url);
      eventSourceRef.current = eventSource;

      eventSource.onopen = () => {
        setIsConnected(true);
        setError(null);
        reconnectAttemptsRef.current = 0;
      };

      eventSource.onerror = () => {
        setIsConnected(false);
        eventSource.close();

        if (reconnectAttemptsRef.current < maxReconnectAttempts) {
          reconnectAttemptsRef.current += 1;
          const delay = reconnectDelay * Math.pow(2, reconnectAttemptsRef.current - 1);

          reconnectTimeoutRef.current = window.setTimeout(() => {
            connect();
          }, delay);
        } else {
          setError('Connection lost. Please refresh the page.');
        }
      };

      const handleEvent = (e: MessageEvent) => {
        try {
          const event: SSEEvent = JSON.parse(e.data);
          setEvents((prev) => [...prev, event]);
          onEvent?.(event);
        } catch (err) {
          console.error('Failed to parse SSE event:', err);
        }
      };

      eventSource.addEventListener('phase', handleEvent);
      eventSource.addEventListener('iteration', handleEvent);
      eventSource.addEventListener('step', handleEvent);
      eventSource.addEventListener('log', handleEvent);
      eventSource.addEventListener('audio', handleEvent);
      eventSource.addEventListener('human_action_required', handleEvent);
      eventSource.addEventListener('complete', handleEvent);
      eventSource.addEventListener('error', handleEvent);
    };

    connect();

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
    };
  }, [sessionId, onEvent, reconnectDelay, maxReconnectAttempts]);

  return {
    events,
    isConnected,
    error,
    clearEvents,
  };
}
