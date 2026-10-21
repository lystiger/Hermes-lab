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
      <div className="flex flex-col gap-4 p-4 md:p-6">
        {error && <div role="alert" className="text-[13px] text-lys-status-danger">Design boards are not available: {error}</div>}
        {manifest && (
          <>
            <div className="text-[12px] text-lys-muted">
              {manifest.decision ? `Chosen: ${manifest.decision}` : 'No direction chosen yet.'} {manifest.decision_note}
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              {manifest.directions.map((d) => {
                const active = d.id === selected;
                return (
                  <button key={d.id} type="button" aria-pressed={active} onClick={() => setSelected(d.id)}
                    className={`flex flex-col gap-2 rounded border p-2 text-left ${active ? 'border-lys-strong' : 'border-lys-subtle hover:border-lys-default'}`}>
                    <span className="h-40 overflow-hidden rounded bg-lys-surface-1">
                      <img src={`${BASE}/${d.detail}`} alt="" className="w-full object-cover object-top" loading="lazy" />
                    </span>
                    <span className="text-[13px] text-lys-primary">{d.label}</span>
                  </button>
                );
              })}
            </div>

            {current && (
              <Card as="section" label={current.label} bodyClassName="p-0">
                <div className="max-h-[78vh] overflow-auto">
                  <img src={`${BASE}/${current.detail}`} alt={`${current.label}: colour, type, states and copy`}
                    className="block h-auto w-full" />
                </div>
              </Card>
            )}

            <details className="rounded border border-lys-subtle p-3">
              <summary className="cursor-pointer text-[13px] text-lys-primary">Comparison of the three directions</summary>
              <div className="mt-3 max-h-[70vh] overflow-auto">
                <img src={`${BASE}/${manifest.sheet}`} alt="The three directions side by side" className="block h-auto w-full" />
              </div>
            </details>
          </>
        )}
      </div>
    </>
  );
};

export default DesignRoute;
