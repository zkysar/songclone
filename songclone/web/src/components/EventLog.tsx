/**
 * Display SSE log events in a scrollable list.
 */

import { useEffect, useRef } from 'react';
import type { SSEEvent, LogEvent } from '../types/events';
import { isLogEvent } from '../types/events';

interface EventLogProps {
  events: SSEEvent[];
  maxHeight?: string;
}

export function EventLog({ events, maxHeight = '300px' }: EventLogProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [events]);

  const logEvents = events.filter(isLogEvent);

  const getLevelColor = (level: LogEvent['level']) => {
    switch (level) {
      case 'info':
        return 'text-blue-400';
      case 'warn':
        return 'text-yellow-400';
      case 'error':
        return 'text-red-400';
      default:
        return 'text-gray-400';
    }
  };

  const getLevelIcon = (level: LogEvent['level']) => {
    switch (level) {
      case 'info':
        return 'ℹ';
      case 'warn':
        return '⚠';
      case 'error':
        return '✗';
      default:
        return '•';
    }
  };

  if (logEvents.length === 0) {
    return (
      <div className="bg-gray-800 rounded-lg p-4 text-gray-500 text-center">
        No events yet...
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="bg-gray-800 rounded-lg p-4 overflow-y-auto font-mono text-sm"
      style={{ maxHeight }}
    >
      {logEvents.map((event, index) => (
        <div key={index} className="flex items-start gap-2 mb-1">
          <span className={`${getLevelColor(event.level)} flex-shrink-0`}>
            {getLevelIcon(event.level)}
          </span>
          <span className="text-gray-300">{event.message}</span>
        </div>
      ))}
    </div>
  );
}
