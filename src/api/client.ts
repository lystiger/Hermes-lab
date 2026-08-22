import { LysStackApi } from './contracts';
import { MockLysStackApi } from './adapters/mockAdapter';

// Current active API client instance (defaults to MockLysStackApi, easily swappable for HttpLysStackApi)
export const lysStackApi: LysStackApi = new MockLysStackApi();

export { MockLysStackApi } from './adapters/mockAdapter';
export * from './types';
export * from './contracts';

