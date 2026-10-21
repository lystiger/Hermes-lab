import React, { useEffect, useState } from 'react';
import { Card } from '../components/Card';
import { PageHeader } from '../components/PageHeader';

/** The design boards for a project, read from the manifest the design build writes. Read-only. */

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
}

const BASE = '/design/unigreen';

export const DesignRoute: React.FC = () => {
  const [manifest, setManifest] = useState<DesignManifest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

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
  }, []);

  const current = manifest?.directions.find((d) => d.id === selected) ?? null;

  return (
    <>
      <PageHeader title="Design" subtitle={manifest ? `${manifest.project} · generated ${manifest.generated}` : 'Unigreen'} />
      <div className="flex flex-col gap-4 p-6">
        {error && <div role="alert" className="text-[13px] text-lys-status-danger">Design boards are not available: {error}</div>}
        {manifest && (
          <>
            <Card as="section" label="Decision" bodyClassName="p-4 flex flex-col gap-2">
              <div className="text-[13px] text-lys-primary">
                {manifest.decision ? `Chosen: ${manifest.decision}` : 'No direction chosen yet'}
              </div>
              <div className="text-[12px] text-lys-muted">{manifest.decision_note}</div>
            </Card>

            <div role="tablist" aria-label="Directions" className="flex flex-wrap gap-2">
              {manifest.directions.map((d) => (
                <button key={d.id} role="tab" aria-selected={d.id === selected} type="button"
                  onClick={() => setSelected(d.id)}
                  className={`rounded border px-3 py-1.5 text-[13px] ${d.id === selected ? 'border-lys-strong text-lys-primary' : 'border-lys-subtle text-lys-muted'}`}>
                  {d.label}
                </button>
              ))}
            </div>

            {current && (
              <Card as="section" label={current.label} bodyClassName="p-0 overflow-auto">
                <img src={`${BASE}/${current.detail}`} alt={`${current.label}: colour, type, states and copy`}
                  className="block h-auto w-full max-w-[1280px]" />
              </Card>
            )}

            <Card as="section" label="Comparison" bodyClassName="p-0 overflow-auto">
              <img src={`${BASE}/${manifest.sheet}`} alt="The three directions side by side" className="block h-auto w-full max-w-[1720px]" />
            </Card>
          </>
        )}
      </div>
    </>
  );
};

export default DesignRoute;
