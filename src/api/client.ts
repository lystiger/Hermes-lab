import { LysStackApi } from './contracts';
import { MockLysStackApi } from './adapters/mockAdapter';
import { HttpLysStackApi } from './adapters/httpAdapter';

const apiUrl = import.meta.env.VITE_LYSSTACK_API_URL;

export const isRealApiMode = Boolean(apiUrl);

export const lysStackApi: LysStackApi = isRealApiMode
  ? new HttpLysStackApi(apiUrl)
  : new MockLysStackApi();

export function createApiClient(customUrl?: string): LysStackApi {
  if (customUrl) {
    return new HttpLysStackApi(customUrl);
  }
  return isRealApiMode ? new HttpLysStackApi(apiUrl) : new MockLysStackApi();
}
