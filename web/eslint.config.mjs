import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // Vendored from shadcn/ui and shadcn-chatbot-kit, kept as upstream ships them. They predate the
    // React Compiler lint rules; our own code under src/components/sdlc and src/app is linted.
    "src/components/ui/**",
    "src/hooks/**",
    "src/lib/audio-utils.ts",
  ]),
]);

export default eslintConfig;
