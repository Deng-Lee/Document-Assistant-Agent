import { apiContracts } from "@/lib/generated/contracts";

export function assertContractShape(contractNames, payload) {
  const names = Array.isArray(contractNames) ? contractNames : [contractNames];
  const failures = [];
  for (const name of names) {
    const schema = apiContracts[name];
    if (!schema) {
      throw new Error(`Unknown contract: ${name}`);
    }
    const result = validateSchema(schema, payload, schema);
    if (result.ok) {
      return payload;
    }
    failures.push(`${name}: ${result.error}`);
  }
  throw new Error(`Contract mismatch: ${failures.join(" | ")}`);
}

function validateSchema(schema, value, rootSchema) {
  const resolved = resolveSchema(schema, rootSchema);
  if (resolved.anyOf) {
    return validateAlternatives(resolved.anyOf, value, rootSchema);
  }
  if (resolved.oneOf) {
    return validateAlternatives(resolved.oneOf, value, rootSchema);
  }
  if (resolved.type === "array") {
    if (!Array.isArray(value)) {
      return { ok: false, error: "expected array" };
    }
    if (resolved.items && value.length > 0) {
      return validateSchema(resolved.items, value[0], rootSchema);
    }
    return { ok: true };
  }
  if (resolved.type === "object" || resolved.properties || resolved.required) {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      return { ok: false, error: "expected object" };
    }
    for (const key of resolved.required || []) {
      if (!(key in value)) {
        return { ok: false, error: `missing required key '${key}'` };
      }
    }
    for (const [key, propertySchema] of Object.entries(resolved.properties || {})) {
      if (!(key in value) || value[key] == null) {
        continue;
      }
      const next = resolveSchema(propertySchema, rootSchema);
      if (next.type === "array" && !Array.isArray(value[key])) {
        return { ok: false, error: `key '${key}' should be an array` };
      }
      if ((next.type === "object" || next.properties || next.required) && (typeof value[key] !== "object" || Array.isArray(value[key]))) {
        return { ok: false, error: `key '${key}' should be an object` };
      }
    }
    return { ok: true };
  }
  if (resolved.type === "string" && typeof value !== "string") {
    return { ok: false, error: "expected string" };
  }
  if (resolved.type === "integer" && !Number.isInteger(value)) {
    return { ok: false, error: "expected integer" };
  }
  if (resolved.type === "number" && typeof value !== "number") {
    return { ok: false, error: "expected number" };
  }
  if (resolved.type === "boolean" && typeof value !== "boolean") {
    return { ok: false, error: "expected boolean" };
  }
  return { ok: true };
}

function validateAlternatives(options, value, rootSchema) {
  const errors = [];
  for (const option of options) {
    const result = validateSchema(option, value, rootSchema);
    if (result.ok) {
      return result;
    }
    errors.push(result.error);
  }
  return { ok: false, error: errors.join(" or ") };
}

function resolveSchema(schema, rootSchema) {
  if (!schema.$ref) {
    return schema;
  }
  const prefix = "#/$defs/";
  if (!schema.$ref.startsWith(prefix)) {
    return schema;
  }
  const key = schema.$ref.slice(prefix.length);
  return rootSchema.$defs?.[key] || schema;
}
