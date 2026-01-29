/**
 * Vertical timeline component for SSE events.
 * Features: color-coded events, filtering, search, expandable details, auto-scroll.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { SSEEvent } from '../types/events';
import {
  isReaperOperationEvent,
  isToolCallEvent,
  isToolResponseEvent,
  isAgentThinkingEvent,
  isIterationEvent,
  isPhaseEvent,
  isStepEvent,
  isLogEvent,
  isAudioEvent,
  isHumanActionEvent,
  isCompleteEvent,
  isErrorEvent,
  isAgentResponseEvent,
} from '../types/events';

interface TimelineProps {
  events: SSEEvent[];
}

type EventTypeFilter =
  | 'all'
  | 'phase'
  | 'iteration'
  | 'step'
  | 'log'
  | 'audio'
  | 'reaper_operation'
  | 'tool_call'
  | 'tool_response'
  | 'agent_thinking'
  | 'agent_response'
  | 'human_action_required'
  | 'complete'
  | 'error';

const EVENT_COLORS: Record<string, { bg: string; border: string; icon: string }> = {
  phase: { bg: 'bg-purple-500/20', border: 'border-purple-500', icon: 'text-purple-400' },
  iteration: { bg: 'bg-blue-500/20', border: 'border-blue-500', icon: 'text-blue-400' },
  step: { bg: 'bg-cyan-500/20', border: 'border-cyan-500', icon: 'text-cyan-400' },
  log: { bg: 'bg-gray-500/20', border: 'border-gray-500', icon: 'text-gray-400' },
  audio: { bg: 'bg-green-500/20', border: 'border-green-500', icon: 'text-green-400' },
  reaper_operation: { bg: 'bg-orange-500/20', border: 'border-orange-500', icon: 'text-orange-400' },
  tool_call: { bg: 'bg-yellow-500/20', border: 'border-yellow-500', icon: 'text-yellow-400' },
  tool_response: { bg: 'bg-lime-500/20', border: 'border-lime-500', icon: 'text-lime-400' },
  agent_thinking: { bg: 'bg-indigo-500/20', border: 'border-indigo-500', icon: 'text-indigo-400' },
  agent_response: { bg: 'bg-pink-500/20', border: 'border-pink-500', icon: 'text-pink-400' },
  human_action_required: { bg: 'bg-amber-500/20', border: 'border-amber-500', icon: 'text-amber-400' },
  complete: { bg: 'bg-emerald-500/20', border: 'border-emerald-500', icon: 'text-emerald-400' },
  error: { bg: 'bg-red-500/20', border: 'border-red-500', icon: 'text-red-400' },
};

const EVENT_ICONS: Record<string, string> = {
  phase: '\u25B6',
  iteration: '\u21BB',
  step: '\u2192',
  log: '\u2139',
  audio: '\u266B',
  reaper_operation: '\u2699',
  tool_call: '\u2B95',
  tool_response: '\u2B90',
  agent_thinking: '\u{1F4AD}',
  agent_response: '\u{1F4AC}',
  human_action_required: '\u26A0',
  complete: '\u2714',
  error: '\u2718',
};

function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp);
  const hours = date.getHours().toString().padStart(2, '0');
  const minutes = date.getMinutes().toString().padStart(2, '0');
  const seconds = date.getSeconds().toString().padStart(2, '0');
  const ms = date.getMilliseconds().toString().padStart(3, '0');
  return `${hours}:${minutes}:${seconds}.${ms}`;
}

function formatDuration(startTimestamp: string, endTimestamp: string): string {
  const start = new Date(startTimestamp).getTime();
  const end = new Date(endTimestamp).getTime();
  const diff = end - start;

  if (diff < 1000) {
    return `${diff}ms`;
  } else if (diff < 60000) {
    return `${(diff / 1000).toFixed(1)}s`;
  } else {
    const mins = Math.floor(diff / 60000);
    const secs = ((diff % 60000) / 1000).toFixed(0);
    return `${mins}m ${secs}s`;
  }
}

function getEventSummary(event: SSEEvent): string {
  if (isPhaseEvent(event)) {
    return `Phase: ${event.phase} (${event.status})`;
  } else if (isIterationEvent(event)) {
    return `Iteration ${event.number} ${event.status}`;
  } else if (isStepEvent(event)) {
    return `Step: ${event.step} (${event.status})`;
  } else if (isLogEvent(event)) {
    return event.message;
  } else if (isAudioEvent(event)) {
    return `Audio ready: iteration ${event.iteration}`;
  } else if (isReaperOperationEvent(event)) {
    const op = event.operation.replace(/_/g, ' ');
    return `REAPER: ${op} (${event.status})`;
  } else if (isToolCallEvent(event)) {
    return `Tool call: ${event.tool}`;
  } else if (isToolResponseEvent(event)) {
    const duration = event.duration_ms ? ` (${event.duration_ms}ms)` : '';
    return `Tool response: ${event.tool} - ${event.status}${duration}`;
  } else if (isAgentThinkingEvent(event)) {
    return `${event.agent}: thinking...`;
  } else if (isAgentResponseEvent(event)) {
    const preview = event.content.slice(0, 50);
    return preview + (event.content.length > 50 ? '...' : '');
  } else if (isHumanActionEvent(event)) {
    return `Action required: ${event.description}`;
  } else if (isCompleteEvent(event)) {
    return `Complete: ${event.reason} (${event.iterations} iterations)`;
  } else if (isErrorEvent(event)) {
    return `Error: ${event.message}`;
  }
  return 'Unknown event';
}

function getEventDetails(event: SSEEvent): Record<string, unknown> | null {
  if (isReaperOperationEvent(event)) {
    return {
      operation: event.operation,
      status: event.status,
      ...(event.details || {}),
      ...(event.error ? { error: event.error } : {}),
    };
  } else if (isToolCallEvent(event)) {
    return {
      tool: event.tool,
      call_id: event.call_id,
      args: event.args,
    };
  } else if (isToolResponseEvent(event)) {
    return {
      tool: event.tool,
      call_id: event.call_id,
      status: event.status,
      duration_ms: event.duration_ms,
      result: event.result,
    };
  } else if (isAgentThinkingEvent(event)) {
    return {
      agent: event.agent,
      content: event.content,
    };
  } else if (isPhaseEvent(event) && event.data) {
    return { data: event.data };
  } else if (isStepEvent(event) && event.data) {
    return { data: event.data };
  } else if (isHumanActionEvent(event)) {
    return {
      description: event.description,
      reason: event.reason,
      steps: event.steps,
    };
  }
  return null;
}

function hasExpandableDetails(event: SSEEvent): boolean {
  return (
    isReaperOperationEvent(event) ||
    isToolCallEvent(event) ||
    isToolResponseEvent(event) ||
    isAgentThinkingEvent(event) ||
    (isPhaseEvent(event) && !!event.data) ||
    (isStepEvent(event) && !!event.data) ||
    isHumanActionEvent(event)
  );
}

function getCurrentIteration(events: SSEEvent[]): number {
  for (let i = events.length - 1; i >= 0; i--) {
    const event = events[i];
    if (isIterationEvent(event)) {
      return event.number;
    }
  }
  return 0;
}

interface EventItemProps {
  event: SSEEvent;
  index: number;
  prevEvent: SSEEvent | null;
  isExpanded: boolean;
  onToggle: () => void;
}

function EventItem({ event, prevEvent, isExpanded, onToggle }: EventItemProps) {
  const colors = EVENT_COLORS[event.type] || EVENT_COLORS.log;
  const icon = EVENT_ICONS[event.type] || '\u2022';
  const summary = getEventSummary(event);
  const details = getEventDetails(event);
  const expandable = hasExpandableDetails(event);

  const duration = prevEvent
    ? formatDuration(prevEvent.timestamp, event.timestamp)
    : null;

  return (
    <div className="relative pl-8 pb-4 last:pb-0">
      {/* Connecting line */}
      <div className="absolute left-3 top-0 bottom-0 w-px bg-gray-700" />

      {/* Event dot */}
      <div
        className={`absolute left-1 top-1 w-5 h-5 rounded-full flex items-center justify-center text-xs ${colors.bg} ${colors.border} border`}
      >
        <span className={colors.icon}>{icon}</span>
      </div>

      {/* Duration indicator */}
      {duration && (
        <div className="absolute left-8 -top-2 text-xs text-gray-500">
          +{duration}
        </div>
      )}

      {/* Event content */}
      <div
        className={`rounded-lg p-3 ${colors.bg} border ${colors.border} ${
          expandable ? 'cursor-pointer hover:opacity-80' : ''
        }`}
        onClick={expandable ? onToggle : undefined}
      >
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-gray-200 truncate">
              {summary}
            </div>
            <div className="text-xs text-gray-500 mt-1">
              {formatTimestamp(event.timestamp)}
            </div>
          </div>
          {expandable && (
            <div className="text-gray-500 text-xs">
              {isExpanded ? '\u25BC' : '\u25B6'}
            </div>
          )}
        </div>

        {/* Expanded details */}
        {isExpanded && details && (
          <div className="mt-3 pt-3 border-t border-gray-700">
            <pre className="text-xs text-gray-400 overflow-x-auto whitespace-pre-wrap">
              {JSON.stringify(details, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}

export function Timeline({ events }: TimelineProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [activeFilters, setActiveFilters] = useState<Set<EventTypeFilter>>(
    new Set(['all'])
  );
  const [expandedEvents, setExpandedEvents] = useState<Set<number>>(new Set());
  const [autoScroll, setAutoScroll] = useState(true);
  const [userScrolled, setUserScrolled] = useState(false);

  const containerRef = useRef<HTMLDivElement>(null);
  const scrollTimeoutRef = useRef<number | null>(null);

  const currentIteration = useMemo(() => getCurrentIteration(events), [events]);

  const filteredEvents = useMemo(() => {
    return events.filter((event) => {
      if (!activeFilters.has('all') && !activeFilters.has(event.type as EventTypeFilter)) {
        return false;
      }

      if (searchQuery) {
        const searchLower = searchQuery.toLowerCase();
        const summary = getEventSummary(event).toLowerCase();
        const details = getEventDetails(event);
        const detailsStr = details ? JSON.stringify(details).toLowerCase() : '';

        return summary.includes(searchLower) || detailsStr.includes(searchLower);
      }

      return true;
    });
  }, [events, activeFilters, searchQuery]);

  const groupedEvents = useMemo(() => {
    const groups: { iteration: number; events: SSEEvent[] }[] = [];
    let currentGroup: { iteration: number; events: SSEEvent[] } | null = null;

    for (const event of filteredEvents) {
      if (isIterationEvent(event) && event.status === 'started') {
        if (currentGroup) {
          groups.push(currentGroup);
        }
        currentGroup = { iteration: event.number, events: [event] };
      } else if (currentGroup) {
        currentGroup.events.push(event);
      } else {
        if (!groups.length || groups[0].iteration !== 0) {
          groups.unshift({ iteration: 0, events: [] });
        }
        groups[0].events.push(event);
      }
    }

    if (currentGroup) {
      groups.push(currentGroup);
    }

    return groups;
  }, [filteredEvents]);

  const handleToggleExpand = useCallback((index: number) => {
    setExpandedEvents((prev) => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  }, []);

  const handleFilterToggle = useCallback((filter: EventTypeFilter) => {
    setActiveFilters((prev) => {
      const next = new Set(prev);
      if (filter === 'all') {
        return new Set(['all']);
      }
      next.delete('all');
      if (next.has(filter)) {
        next.delete(filter);
        if (next.size === 0) {
          return new Set(['all']);
        }
      } else {
        next.add(filter);
      }
      return next;
    });
  }, []);

  const handleScroll = useCallback(() => {
    if (scrollTimeoutRef.current) {
      clearTimeout(scrollTimeoutRef.current);
    }

    setUserScrolled(true);
    setAutoScroll(false);

    scrollTimeoutRef.current = window.setTimeout(() => {
      const container = containerRef.current;
      if (container) {
        const isAtBottom =
          container.scrollHeight - container.scrollTop - container.clientHeight < 50;
        if (isAtBottom) {
          setAutoScroll(true);
          setUserScrolled(false);
        }
      }
    }, 150);
  }, []);

  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [filteredEvents, autoScroll]);

  useEffect(() => {
    return () => {
      if (scrollTimeoutRef.current) {
        clearTimeout(scrollTimeoutRef.current);
      }
    };
  }, []);

  const filterOptions: { type: EventTypeFilter; label: string }[] = [
    { type: 'all', label: 'All' },
    { type: 'phase', label: 'Phase' },
    { type: 'iteration', label: 'Iteration' },
    { type: 'step', label: 'Step' },
    { type: 'reaper_operation', label: 'REAPER' },
    { type: 'tool_call', label: 'Tool Call' },
    { type: 'tool_response', label: 'Tool Response' },
    { type: 'agent_thinking', label: 'Thinking' },
    { type: 'log', label: 'Log' },
    { type: 'error', label: 'Error' },
  ];

  return (
    <div className="flex flex-col h-full">
      {/* Search and filters */}
      <div className="mb-4 space-y-3">
        <input
          type="text"
          placeholder="Search events..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-sm text-white placeholder-gray-400 focus:outline-none focus:border-blue-500"
        />

        <div className="flex flex-wrap gap-2">
          {filterOptions.map(({ type, label }) => {
            const isActive = activeFilters.has(type);
            const colors = EVENT_COLORS[type] || EVENT_COLORS.log;
            return (
              <button
                key={type}
                onClick={() => handleFilterToggle(type)}
                className={`px-2 py-1 text-xs rounded transition-colors ${
                  isActive
                    ? `${colors.bg} ${colors.border} border text-white`
                    : 'bg-gray-700 border border-gray-600 text-gray-400 hover:bg-gray-600'
                }`}
              >
                {label}
              </button>
            );
          })}
        </div>

        {/* Auto-scroll indicator */}
        <div className="flex items-center justify-between text-xs text-gray-500">
          <span>
            {filteredEvents.length} events
            {currentIteration > 0 && ` | Iteration ${currentIteration}`}
          </span>
          <button
            onClick={() => {
              setAutoScroll(!autoScroll);
              setUserScrolled(false);
            }}
            className={`px-2 py-1 rounded ${
              autoScroll
                ? 'bg-green-500/20 text-green-400'
                : 'bg-gray-700 text-gray-400'
            }`}
          >
            {autoScroll ? 'Auto-scroll ON' : 'Auto-scroll OFF'}
          </button>
        </div>
      </div>

      {/* Timeline content */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto min-h-0 max-h-96"
      >
        {groupedEvents.length === 0 ? (
          <div className="text-center text-gray-500 py-8">No events to display</div>
        ) : (
          groupedEvents.map((group) => (
            <div key={group.iteration} className="mb-6 last:mb-0">
              {group.iteration > 0 && (
                <div className="sticky top-0 z-10 bg-gray-800 py-2 mb-2 border-b border-gray-700">
                  <span className="text-sm font-semibold text-blue-400">
                    Iteration {group.iteration}
                  </span>
                </div>
              )}
              {group.events.map((event, idx) => {
                const globalIndex = events.indexOf(event);
                const prevEvent = idx > 0 ? group.events[idx - 1] : null;
                return (
                  <EventItem
                    key={globalIndex}
                    event={event}
                    index={globalIndex}
                    prevEvent={prevEvent}
                    isExpanded={expandedEvents.has(globalIndex)}
                    onToggle={() => handleToggleExpand(globalIndex)}
                  />
                );
              })}
            </div>
          ))
        )}

        {/* Scroll pause indicator */}
        {userScrolled && !autoScroll && (
          <div className="sticky bottom-0 bg-gray-800/90 text-center py-2 text-xs text-amber-400">
            Scroll paused - scroll to bottom to resume
          </div>
        )}
      </div>
    </div>
  );
}
