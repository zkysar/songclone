/**
 * PlanViewer component displays execution plan details.
 * Shows reasoning, tracks, instruments, and FX chains in a collapsible tree.
 */

import { useState } from 'react';
import type { ExecutionPlan, TrackPlan, FXConfig } from '../types/events';

interface PlanViewerProps {
  plan: ExecutionPlan;
}

interface CollapsibleSectionProps {
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}

function CollapsibleSection({ title, defaultOpen = false, children }: CollapsibleSectionProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <div className="border border-gray-600 rounded overflow-hidden">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between p-2 bg-gray-700 hover:bg-gray-600 text-left"
      >
        <span className="font-medium">{title}</span>
        <span className="text-gray-400">{isOpen ? '\u25bc' : '\u25b6'}</span>
      </button>
      {isOpen && (
        <div className="p-3 bg-gray-800/50">
          {children}
        </div>
      )}
    </div>
  );
}

function FXChainDisplay({ fx }: { fx: FXConfig[] }) {
  if (fx.length === 0) {
    return <span className="text-gray-500 text-xs">No FX</span>;
  }

  return (
    <div className="flex flex-wrap gap-1">
      {fx.map((effect, index) => (
        <span
          key={index}
          className="inline-block px-2 py-0.5 bg-purple-500/20 text-purple-300 text-xs rounded"
        >
          {effect.plugin}
          {effect.preset && ` (${effect.preset})`}
        </span>
      ))}
    </div>
  );
}

function TrackDisplay({ track, index }: { track: TrackPlan; index: number }) {
  const roleColors: Record<string, string> = {
    vocals: 'bg-pink-500/20 text-pink-300',
    drums: 'bg-orange-500/20 text-orange-300',
    bass: 'bg-blue-500/20 text-blue-300',
    other: 'bg-green-500/20 text-green-300',
    master: 'bg-yellow-500/20 text-yellow-300',
  };

  return (
    <div className="border border-gray-600 rounded p-3 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">{track.name}</span>
          <span className={`px-2 py-0.5 text-xs rounded ${roleColors[track.role] || 'bg-gray-500/20 text-gray-300'}`}>
            {track.role}
          </span>
        </div>
        <span className="text-xs text-gray-400">Track {index + 1}</span>
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        <div>
          <span className="text-gray-400">Instrument: </span>
          <span>{track.instrument.vst}</span>
          {track.instrument.preset && (
            <span className="text-gray-400"> ({track.instrument.preset})</span>
          )}
        </div>
        <div>
          <span className="text-gray-400">MIDI Source: </span>
          <span>{track.midi_source}</span>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2 text-xs">
        <div>
          <span className="text-gray-400">Volume: </span>
          <span>{track.mix.volume_db.toFixed(1)} dB</span>
        </div>
        <div>
          <span className="text-gray-400">Pan: </span>
          <span>{track.mix.pan === 0 ? 'C' : track.mix.pan > 0 ? `R${Math.abs(track.mix.pan * 100).toFixed(0)}` : `L${Math.abs(track.mix.pan * 100).toFixed(0)}`}</span>
        </div>
        <div>
          <span className="text-gray-400">Mute: </span>
          <span>{track.mix.mute ? 'Yes' : 'No'}</span>
        </div>
      </div>

      {track.midi_transform && (
        <div className="text-xs">
          <span className="text-gray-400">Transform: </span>
          <span>
            Transpose {track.midi_transform.transpose > 0 ? '+' : ''}{track.midi_transform.transpose} semitones,
            Velocity {track.midi_transform.velocity_scale.toFixed(2)}x
          </span>
        </div>
      )}

      <div>
        <span className="text-gray-400 text-xs">FX: </span>
        <FXChainDisplay fx={track.fx} />
      </div>
    </div>
  );
}

export function PlanViewer({ plan }: PlanViewerProps) {
  return (
    <div className="space-y-3">
      {/* Reasoning */}
      <div className="bg-blue-500/10 border border-blue-500/30 rounded p-3">
        <h4 className="text-sm font-medium text-blue-300 mb-1">AI Reasoning</h4>
        <p className="text-sm text-gray-300">{plan.reasoning}</p>
      </div>

      {/* Tracks */}
      <CollapsibleSection title={`Tracks (${plan.tracks.length})`} defaultOpen={true}>
        <div className="space-y-2">
          {plan.tracks.map((track, index) => (
            <TrackDisplay key={index} track={track} index={index} />
          ))}
        </div>
      </CollapsibleSection>

      {/* Master FX */}
      {plan.master_fx.length > 0 && (
        <CollapsibleSection title="Master FX Chain">
          <div className="space-y-1">
            {plan.master_fx.map((fx, index) => (
              <div key={index} className="flex items-center gap-2 text-sm">
                <span className="w-6 text-center text-gray-500">{index + 1}.</span>
                <span className="px-2 py-0.5 bg-purple-500/20 text-purple-300 rounded">
                  {fx.plugin}
                </span>
                {fx.preset && <span className="text-gray-400">Preset: {fx.preset}</span>}
                {fx.params && Object.keys(fx.params).length > 0 && (
                  <span className="text-gray-500 text-xs">
                    ({Object.entries(fx.params).map(([k, v]) => `${k}=${v}`).join(', ')})
                  </span>
                )}
              </div>
            ))}
          </div>
        </CollapsibleSection>
      )}
    </div>
  );
}
