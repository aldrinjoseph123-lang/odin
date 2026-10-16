// The password rule as the person reads it. The length is the admin's policy
// (Settings › Sign-in & security) and arrives with /api/session; 12 is only the
// floor the server enforces (review P2-38).
export const MIN_PASSWORD = 12
export const passwordRule = (min = MIN_PASSWORD) => `At least ${min} characters, mixing letters with numbers or symbols.`
