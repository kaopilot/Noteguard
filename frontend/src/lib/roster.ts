// Demonstrator login only: the synthetic staff roster (names and roles, no clinical content) is read
// at build time from the repo fixture. Production identity comes from SSO / SMART launch.
import clinic from '../../../fixtures/encounters/clinic.json';
import type { Staff } from '../api/types';

export const ROSTER: readonly Staff[] = clinic.staff as Staff[];
