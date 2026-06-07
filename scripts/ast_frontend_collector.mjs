#!/usr/bin/env node
import { createHash } from "node:crypto";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { extname, relative } from "node:path";

const requireFromFrontend = createRequire(new URL("../web/frontend/package.json", import.meta.url));
const ts = requireFromFrontend("typescript");
const { parse: parseVue } = requireFromFrontend("@vue/compiler-sfc");
const postcss = requireFromFrontend("postcss");

const input = JSON.parse(readStdin() || "{}");
const projectRoot = input.projectRoot || process.cwd();
const files = Array.isArray(input.files) ? input.files : [];
const units = [];
const errors = [];

for (const file of files) {
  try {
    const source = readFileSync(file, "utf8");
    const ext = extname(file);
    if ([".ts", ".tsx", ".js", ".mjs"].includes(ext)) {
      collectScript(file, source, ext === ".js" || ext === ".mjs" ? "javascript" : "typescript");
    } else if (ext === ".vue") {
      collectVue(file, source);
    } else if (ext === ".css") {
      collectCss(file, source, "css");
    }
  } catch (error) {
    errors.push({ path: rel(file), language: languageFor(file), message: String(error?.message || error), line: 0 });
  }
}

process.stdout.write(JSON.stringify({ units, errors }));

function collectVue(file, source) {
  const parsed = parseVue(source, { filename: file });
  const descriptor = parsed.descriptor;
  const script = descriptor.scriptSetup || descriptor.script;
  if (script?.content) {
    collectScript(file, script.content, "vue", script.loc?.start?.line || 1);
  }
  if (descriptor.template?.content) {
    const tokens = templateTokens(descriptor.template.content);
    if (tokens.length) {
      pushUnit({
        file,
        language: "vue",
        kind: "template",
        name: "template",
        startLine: descriptor.template.loc?.start?.line || 1,
        endLine: descriptor.template.loc?.end?.line || descriptor.template.loc?.start?.line || 1,
        tokens,
        calls: [],
        imports: [],
        exports: [],
      });
    }
  }
  for (const style of descriptor.styles || []) {
    collectCss(file, style.content, "css", style.loc?.start?.line || 1);
  }
}

function collectScript(file, source, language, lineOffset = 1) {
  const sourceFile = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
  const imports = [];
  const exports = [];

  sourceFile.forEachChild(node => {
    if (ts.isImportDeclaration(node) && node.moduleSpecifier?.text) imports.push(String(node.moduleSpecifier.text));
    if (hasExportModifier(node) && node.name?.text) exports.push(String(node.name.text));
  });

  visit(sourceFile);

  function visit(node) {
    if (isScriptUnit(node)) {
      const tokens = scriptTokens(node);
      const { startLine, endLine } = lineRange(sourceFile, node, lineOffset);
      pushUnit({
        file,
        language,
        kind: scriptKind(node),
        name: node.name?.text || inferredName(node) || "<anonymous>",
        startLine,
        endLine,
        tokens,
        calls: callNames(node),
        imports,
        exports,
      });
    }
    ts.forEachChild(node, visit);
  }
}

function collectCss(file, source, language, lineOffset = 1) {
  const root = postcss.parse(source, { from: file });
  root.walkRules(rule => {
    const tokens = [];
    rule.walkDecls(decl => {
      tokens.push(`decl:${decl.prop}:${normalizeCssValue(decl.value)}`);
    });
    if (!tokens.length) return;
    const start = (rule.source?.start?.line || 1) + lineOffset - 1;
    const end = (rule.source?.end?.line || rule.source?.start?.line || 1) + lineOffset - 1;
    pushUnit({
      file,
      language,
      kind: "style-rule",
      name: rule.selector || "<style-rule>",
      startLine: start,
      endLine: end,
      tokens: tokens.sort(),
      calls: [],
      imports: [],
      exports: [],
    });
  });
}

