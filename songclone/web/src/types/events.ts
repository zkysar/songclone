/**
 * SSE event types matching Python Pydantic schemas.
 * Per constitution X: Events MUST be typed (TypeScript interfaces matching Python schemas).
 */

export type PhaseType = 'analysis' | 'iteration';
export type EventStatus = 'started' | 'complete';
export type StepType = 'planning' | 'execution' | 'evaluation';
export type LogLevel = 'info' | 'warn' | 'error';
export type CompleteReason = 'threshold_reached' | 'max_iterations' | 'cancelled';

export interface PhaseEvent {
  type: 'phase';
  phase: PhaseType;
  status: EventStatus;
  data?: unknown;
}

export interface IterationEvent {
  type: 'iteration';
  number: number;
  status: EventStatus;
}

export interface StepEvent {
  type: 'step';
  step: StepType;
  status: EventStatus;
  data?: unknown;
}

export interface LogEvent {
  type: 'log';
  level: LogLevel;
  message: string;
}

export interface AudioEvent {
  type: 'audio';
  iteration: number;
  path: string;
}

export interface HumanActionEvent {
  type: 'human_action_required';
  description: string;
  reason: string;
  steps: string[];
}

export interface CompleteEvent {
  type: 'complete';
  reason: CompleteReason;
  iterations: number;
}

export interface ErrorEvent {
  type: 'error';
  message: string;
  recoverable: boolean;
}

export type SSEEvent =
  | PhaseEvent
  | IterationEvent
  | StepEvent
  | LogEvent
  | AudioEvent
  | HumanActionEvent
  | CompleteEvent
  | ErrorEvent;

// Type guard functions for narrowing event types
export function isPhaseEvent(event: SSEEvent): event is PhaseEvent {
  return event.type === 'phase';
}

export function isIterationEvent(event: SSEEvent): event is IterationEvent {
  return event.type === 'iteration';
}

export function isStepEvent(event: SSEEvent): event is StepEvent {
  return event.type === 'step';
}

export function isLogEvent(event: SSEEvent): event is LogEvent {
  return event.type === 'log';
}

export function isAudioEvent(event: SSEEvent): event is AudioEvent {
  return event.type === 'audio';
}

export function isHumanActionEvent(event: SSEEvent): event is HumanActionEvent {
  return event.type === 'human_action_required';
}

export function isCompleteEvent(event: SSEEvent): event is CompleteEvent {
  return event.type === 'complete';
}

export function isErrorEvent(event: SSEEvent): event is ErrorEvent {
  return event.type === 'error';
}

// Session and iteration types matching API schemas

export interface Scores {
  timing: number;
  harmony: number;
  melody: number;
  instruments: number;
  mix: number;
  overall: number;
}

export interface FeedbackItem {
  priority: number;
  category: 'timing' | 'harmony' | 'melody' | 'instruments' | 'mix' | 'other';
  issue: string;
  suggestion: string;
}

export interface EvaluationResult {
  scores: Scores;
  total_score: number;
  max_score: number;
  feedback: FeedbackItem[];
  stop_early: boolean;
  stop_reason: string | null;
  evaluation_method: 'ai' | 'mfcc_fallback';
}

export interface InstrumentConfig {
  vst: string;
  preset: string | null;
}

export interface MixSettings {
  volume_db: number;
  pan: number;
  mute: boolean;
}

export interface FXConfig {
  plugin: string;
  preset: string | null;
  params: Record<string, unknown> | null;
}

export interface TrackPlan {
  name: string;
  role: 'vocals' | 'drums' | 'bass' | 'other' | 'master';
  instrument: InstrumentConfig;
  midi_source: string;
  midi_transform: { transpose: number; velocity_scale: number } | null;
  mix: MixSettings;
  fx: FXConfig[];
}

export interface ExecutionPlan {
  reasoning: string;
  tracks: TrackPlan[];
  master_fx: FXConfig[];
}

export interface Iteration {
  number: number;
  plan: ExecutionPlan;
  render_path: string | null;
  evaluation: EvaluationResult | null;
  started_at: string;
  completed_at: string | null;
  status: 'planning' | 'executing' | 'evaluating' | 'completed' | 'failed';
}

export interface Session {
  id: string;
  status: 'uploading' | 'analyzing' | 'iterating' | 'paused' | 'completed' | 'failed' | 'cancelled';
  original_audio_path: string | null;
  iterations: Iteration[];
  current_iteration: number;
  max_iterations: number;
  quality_threshold: number;
  error: string | null;
}
