import React, { useEffect, useState } from 'react';
import { Card } from '../components/Card';
import { PageHeader } from '../components/PageHeader';

/**
 * The design boards for a project. Choosing a direction records it as a human decision in LysStack,
 * through the Hermes API. The page only shows boards and asks for the choice; it does not act on it.
 */

export interface DesignDirection {
  id: string;
  label: string;
  detail: string;
}

export interface DesignManifest {
  project: string;
  generated: string;
  sheet: string;
  contrast: string;
  directions: DesignDirection[];
  decision: string | null;
  decision_note: string;
  diagrams?: { id: string; label: string; file: string }[];
}

interface CurrentDecision {
  direction: string | null;
  label: string;
  reason: string;
  date: string | null;
}

const BASE = '/design/unigreen';
const API = import.meta.env.VITE_LYSSTACK_API_URL || 'http://localhost:8000';
const MIN_REASON = 10;

export const DesignRoute: React.FC = () => {
  const [manifest, setManifest] = useState<DesignManifest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [chosen, setChosen] = useState<CurrentDecision | null>(null);
  const [apiOk, setApiOk] = useState(false);
  const [pending, setPending] = useState<string | null>(null);
  const [reason, setReason] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  // Once a direction is chosen, the other choices stay locked until Lystiger asks to change it.
  const [changing, setChanging] = useState(false);
  const locked = !!chosen && !changing;
  // After a choice the page waits for the next design task; the boards stay one click away.
  const [showBoards, setShowBoards] = useState(false);
  const waiting = !!chosen && !changing && !showBoards;

  useEffect(() => {
    fetch(`${BASE}/manifest.json`)
      .then((r) => {
        if (!r.ok) throw new Error(`manifest not found (${r.status})`);
        return r.json() as Promise<DesignManifest>;
      })
      .then((m) => {
        setManifest(m);
        setSelected(m.directions[0]?.id ?? null);
      })
      .catch((e: Error) => setError(e.message));

    fetch(`${API}/design/unigreen/decision`)
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status));
        return r.json() as Promise<{ decision: CurrentDecision | null }>;
      })
      .then((body) => {
        setChosen(body.decision);
        setApiOk(true);
      })
      .catch(() => setApiOk(false));
  }, []);

  const current = manifest?.directions.find((d) => d.id === selected) ?? null;
  const pendingLabel = manifest?.directions.find((d) => d.id === pending)?.label ?? '';

  async function confirm() {
    if (!pending || reason.trim().length < MIN_REASON) return;
    setSaving(true);
    setSaveError(null);
    try {
      const response = await fetch(`${API}/design/unigreen/decision`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ direction: pending, reason: reason.trim() }),
      });
      if (!response.ok) {
        const body = (await response.json().catch(() => ({}))) as { detail?: string };
        throw new Error(body.detail ?? `request failed (${response.status})`);
      }
      setChosen({ direction: pending, label: pendingLabel, reason: reason.trim(), date: null });
      setPending(null);
      setReason('');
      setChanging(false);
    } catch (e) {
      setSaveError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <PageHeader title="Design" />
      <div className="flex flex-col gap-4 p-4 md:p-6">
        {error && <div role="alert" className="text-[13px] text-lys-status-danger">Design boards are not available: {error}</div>}
        {!apiOk && manifest && (
          <div className="text-[12px] text-lys-muted">The Hermes API is not reachable, so a choice cannot be recorded right now.</div>
        )}
        {manifest && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-2 text-[13px] text-lys-primary">
              {!chosen && <span>No direction chosen yet.</span>}
            </div>

            {waiting && (
              <div className="flex flex-col gap-3 rounded border border-lys-subtle p-4">
                <div className="text-[13px] text-lys-primary">Design decided. Waiting for the next design task.</div>
                <div className="flex flex-wrap gap-2">
                  <button type="button" onClick={() => setShowBoards(true)}
                    className="rounded border border-lys-subtle px-3 py-1.5 text-[12px] text-lys-primary">Show the boards</button>
                </div>
              </div>
            )}

            {!waiting && (<>
            {chosen && !changing && (
              <div>
                <div className="flex flex-wrap gap-2">
                  <button type="button" onClick={() => setShowBoards(false)}
                    className="rounded border border-lys-subtle px-3 py-1.5 text-[12px] text-lys-primary">← Back to decision</button>
                  <button type="button" onClick={() => setChanging(true)} disabled={!apiOk}
                    className="rounded border border-lys-subtle px-3 py-1.5 text-[12px] text-lys-muted disabled:opacity-40">Change decision</button>
                </div>
              </div>
            )}
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              {manifest.directions.map((d) => {
                const active = d.id === selected;
                const isChosen = chosen?.direction === d.id;
                return (
                  <div key={d.id} className={`flex flex-col gap-2 rounded border p-2 ${active ? 'border-lys-strong' : 'border-lys-subtle'}`}>
                    <button type="button" aria-pressed={active} onClick={() => setSelected(d.id)} className="flex flex-col gap-2 text-left">
                      <span className="h-40 overflow-hidden rounded bg-lys-surface-1">
                        <img src={`${BASE}/${d.detail}`} alt="" className="w-full object-cover object-top" loading="lazy" />
                      </span>
                      <span className="text-[13px] text-lys-primary">{d.label}</span>
                    </button>
                    <span className="text-[12px] text-lys-muted">{isChosen ? 'Chosen' : 'Not chosen'}</span>
                    <button type="button" disabled={!apiOk || saving || isChosen || locked}
                      onClick={() => { setPending(d.id); setReason(''); setSaveError(null); }}
                      className="w-full rounded border border-lys-subtle px-3 py-2 text-center text-[13px] text-lys-primary disabled:opacity-40">
                      Choose this direction
                    </button>
                  </div>
                );
              })}
            </div>

            {pending && (
              <Card as="section" label={`Choose ${pendingLabel}`} bodyClassName="p-4 flex flex-col gap-3">
                <p className="text-[13px] text-lys-primary">
                  This is recorded in LysStack as your decision. Write why, in at least {MIN_REASON} characters.
                </p>
                <label className="flex flex-col gap-1 text-[12px] text-lys-muted">
                  Reason
                  <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3}
                    className="rounded border border-lys-default bg-lys-surface-0 p-2 text-[13px] text-lys-primary" />
                </label>
                {saveError && <div role="alert" className="text-[12px] text-lys-status-danger">{saveError}</div>}
                <div className="flex gap-2">
                  <button type="button" onClick={() => void confirm()} disabled={saving || reason.trim().length < MIN_REASON}
                    className="rounded border border-lys-strong px-3 py-1.5 text-[13px] text-lys-primary disabled:opacity-40">
                    {saving ? 'Recording…' : 'Confirm choice'}
                  </button>
                  <button type="button" onClick={() => setPending(null)}
                    className="rounded border border-lys-subtle px-3 py-1.5 text-[13px] text-lys-muted">Cancel</button>
                </div>
              </Card>
            )}

            {current && (
              <Card as="section" label={current.label} bodyClassName="p-0">
                <div className="max-h-[78vh] overflow-auto">
                  <img src={`${BASE}/${current.detail}`} alt={`${current.label}: colour, type, states and copy`}
                    className="block h-auto w-full" />
                </div>
              </Card>
            )}

            {manifest.diagrams && manifest.diagrams.length > 0 && (
              <details className="rounded border border-lys-subtle p-3">
                <summary className="cursor-pointer text-[13px] text-lys-primary">Flows and structure</summary>
                <div className="mt-3 flex flex-col gap-4">
                  {manifest.diagrams.map((d) => (
                    <figure key={d.id} className="m-0">
                      <figcaption className="mb-2 text-[12px] text-lys-muted">{d.label}</figcaption>
                      <img src={`${BASE}/${d.file}`} alt={d.label} className="block h-auto w-full" loading="lazy" />
                    </figure>
                  ))}
                </div>
              </details>
            )}

            <details className="rounded border border-lys-subtle p-3">
              <summary className="cursor-pointer text-[13px] text-lys-primary">Comparison of the three directions</summary>
              <div className="mt-3 max-h-[70vh] overflow-auto">
                <img src={`${BASE}/${manifest.sheet}`} alt="The three directions side by side" className="block h-auto w-full" />
              </div>
            </details>
            </>)}
          </>
        )}
      </div>
    </>
  );
};

export default DesignRoute;