function isScriptUnit(node) {
  return (
    ts.isFunctionDeclaration(node) ||
    ts.isMethodDeclaration(node) ||
    ts.isClassDeclaration(node) ||
    ts.isArrowFunction(node) ||
    ts.isFunctionExpression(node)
  );
}

function scriptKind(node) {
  if (ts.isClassDeclaration(node)) return "class";
  if (ts.isMethodDeclaration(node)) return "method";
  return "ts-function";
}

function scriptTokens(node) {
  const tokens = [];
  function walk(child) {
    if (ts.isIdentifier(child)) {
      tokens.push("Identifier");
    } else if (ts.isStringLiteral(child) || ts.isNumericLiteral(child) || child.kind === ts.SyntaxKind.TrueKeyword || child.kind === ts.SyntaxKind.FalseKeyword) {
      tokens.push(`Literal:${ts.SyntaxKind[child.kind]}`);
    } else {
      tokens.push(ts.SyntaxKind[child.kind] || String(child.kind));
    }
    ts.forEachChild(child, walk);
  }
  walk(node);
  return tokens;
}

function callNames(node) {
  const names = new Set();
  function walk(child) {
    if (ts.isCallExpression(child)) names.add(exprName(child.expression));
    ts.forEachChild(child, walk);
  }
  walk(node);
  return [...names].filter(Boolean).sort();
}

function exprName(node) {
  if (ts.isIdentifier(node)) return node.text;
  if (ts.isPropertyAccessExpression(node)) return `${exprName(node.expression)}.${node.name.text}`;
  return "";
}

function inferredName(node) {
  const parent = node.parent;
  if (parent && ts.isVariableDeclaration(parent) && ts.isIdentifier(parent.name)) return parent.name.text;
  if (parent && ts.isPropertyAssignment(parent) && ts.isIdentifier(parent.name)) return parent.name.text;
  return "";
}

function hasExportModifier(node) {
  return Boolean(node.modifiers?.some(modifier => modifier.kind === ts.SyntaxKind.ExportKeyword));
}

function lineRange(sourceFile, node, lineOffset) {
  const start = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile));
  const end = sourceFile.getLineAndCharacterOfPosition(node.getEnd());
  return {
    startLine: start.line + lineOffset,
    endLine: end.line + lineOffset,
  };
}

function templateTokens(template) {
  const tokens = [];
  for (const match of template.matchAll(/<\/?([A-Za-z][\w-]*)|(@[\w:-]+)|(:[\w:-]+)|(v-[\w:-]+)/g)) {
    tokens.push(match[1] ? `tag:${match[1]}` : `binding:${match[0]}`);
  }
  return tokens;
}

function normalizeCssValue(value) {
  return String(value).replace(/#[0-9a-fA-F]{3,8}/g, "<color>").replace(/\b\d+(\.\d+)?(px|rem|em|%)?\b/g, "<num>");
}

function pushUnit({ file, language, kind, name, startLine, endLine, tokens, calls, imports, exports }) {
  const unitTokens = tokens.filter(Boolean);
  const path = rel(file);
  units.push({
    id: `unit:${path}:${startLine}:${name}`,
    path,
    language,
    kind,
    name,
    start_line: startLine,
    end_line: endLine,
    node_count: unitTokens.length,
    fingerprint: sha1(unitTokens.join("\n")),
    tokens: unitTokens,
    calls,
    imports,
    exports,
  });
}

function rel(file) {
  return relative(projectRoot, file).replaceAll("\\", "/");
}

function languageFor(file) {
  const ext = extname(file);
  if (ext === ".vue") return "vue";
  if (ext === ".css") return "css";
  if (ext === ".js" || ext === ".mjs") return "javascript";
  return "typescript";
}

function sha1(value) {
  return createHash("sha1").update(value).digest("hex");
}

function readStdin() {
  return readFileSync(0, "utf8");
}
