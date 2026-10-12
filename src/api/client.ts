import { HermesApi } from './contracts';
import { MockHermesApi } from './adapters/mockAdapter';
import { HttpHermesApi } from './adapters/httpAdapter';

const apiUrl = import.meta.env.VITE_LYSSTACK_API_URL;

export const isRealApiMode = Boolean(apiUrl);

export const hermesApi: HermesApi = isRealApiMode
  ? new HttpHermesApi(apiUrl)
  : new MockHermesApi();

export function createApiClient(customUrl?: string): HermesApi {
  if (customUrl) {
    return new HttpHermesApi(customUrl);
  }
  return isRealApiMode ? new HttpHermesApi(apiUrl) : new MockHermesApi();
}
