import '@testing-library/jest-dom';
import { afterEach } from 'vitest';
import { resetInFlightRequests } from './api/inFlight';

afterEach(() => {
  resetInFlightRequests();
});
