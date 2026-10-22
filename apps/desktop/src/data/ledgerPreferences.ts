export const preferenceKeys = ['toujing.userStrategies','toujing.strategy','toujing.theme','toujing.locale','toujing.welcome.skip.v1'] as const;
export function backupPreferences(storage: Pick<Storage,'getItem'>) { return Object.fromEntries(preferenceKeys.flatMap(k => { const value=storage.getItem(k); return value===null?[]:[[k,value]]; })); }
export function applyRestoredPreferences(storage: Pick<Storage,'setItem'|'removeItem'>, raw: Record<string, unknown>) {
  if (Object.keys(raw).some(k => !preferenceKeys.includes(k as typeof preferenceKeys[number]) || typeof raw[k] !== 'string')) throw new Error('无效的恢复偏好');
  for (const k of preferenceKeys) { if (typeof raw[k] === 'string') storage.setItem(k,raw[k]); else storage.removeItem(k); }
}
