export function canonicalResearchJson(value: unknown): string {
  function canonical(item: unknown, depth: number): string {
    if (depth > 16) throw new Error('Research evidence exceeds the fingerprint depth limit.');
    if (Array.isArray(item)) return '[' + item.map(entry => canonical(entry, depth + 1)).join(',') + ']';
    if (typeof item === 'object' && item !== null) {
      const fields = item as Record<string, unknown>;
      return '{' + Object.keys(fields).sort().map(key =>
        JSON.stringify(key) + ':' + canonical(fields[key], depth + 1)).join(',') + '}';
    }
    const scalar = JSON.stringify(item);
    if (scalar === undefined) throw new Error('Invalid research fingerprint input.');
    return scalar;
  }
  return canonical(value, 0).replace(/[\u007f-\uffff]/g, char =>
    '\\u' + char.charCodeAt(0).toString(16).padStart(4, '0'));
}

export async function researchFingerprint(value: unknown): Promise<string> {
  const checksum = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(canonicalResearchJson(value)));
  return Array.from(new Uint8Array(checksum), byte => byte.toString(16).padStart(2, '0')).join('');
}
