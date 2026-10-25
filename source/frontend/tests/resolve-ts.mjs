// Mirror tsconfig's @/* alias for Node's native TypeScript unit-test runner.
import { existsSync } from "node:fs";

export async function resolve(specifier, context, nextResolve) {
  let url;
  if (specifier.startsWith("@/")) {
    url = new URL("../" + specifier.slice(2), import.meta.url);
  } else if (specifier.startsWith(".") && context.parentURL) {
    url = new URL(specifier, context.parentURL);
  }
  if (url) {
    const source = new URL(url.href + ".ts");
    if (existsSync(source)) return nextResolve(source.href, context);
  }
  return nextResolve(specifier, context);
}
