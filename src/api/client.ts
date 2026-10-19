import { HermesApi } from './contracts';
import { MockHermesApi } from './adapters/mockAdapter';
import { HttpHermesApi } from './adapters/httpAdapter';

/** Real Hermes runtime API, used unless mock data is requested explicitly (rule 2). */
export const DEFAULT_HERMES_URL = 'http://localhost:8000';

const apiUrl = import.meta.env.VITE_LYSSTACK_API_URL || DEFAULT_HERMES_URL;

/** Mock fixtures are opt-in only: `VITE_LYSCONTROL_MOCK=1`. The UI then shows a persistent MOCK DATA banner. */
export const isMockMode = import.meta.env.VITE_LYSCONTROL_MOCK === '1';

/** True whenever data comes from Hermes over HTTP. Kept under its original name for existing call sites. */
export const isRealApiMode = !isMockMode;

export const hermesApi: HermesApi = isMockMode
  ? new MockHermesApi()
  : new HttpHermesApi(apiUrl);

export function createApiClient(customUrl?: string): HermesApi {
  if (customUrl) {
    return new HttpHermesApi(customUrl);
  }
  return isMockMode ? new MockHermesApi() : new HttpHermesApi(apiUrl);
}
