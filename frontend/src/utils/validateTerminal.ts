import type { TerminalState } from "../types";
import contract from "../contracts/terminal.schema.json";

type Schema = {
  $ref?: string; $defs?: Record<string, Schema>; anyOf?: Schema[];
  const?: unknown; enum?: unknown[]; type?: string; format?: string; minLength?: number;
  properties?: Record<string, Schema>; required?: string[];
  additionalProperties?: boolean | Schema; items?: Schema;
  minimum?: number; maximum?: number; exclusiveMinimum?: number; exclusiveMaximum?: number;
};
const schema = contract as Schema;
const decimal = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/;
const timestamp = /^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/;
function check(value: unknown, rule: Schema, path: string): void {
  const fail = (): never => { throw new Error(`Invalid terminal field: ${path}`); };
  if (rule.$ref) return check(value, schema.$defs![rule.$ref.split("/").at(-1)!], path);
  if (rule.anyOf) {
    for (const candidate of rule.anyOf) {
      try { check(value, candidate, path); return; } catch { /* try next wire variant */ }
    }
    return fail();
  }
  if ("const" in rule && value !== rule.const) fail();
  if (rule.enum && !rule.enum.includes(value)) fail();
  switch (rule.type) {
    case "null": if (value !== null) fail(); break;
    case "boolean": if (typeof value !== "boolean") fail(); break;
    case "string":
      if (typeof value !== "string") return fail();
      if (rule.minLength !== undefined && value.length < rule.minLength) fail();
      if (rule.format === "sha256" && !/^[0-9a-f]{64}$/.test(value)) fail();
      if (rule.format === "decimal" && (!decimal.test(value) || !Number.isFinite(Number(value)))) fail();
      if (rule.format === "decimal") {
        const numeric = Number(value);
        if ((rule.minimum !== undefined && numeric < rule.minimum) ||
            (rule.maximum !== undefined && numeric > rule.maximum) ||
            (rule.exclusiveMinimum !== undefined && numeric <= rule.exclusiveMinimum) ||
            (rule.exclusiveMaximum !== undefined && numeric >= rule.exclusiveMaximum)) fail();
      }
      if (rule.format === "date-time") {
        if (!timestamp.test(value) || !Number.isFinite(Date.parse(value))) fail();
        const day = value.slice(0, 10), local = new Date(`${day}T00:00:00Z`);
        if (!Number.isFinite(local.getTime()) || local.toISOString().slice(0, 10) !== day) fail();
      }
      break;
    case "integer": case "number":
      if (typeof value !== "number" || !Number.isFinite(value) ||
          (rule.type === "integer" && !Number.isSafeInteger(value))) return fail();
      if ((rule.minimum !== undefined && value < rule.minimum) ||
          (rule.maximum !== undefined && value > rule.maximum) ||
          (rule.exclusiveMinimum !== undefined && value <= rule.exclusiveMinimum) ||
          (rule.exclusiveMaximum !== undefined && value >= rule.exclusiveMaximum)) fail();
      break;
    case "array":
      if (!Array.isArray(value)) return fail();
      value.forEach((item, i) => check(item, rule.items!, `${path}[${i}]`));
      break;
    case "object": {
      if (!value || typeof value !== "object" || Array.isArray(value)) return fail();
      const object = value as Record<string, unknown>;
      for (const key of rule.required ?? []) if (!Object.hasOwn(object, key)) fail();
      for (const [key, item] of Object.entries(object)) {
        const field = rule.properties?.[key];
        if (field) check(item, field, `${path}.${key}`);
        else if (rule.additionalProperties === false) fail();
        else if (typeof rule.additionalProperties === "object") check(item, rule.additionalProperties, `${path}.${key}`);
      }
      break;
    }
  }
}
export function validateTerminal(value: unknown): TerminalState {
  check(value, schema, "terminal");
  const frame = value as TerminalState;
  if (!frame.process_id || !frame.session_id) throw new Error("Invalid terminal identity");
  return frame;
}
