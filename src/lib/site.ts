import fs from "node:fs";
import path from "node:path";
import MarkdownIt from "markdown-it";
import type { Token } from "markdown-it";

export class BuildError extends Error {}

export interface Post {
  id: string;
  source: string;
  fields: Record<string, string>;
  body: string;
  firstText: string;
  type: "short" | "medium" | "long";
  written: string;
  title: string;
}

export interface Share {
  post: string;
  where: string;
  url: string;
  at: string;
  line: number;
}

export interface Tagging {
  tag: string;
  at: string;
  why: string;
}

export interface LinkEvent {
  action: "created" | "reason-changed" | "removed";
  at: string;
  why: string;
}

export interface Link {
  source: string;
  line: number;
  id: string;
  fromId: string;
  toId: string;
  anchor: string;
  events: LinkEvent[];
  active: boolean;
  createdAt: string;
  currentReason: string;
}

export type PatchOp = "replace" | "insert-before" | "insert-after" | "delete";

export interface Patch {
  source: string;
  line: number;
  id: string;
  postId: string;
  at: string;
  why: string;
  op: PatchOp;
  anchor: string;
  text?: string;
}

export interface PatchRegion {
  id: string;
  history: Patch[];
  deleted: boolean;
}

export interface BodyLinkMarkup {
  token: string;
  href: string;
  label: string;
  number: number;
}

export interface PostBodyMarkup {
  html: string;
  links: BodyLinkMarkup[];
  regions: PatchRegion[];
}

type BodyUnit = {
  kind: "body";
  text: string;
  owner?: Patch;
  history: Patch[];
};

type DeletedUnit = {
  kind: "deleted";
  owner: Patch;
  history: Patch[];
};

type Unit = BodyUnit | DeletedUnit;

export class PatchState {
  units: Unit[];
  patches: Patch[] = [];

  constructor(post: Post) {
    this.units = Array.from(post.body, (text) => ({ kind: "body", text, history: [] }));
  }

  get body(): string {
    return this.units.filter((unit): unit is BodyUnit => unit.kind === "body").map((unit) => unit.text).join("");
  }

  get hasPatches(): boolean {
    return this.patches.length > 0;
  }

  private history(units: Unit[], patch: Patch): Patch[] {
    const found = new Map<string, Patch>();
    for (const unit of units) for (const previous of unit.history) found.set(previous.id, previous);
    if (!found.has(patch.id)) found.set(patch.id, patch);
    return [...found.values()].sort((a, b) => a.at.localeCompare(b.at) || a.id.localeCompare(b.id));
  }

  apply(patch: Patch): void {
    const visibleIndices: number[] = [];
    for (const [index, unit] of this.units.entries()) if (unit.kind === "body") visibleIndices.push(index);
    const positions = occurrences(this.body, patch.anchor);
    if (positions.length !== 1 || !patch.anchor) throw new BuildError(patch.source);
    const anchorStart = codePointOffset(this.body, positions[0]);
    const anchorEnd = anchorStart + Array.from(patch.anchor).length;
    if (patch.op === "replace" || patch.op === "delete") validatePatchSourceOverlaps(this.body, anchorStart, anchorEnd, patch);
    const nodeStart = visibleIndices[anchorStart];
    const nodeEnd = visibleIndices[anchorEnd - 1] + 1;
    const replaced = this.units.slice(nodeStart, nodeEnd);
    const history = this.history(replaced, patch);

    if (patch.op === "delete") {
      this.units.splice(nodeStart, nodeEnd - nodeStart, { kind: "deleted", owner: patch, history });
    } else if (patch.op === "replace") {
      this.units.splice(
        nodeStart,
        nodeEnd - nodeStart,
        ...Array.from(patch.text || "", (text) => ({ kind: "body", text, owner: patch, history })),
      );
    } else {
      const inserted = Array.from(patch.text || "", (text) => ({ kind: "body" as const, text, owner: patch, history: [patch] }));
      const insertion = patch.op === "insert-before" ? nodeStart : nodeEnd;
      this.units.splice(insertion, 0, ...inserted);
    }
    this.patches.push(patch);
  }

  markedBody(): { body: string; regions: PatchRegion[] } {
    const pieces: string[] = [];
    const regions: PatchRegion[] = [];
    let index = 0;
    let unitIndex = 0;
    while (unitIndex < this.units.length) {
      const unit = this.units[unitIndex];
      if (unit.kind === "deleted") {
        regions.push({ id: `patch-region-${index}`, history: unit.history, deleted: true });
        pieces.push(patchStart(index), patchEnd(index));
        index += 1;
        unitIndex += 1;
        continue;
      }
      if (!unit.owner) {
        pieces.push(unit.text);
        unitIndex += 1;
        continue;
      }
      const owner = unit.owner;
      const grouped: BodyUnit[] = [];
      while (unitIndex < this.units.length) {
        const current = this.units[unitIndex];
        if (current.kind !== "body" || current.owner?.id !== owner.id) break;
        grouped.push(current);
        unitIndex += 1;
      }
      if (!grouped.length) continue;
      regions.push({ id: `patch-region-${index}`, history: grouped[0].history, deleted: false });
      pieces.push(patchStart(index), ...grouped.map((item) => item.text), patchEnd(index));
      index += 1;
    }
    return { body: pieces.join(""), regions };
  }

  patchRanges(): Array<[number, number, Patch]> {
    const ranges: Array<[number, number, Patch]> = [];
    let visibleIndex = 0;
    let unitIndex = 0;
    while (unitIndex < this.units.length) {
      const unit = this.units[unitIndex];
      if (unit.kind === "deleted") {
        unitIndex += 1;
        continue;
      }
      if (!unit.owner) {
        visibleIndex += 1;
        unitIndex += 1;
        continue;
      }
      const owner = unit.owner;
      const start = visibleIndex;
      while (unitIndex < this.units.length) {
        const current = this.units[unitIndex];
        if (current.kind !== "body" || current.owner?.id !== owner.id) break;
        visibleIndex += 1;
        unitIndex += 1;
      }
      ranges.push([start, visibleIndex, owner]);
    }
    return ranges;
  }
}

export interface SiteData {
  contentRoot: string;
  aboutPath: string;
  aboutBody: string;
  posts: Post[];
  links: Link[];
  patchStates: Map<string, PatchState>;
  shares: Map<string, Share[]>;
  taggings: Map<string, Tagging[]>;
}

export const SHARE_PLACES: Record<string, [string, string]> = {
  x: ["X", "x.svg"],
  threads: ["Threads", "threads.svg"],
  linkedin: ["LinkedIn", "linkedin.png"],
  substack: ["Substack", "substack.png"],
  bluesky: ["Bluesky", "bluesky.svg"],
};

const TABLES = new Set(["links.jsonl", "patches.jsonl", "shares.jsonl", "tags.jsonl"]);
const WRITTEN_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/;
const RECORD_ID_RE = /^[a-z0-9-]+$/;
const PATCH_MARKER_RE = /\u0000guin-patch-(?:start|end)-\d+\u0000/g;

const markdown = new MarkdownIt("commonmark", { html: false, linkify: false, breaks: true });
markdown.enable(["table", "strikethrough"]);

function rootPath(): string {
  return path.resolve(process.env.GUIN_CONTENT_ROOT || path.join(process.cwd(), "content"));
}

function fail(file: string): never {
  throw new BuildError(file);
}

function readUtf8(file: string): string {
  try {
    return fs.readFileSync(file, "utf8");
  } catch {
    return fail(file);
  }
}

function htmlEscape(value: string, quote = false): string {
  let escaped = value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  if (quote) escaped = escaped.replace(/"/g, "&quot;");
  return escaped;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseWritten(value: string, file: string): string {
  if (!WRITTEN_RE.test(value)) fail(file);
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime()) || parsed.toISOString().replace(".000Z", "Z") !== value) fail(file);
  return value;
}

function timeId(written: string): string {
  return `${written.slice(0, 4)}${written.slice(5, 7)}${written.slice(8, 10)}-${written.slice(11, 13)}${written.slice(14, 16)}${written.slice(17, 19)}`;
}

function allFiles(directory: string): string[] {
  let entries: fs.Dirent[];
  try {
    entries = fs.readdirSync(directory, { withFileTypes: true });
  } catch (error: any) {
    if (error?.code === "ENOENT") return [];
    throw error;
  }
  return entries.flatMap((entry) => {
    const full = path.join(directory, entry.name);
    return entry.isDirectory() ? allFiles(full) : entry.isFile() ? [full] : [];
  });
}

function imageWidth(alt: string, file: string): { alt: string; width?: number } {
  const match = /^(.*)\|(\d+)$/s.exec(alt);
  if (!match) return { alt };
  const width = Number(match[2]);
  if (width < 1 || width > 9999) fail(file);
  return { alt: match[1], width };
}

function imageSource(root: string, source: string, file: string): void {
  const parts = source.split("/");
  if (source.startsWith("/") || parts.length < 2 || parts[0] !== "images" || parts.some((part) => !part || part === "." || part === "..")) fail(file);
  try {
    if (!fs.statSync(path.join(root, ...parts)).isFile()) fail(file);
  } catch {
    fail(file);
  }
}

function occurrences(value: string, needle: string): number[] {
  if (!needle) return [];
  const positions: number[] = [];
  let start = 0;
  while (true) {
    const position = value.indexOf(needle, start);
    if (position < 0) return positions;
    positions.push(position);
    start = position + 1;
  }
}

function codePointOffset(value: string, codeUnitOffset: number): number {
  return Array.from(value.slice(0, codeUnitOffset)).length;
}

function patchStart(index: number): string {
  return `\u0000guin-patch-start-${index}\u0000`;
}

function patchEnd(index: number): string {
  return `\u0000guin-patch-end-${index}\u0000`;
}

interface Row {
  file: string;
  line: number;
  value: Record<string, unknown>;
}

function tableRows(root: string, name: string): Row[] {
  const file = path.join(root, name);
  if (!fs.existsSync(file)) return [];
  const rows: Row[] = [];
  for (const [index, line] of readUtf8(file).split("\n").entries()) {
    if (!line.trim()) continue;
    try {
      const value: unknown = JSON.parse(line);
      if (!isObject(value)) fail(`${file}:${index + 1}`);
      rows.push({ file: `${file}:${index + 1}`, line: index + 1, value });
    } catch (error) {
      if (error instanceof BuildError) throw error;
      fail(`${file}:${index + 1}`);
    }
  }
  return rows;
}

function stringValue(value: unknown, file: string): string {
  if (typeof value !== "string") fail(file);
  return value;
}

function validateBodyCharacters(value: string, file: string): void {
  if (/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/.test(value)) fail(file);
}

function parsePost(file: string, root: string): Post {
  const lines = readUtf8(file).split(/\r\n?|\n/);
  const separator = lines.findIndex((line) => line.trim() === "");
  if (separator < 0) fail(file);
  const fields: Record<string, string> = {};
  for (const line of lines.slice(0, separator)) {
    const colon = line.indexOf(":");
    if (colon < 0) fail(file);
    const key = line.slice(0, colon).trim();
    const value = line.slice(colon + 1).trim();
    if (!["written", "type", "title"].includes(key) || key in fields) fail(file);
    fields[key] = value;
  }
  if (!("written" in fields) || !("type" in fields)) fail(file);
  parseWritten(fields.written, file);
  if (!( ["short", "medium", "long"] as string[]).includes(fields.type)) fail(file);
  if (fields.type === "short" && "title" in fields) fail(file);
  const body = lines.slice(separator + 1).join("\n");
  if (!body.trim()) fail(file);
  validateBodyCharacters(body, file);
  const id = path.basename(file, path.extname(file));
  if (id !== timeId(fields.written)) fail(file);
  return { id, source: file, fields, body, firstText: "", type: fields.type as Post["type"], written: fields.written, title: fields.title || "" };
}

function parsePosts(root: string): Post[] {
  const posts: Post[] = [];
  const ids = new Set<string>();
  for (const file of allFiles(root).sort()) {
    const relative = path.relative(root, file).split(path.sep);
    const relativeName = relative.join("/");
    if (relative[0] === "images" || relativeName === "about.md" || TABLES.has(relativeName)) continue;
    const post = parsePost(file, root);
    if (ids.has(post.id)) fail(file);
    ids.add(post.id);
    posts.push(post);
  }
  return posts;
}

function parsePatches(root: string, posts: Post[]): Patch[] {
  const knownPosts = new Set(posts.map((post) => post.id));
  const patches: Patch[] = [];
  const ids = new Set<string>();
  for (const row of tableRows(root, "patches.jsonl")) {
    const common = ["id", "post", "at", "why", "op", "anchor"];
    if (!common.every((key) => key in row.value)) fail(row.file);
    const op = stringValue(row.value.op, row.file);
    if (!["replace", "insert-before", "insert-after", "delete"].includes(op)) fail(row.file);
    const expected = new Set([...common, ...(op === "delete" ? [] : ["text"])]);
    if (Object.keys(row.value).sort().join("|") !== [...expected].sort().join("|")) fail(row.file);
    const id = stringValue(row.value.id, row.file);
    const postId = stringValue(row.value.post, row.file);
    const at = stringValue(row.value.at, row.file);
    const why = stringValue(row.value.why, row.file);
    const anchor = stringValue(row.value.anchor, row.file);
    if (!RECORD_ID_RE.test(id) || ids.has(id) || !knownPosts.has(postId)) fail(row.file);
    ids.add(id);
    parseWritten(at, row.file);
    const text = op === "delete" ? undefined : stringValue(row.value.text, row.file);
    if (text !== undefined) validateBodyCharacters(text, row.file);
    patches.push({ source: row.file, line: row.line, id, postId, at, why, op: op as PatchOp, anchor, ...(text === undefined ? {} : { text }) });
  }
  return patches;
}

function applyPatches(posts: Post[], patches: Patch[]): Map<string, PatchState> {
  const states = new Map(posts.map((post) => [post.id, new PatchState(post)]));
  for (const patch of [...patches].sort((a, b) => a.at.localeCompare(b.at) || a.id.localeCompare(b.id))) states.get(patch.postId)!.apply(patch);
  return states;
}

type MarkdownEnvironment = {
  root: string;
  file: string;
  imagePrefix: string;
  wrapImages: boolean;
  sentinelPrefix?: string;
  imageBarToken?: string;
};

type Span = [number, number];

type LinkCandidate = {
  start: number;
  end: number;
  label: string;
  address?: string;
};

type MarkdownSyntaxSpan = {
  start: number;
  end: number;
};

function escapedAt(value: string, index: number): boolean {
  let slashes = 0;
  for (let cursor = index - 1; cursor >= 0 && value[cursor] === "\\"; cursor -= 1) slashes += 1;
  return slashes % 2 === 1;
}

function lineStarts(value: string): number[] {
  const starts = [0];
  for (let index = 0; index < value.length; index += 1) if (value[index] === "\n") starts.push(index + 1);
  return starts;
}

function blockSourceSpan(value: string, map: [number, number]): Span {
  const starts = lineStarts(value);
  const lines = value.split("\n");
  const start = starts[map[0]] ?? value.length;
  const lastLine = Math.max(map[0], map[1] - 1);
  const end = (starts[lastLine] ?? value.length) + (lines[lastLine] || "").length;
  return [codePointOffset(value, start), codePointOffset(value, end)];
}

function markdownCodeSpans(value: string): Span[] {
  const spans: Span[] = [];
  const blockSpans: Span[] = [];
  for (const token of markdown.parse(value, {})) {
    if ((token.type === "fence" || token.type === "code_block") && token.map) {
      const span = blockSourceSpan(value, token.map as [number, number]);
      blockSpans.push(span);
      spans.push(span);
    }
  }

  const isInBlock = (start: number, end: number) => blockSpans.some(([blockStart, blockEnd]) => start < blockEnd && blockStart < end);
  let index = 0;
  while (index < value.length) {
    if (value[index] !== "`" || escapedAt(value, index) || isInBlock(codePointOffset(value, index), codePointOffset(value, index + 1))) {
      index += 1;
      continue;
    }
    let run = 1;
    while (value[index + run] === "`") run += 1;
    let close = index + run;
    while (close < value.length) {
      // Backslashes have no escape meaning inside a CommonMark code span.
      if (value[close] !== "`") {
        close += 1;
        continue;
      }
      let closeRun = 1;
      while (value[close + closeRun] === "`") closeRun += 1;
      if (closeRun === run) {
        const start = codePointOffset(value, index);
        const end = codePointOffset(value, close + closeRun);
        if (!isInBlock(start, end)) spans.push([start, end]);
        index = close + closeRun;
        break;
      }
      close += closeRun;
    }
    if (close >= value.length) index += run;
  }
  return spans.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
}

function findBracketClose(value: string, start: number): number {
  let depth = 0;
  for (let index = start; index < value.length; index += 1) {
    if (escapedAt(value, index)) continue;
    if (value[index] === "[") depth += 1;
    if (value[index] !== "]") continue;
    depth -= 1;
    if (depth === 0) return index;
  }
  return -1;
}

function findParenClose(value: string, start: number): number {
  let depth = 0;
  for (let index = start; index < value.length; index += 1) {
    if (escapedAt(value, index)) continue;
    if (value[index] === "(") depth += 1;
    if (value[index] !== ")") continue;
    depth -= 1;
    if (depth === 0) return index;
  }
  return -1;
}

function referenceKey(value: string): string {
  return value.trim().replace(/[ \t\n]+/g, " ").toLowerCase();
}

function markdownImageEnd(value: string, index: number, references: Map<string, string>): number | undefined {
  if (value[index] !== "!" || value[index + 1] !== "[") return undefined;
  const labelEnd = findBracketClose(value, index + 1);
  if (labelEnd < 0) return undefined;
  let end = labelEnd + 1;
  if (value[end] === "(") {
    const destinationEnd = findParenClose(value, end);
    return destinationEnd < 0 ? undefined : destinationEnd + 1;
  }
  if (value[end] === "[") {
    const referenceEnd = findBracketClose(value, end);
    if (referenceEnd < 0) return undefined;
    const reference = value.slice(end + 1, referenceEnd) || value.slice(index + 2, labelEnd);
    return references.has(referenceKey(reference)) ? referenceEnd + 1 : undefined;
  }
  return references.has(referenceKey(value.slice(index + 2, labelEnd))) ? end : undefined;
}

function markdownLinkCandidates(value: string, codeSpans = markdownCodeSpans(value)): LinkCandidate[] {
  const candidates: LinkCandidate[] = [];
  const references = new Map<string, string>();
  const definitionRanges: Array<[number, number]> = [];
  const addCandidate = (start: number, end: number, label: string, address?: string) => {
    candidates.push({ start: codePointOffset(value, start), end: codePointOffset(value, end), label, ...(address === undefined ? {} : { address }) });
  };
  const addReferences = (pattern: RegExp) => {
    for (const match of value.matchAll(pattern)) {
      const start = match.index || 0;
      const lineEnd = value.indexOf("\n", start + match[0].length);
      const end = lineEnd < 0 ? value.length : lineEnd;
      const pointStart = codePointOffset(value, start);
      const pointEnd = codePointOffset(value, end);
      if (codeSpans.some(([codeStart, codeEnd]) => pointStart < codeEnd && codeStart < pointEnd)) continue;
      definitionRanges.push([start, end]);
      references.set(referenceKey(match[1]), match[2] || match[3] || "");
    }
  };
  addReferences(/^ {0,3}\[([^\]\n]+)\]:[ \t]*(?:<([^>\n]+)>|(\S+))/gm);
  addReferences(/^(?: {0,3}>[ \t]?)+[ \t]*\[([^\]\n]+)\]:[ \t]*(?:<([^>\n]+)>|(\S+))/gm);
  const inCode = (start: number, end: number) => {
    const startPoint = codePointOffset(value, start);
    const endPoint = codePointOffset(value, end);
    return codeSpans.some(([codeStart, codeEnd]) => codeStart <= startPoint && endPoint <= codeEnd);
  };
  for (let index = 0; index < value.length; index += 1) {
    if (escapedAt(value, index)) continue;
    const definition = definitionRanges.find(([start, end]) => start <= index && index < end);
    if (definition) {
      index = definition[1] - 1;
      continue;
    }
    const imageEnd = markdownImageEnd(value, index, references);
    if (imageEnd !== undefined) {
      index = imageEnd - 1;
      continue;
    }
    if (value[index] === "<") {
      const close = value.indexOf(">", index + 1);
      if (close >= 0 && /^[A-Za-z][A-Za-z0-9+.-]*:[^<>\s]+$/.test(value.slice(index + 1, close))) {
        if (!inCode(index, close + 1)) addCandidate(index, close + 1, value.slice(index + 1, close), value.slice(index + 1, close));
        index = close;
      }
      continue;
    }
    if (value[index] !== "[" || value[index - 1] === "!") continue;
    const labelEnd = findBracketClose(value, index);
    if (labelEnd < 0) continue;
    let end = labelEnd + 1;
    let address: string | undefined;
    if (value[end] === "(") {
      const destinationEnd = findParenClose(value, end);
      if (destinationEnd < 0) continue;
      const destination = value.slice(end + 1, destinationEnd).trim();
      const firstDestination = destination.split(/[ \t]+/, 1)[0] || "";
      address = firstDestination.startsWith("<") && firstDestination.endsWith(">") ? firstDestination.slice(1, -1) : firstDestination;
      end = destinationEnd + 1;
    } else if (value[end] === "[") {
      const referenceEnd = findBracketClose(value, end);
      if (referenceEnd < 0) continue;
      const reference = value.slice(end + 1, referenceEnd);
      const referenceName = reference || value.slice(index + 1, labelEnd);
      address = references.get(referenceKey(referenceName));
      if (address === undefined) {
        index = referenceEnd;
        continue;
      }
      end = referenceEnd + 1;
    } else {
      if (value[end] === ":") continue;
      const address = references.get(referenceKey(value.slice(index + 1, labelEnd)));
      if (address === undefined) continue;
      if (!inCode(index, end)) addCandidate(index, end, value.slice(index + 1, labelEnd), address);
      index = end - 1;
      continue;
    }
    if (!inCode(index, end)) addCandidate(index, end, value.slice(index + 1, labelEnd), address);
    index = end - 1;
  }
  return candidates;
}

export function externalLinkSpans(text: string): Array<[number, number]> {
  return markdownLinkCandidates(text).map(({ start, end }) => [start, end]);
}

function markdownImageSpans(value: string, codeSpans = markdownCodeSpans(value)): Span[] {
  const spans: Span[] = [];
  const references = new Map<string, string>();
  const addReferences = (pattern: RegExp) => {
    for (const match of value.matchAll(pattern)) {
      const start = match.index || 0;
      const lineEnd = value.indexOf("\n", start + match[0].length);
      const end = lineEnd < 0 ? value.length : lineEnd;
      const pointStart = codePointOffset(value, start);
      const pointEnd = codePointOffset(value, end);
      if (codeSpans.some(([codeStart, codeEnd]) => pointStart < codeEnd && codeStart < pointEnd)) continue;
      references.set(referenceKey(match[1]), match[2] || match[3] || "");
    }
  };
  addReferences(/^ {0,3}\[([^\]\n]+)\]:[ \t]*(?:<([^>\n]+)>|(\S+))/gm);
  addReferences(/^(?: {0,3}>[ \t]?)+[ \t]*\[([^\]\n]+)\]:[ \t]*(?:<([^>\n]+)>|(\S+))/gm);
  const inCode = (start: number, end: number) => {
    const startPoint = codePointOffset(value, start);
    const endPoint = codePointOffset(value, end);
    return codeSpans.some(([codeStart, codeEnd]) => codeStart < endPoint && startPoint < codeEnd);
  };
  for (let index = 0; index < value.length; index += 1) {
    if (value[index] !== "!" || escapedAt(value, index) || value[index + 1] !== "[") continue;
    const end = markdownImageEnd(value, index, references);
    if (end === undefined) continue;
    if (!inCode(index, end)) spans.push([codePointOffset(value, index), codePointOffset(value, end)]);
    index = end - 1;
  }
  const linkSpans = markdownLinkCandidates(value, codeSpans).map(({ start, end }) => [start, end] as Span);
  return spans.filter(([start, end]) => !linkSpans.some(([linkStart, linkEnd]) => linkStart <= start && end <= linkEnd));
}

function markdownSyntaxSpans(value: string): MarkdownSyntaxSpan[] {
  const spans: MarkdownSyntaxSpan[] = [];
  const lines = value.split("\n");
  const starts = lineStarts(value);
  const codeLines = new Set<number>();
  const tableLines = new Set<number>();
  const setextLines = new Set<number>();
  for (const token of markdown.parse(value, {})) {
    if (!token.map) continue;
    if (token.type === "fence" || token.type === "code_block") {
      for (let line = token.map[0]; line < token.map[1]; line += 1) codeLines.add(line);
    }
    if (token.type === "table_open") {
      for (let line = token.map[0]; line < token.map[1]; line += 1) tableLines.add(line);
    }
    if (token.type === "heading_open" && token.map[1] - token.map[0] > 1) setextLines.add(token.map[1] - 1);
  }
  const add = (line: number, start: number, end: number) => {
    if (end <= start) return;
    spans.push({ start: codePointOffset(value, starts[line] + start), end: codePointOffset(value, starts[line] + end) });
  };
  const linePrefix = (line: string, lineNumber: number): number => {
    let position = 0;
    let spaces = 0;
    while (position < line.length && spaces < 4 && line[position] === " ") {
      position += 1;
      spaces += 1;
    }
    while (line[position] === ">") {
      add(lineNumber, position, position + 1);
      position += 1;
      if (line[position] === " ") position += 1;
      spaces = 0;
      while (position < line.length && spaces < 4 && line[position] === " ") {
        position += 1;
        spaces += 1;
      }
    }
    return position;
  };
  const inCode = (start: number, end: number, codeSpans: Span[]) => codeSpans.some(([codeStart, codeEnd]) => start < codeEnd && codeStart < end);
  const codeSpans = markdownCodeSpans(value);
  for (let lineNumber = 0; lineNumber < lines.length; lineNumber += 1) {
    if (codeLines.has(lineNumber)) continue;
    const line = lines[lineNumber];
    const contentStart = linePrefix(line, lineNumber);
    const content = line.slice(contentStart);
    const absolute = (offset: number) => starts[lineNumber] + offset;
    const definition = /^\[[^\]\n]+\]:[ \t]*(?:<[^>\n]+>|\S+)/.exec(content);
    if (definition) {
      add(lineNumber, 0, line.length);
      continue;
    }
    const heading = /^(#{1,6})(?=[ \t]|$)/.exec(content);
    if (heading) {
      let end = contentStart + heading[1].length;
      while (end < line.length && (line[end] === " " || line[end] === "\t")) end += 1;
      add(lineNumber, contentStart, end);
    }
    const list = /^(?:[*+-]|\d{1,9}[.)])(?=[ \t]|$)/.exec(content);
    if (list) {
      let end = contentStart + list[0].length;
      while (end < line.length && (line[end] === " " || line[end] === "\t")) end += 1;
      add(lineNumber, contentStart, end);
    }
    if (/^(?:[ \t]*[*_-]){3,}[ \t]*$/.test(content)) add(lineNumber, contentStart, line.length);
    if (setextLines.has(lineNumber)) add(lineNumber, contentStart, line.length);
    if (!tableLines.has(lineNumber)) continue;
    const separatorCells = content.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());
    if (separatorCells.length > 1 && separatorCells.every((cell) => /^:?-+:?$/.test(cell))) add(lineNumber, contentStart, line.length);
    for (let column = contentStart; column < line.length; column += 1) {
      if (line[column] !== "|" || escapedAt(line, column)) continue;
      const point = codePointOffset(value, absolute(column));
      if (inCode(point, point + 1, codeSpans)) continue;
      const before = line.slice(0, column);
      const imageWidthBar = /!\[[^\]\n]*$/.test(before) && /^\d+\](?:\(|\[)/.test(line.slice(column + 1));
      if (!imageWidthBar) add(lineNumber, column, column + 1);
    }
  }
  return spans;
}

function overlaps(start: number, end: number, spanStart: number, spanEnd: number): boolean {
  return start < spanEnd && spanStart < end;
}

function covers(start: number, end: number, spanStart: number, spanEnd: number): boolean {
  return start <= spanStart && spanEnd <= end;
}

function validatePatchSourceOverlaps(body: string, start: number, end: number, patch: Patch): void {
  for (const [spanStart, spanEnd] of markdownCodeSpans(body)) {
    if (overlaps(start, end, spanStart, spanEnd) && !covers(start, end, spanStart, spanEnd)) fail(patch.source);
  }
  for (const [spanStart, spanEnd] of markdownImageSpans(body)) {
    if (overlaps(start, end, spanStart, spanEnd) && !covers(start, end, spanStart, spanEnd)) fail(patch.source);
  }
  for (const { start: spanStart, end: spanEnd } of markdownLinkCandidates(body)) {
    if (overlaps(start, end, spanStart, spanEnd) && !covers(start, end, spanStart, spanEnd)) fail(patch.source);
  }
  for (const { start: spanStart, end: spanEnd } of markdownSyntaxSpans(body)) {
    if (overlaps(start, end, spanStart, spanEnd)) fail(patch.source);
  }
}

function validatePatchExternalOverlaps(states: Map<string, PatchState>): void {
  for (const state of states.values()) {
    for (const [linkStart, linkEnd] of externalLinkSpans(state.body)) {
      for (const [regionStart, regionEnd, patch] of state.patchRanges()) {
        const overlaps = linkStart < regionEnd && regionStart < linkEnd;
        const coversLink = regionStart <= linkStart && linkEnd <= regionEnd;
        if (overlaps && !coversLink) fail(patch.source);
      }
    }
  }
}

function validatePatchCodeOverlaps(states: Map<string, PatchState>): void {
  for (const state of states.values()) {
    for (const codeSpan of markdownCodeSpans(state.body)) {
      for (const [regionStart, regionEnd, patch] of state.patchRanges()) {
        const overlaps = codeSpan[0] < regionEnd && regionStart < codeSpan[1];
        const coversCode = regionStart <= codeSpan[0] && codeSpan[1] <= regionEnd;
        if (overlaps && !coversCode) fail(patch.source);
      }
    }
  }
}

function validatePatchImageOverlaps(states: Map<string, PatchState>): void {
  for (const state of states.values()) {
    for (const imageSpan of markdownImageSpans(state.body)) {
      for (const [regionStart, regionEnd, patch] of state.patchRanges()) {
        const overlaps = imageSpan[0] < regionEnd && regionStart < imageSpan[1];
        const coversImage = regionStart <= imageSpan[0] && imageSpan[1] <= regionEnd;
        if (overlaps && !coversImage) fail(patch.source);
      }
    }
  }
}

function validatePatchSyntaxOverlaps(states: Map<string, PatchState>): void {
  for (const state of states.values()) {
    for (const { start: syntaxStart, end: syntaxEnd } of markdownSyntaxSpans(state.body)) {
      for (const [regionStart, regionEnd, patch] of state.patchRanges()) {
        if (overlaps(syntaxStart, syntaxEnd, regionStart, regionEnd)) fail(patch.source);
      }
    }
  }
}

function parseLinks(root: string, posts: Post[], states: Map<string, PatchState>): Link[] {
  const knownPosts = new Set(posts.map((post) => post.id));
  const byId = new Map<string, Link>();
  for (const row of tableRows(root, "links.jsonl")) {
    const action = row.value.action;
    if (typeof action !== "string") fail(row.file);
    if (action === "created") {
      if (Object.keys(row.value).sort().join("|") !== "action|anchor|at|from|link|to|why") fail(row.file);
      const id = stringValue(row.value.link, row.file);
      const fromId = stringValue(row.value.from, row.file);
      const toId = stringValue(row.value.to, row.file);
      const anchor = stringValue(row.value.anchor, row.file);
      if (!RECORD_ID_RE.test(id) || byId.has(id) || !anchor || !knownPosts.has(fromId) || !knownPosts.has(toId)) fail(row.file);
      byId.set(id, { source: row.file, line: row.line, id, fromId, toId, anchor, events: [], active: true, createdAt: "", currentReason: "" });
    } else if (action === "reason-changed" || action === "removed") {
      if (Object.keys(row.value).sort().join("|") !== "action|at|link|why") fail(row.file);
      const id = stringValue(row.value.link, row.file);
      if (!byId.has(id)) fail(row.file);
    } else {
      fail(row.file);
    }
    const at = parseWritten(stringValue(row.value.at, row.file), row.file);
    const why = stringValue(row.value.why, row.file);
    const link = byId.get(stringValue(row.value.link, row.file))!;
    if (link.events.length && at < link.events[link.events.length - 1].at) fail(row.file);
    link.events.push({ action, at, why });
  }

  const links = [...byId.values()];
  for (const link of links) {
    link.createdAt = link.events[0].at;
    link.currentReason = [...link.events].reverse().find((event) => event.action !== "removed")?.why || "";
    link.active = link.events[link.events.length - 1].action !== "removed";
    const body = states.get(link.fromId)!.body;
    if (occurrences(body, link.anchor).length !== 1) fail(link.source);
    const start = codePointOffset(body, body.indexOf(link.anchor));
    const end = start + Array.from(link.anchor).length;
    if (markdownCodeSpans(body).some(([codeStart, codeEnd]) => start < codeEnd && codeStart < end)) fail(link.source);
    if (externalLinkSpans(body).some(([linkStart, linkEnd]) => start < linkEnd && linkStart < end)) fail(link.source);
  }
  return links;
}

function validTag(tag: string): boolean {
  return tag.length > 0 && tag.length <= 40 && tag === tag.trim() && ![".", ".."].includes(tag) && !/[\\/\n\r]/.test(tag);
}

function parseShares(root: string, posts: Post[]): Map<string, Share[]> {
  const knownPosts = new Set(posts.map((post) => post.id));
  const shares: Share[] = [];
  for (const row of tableRows(root, "shares.jsonl")) {
    if (Object.keys(row.value).sort().join("|") !== "at|post|url|where") fail(row.file);
    const post = stringValue(row.value.post, row.file);
    const where = stringValue(row.value.where, row.file);
    const url = stringValue(row.value.url, row.file);
    const at = stringValue(row.value.at, row.file);
    if (!knownPosts.has(post) || !(where in SHARE_PLACES) || !/^https:\/\/\S+$/.test(url)) fail(row.file);
    parseWritten(at, row.file);
    shares.push({ post, where, url, at, line: row.line });
  }
  shares.sort((a, b) => a.at.localeCompare(b.at) || a.line - b.line);
  const result = new Map<string, Share[]>();
  for (const share of shares) result.set(share.post, [...(result.get(share.post) || []), share]);
  return result;
}

function parseTags(root: string, posts: Post[]): Map<string, Tagging[]> {
  const knownPosts = new Set(posts.map((post) => post.id));
  const last = new Map<string, { action: string; at: string; why: string }>();
  for (const row of tableRows(root, "tags.jsonl")) {
    if (Object.keys(row.value).sort().join("|") !== "action|at|post|tag|why") fail(row.file);
    const post = stringValue(row.value.post, row.file);
    const tag = stringValue(row.value.tag, row.file);
    const action = stringValue(row.value.action, row.file);
    const at = stringValue(row.value.at, row.file);
    const why = stringValue(row.value.why, row.file);
    if (!knownPosts.has(post) || !validTag(tag) || !["added", "removed"].includes(action)) fail(row.file);
    parseWritten(at, row.file);
    const key = `${post}\u0000${tag}`;
    const previous = last.get(key);
    if ((!previous && action !== "added") || (previous && (previous.action === action || at < previous.at))) fail(row.file);
    last.set(key, { action, at, why });
  }
  const result = new Map<string, Tagging[]>();
  for (const [key, value] of [...last.entries()].sort(([a], [b]) => a.localeCompare(b))) {
    if (value.action !== "added") continue;
    const separator = key.indexOf("\u0000");
    const post = key.slice(0, separator);
    result.set(post, [...(result.get(post) || []), { tag: key.slice(separator + 1), at: value.at, why: value.why }]);
  }
  return result;
}

function parseAbout(root: string): { path: string; body: string } {
  const file = path.join(root, "about.md");
  if (!fs.existsSync(file)) fail(file);
  const body = readUtf8(file);
  if (!body.trim()) fail(file);
  validateBodyCharacters(body, file);
  return { path: file, body };
}

function stripPatchMarkers(value: string): string {
  return value.replace(PATCH_MARKER_RE, "");
}

function visibleText(value: string): string {
  const withAlt = value.replace(/<img\b[^>]*\balt="([^"]*)"[^>]*>/gi, "$1");
  return withAlt
    .replace(/<[^>]+>/g, "")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#(\d+);/g, (_, code) => String.fromCodePoint(Number(code)))
    .replace(/&#x([0-9a-f]+);/gi, (_, code) => String.fromCodePoint(parseInt(code, 16)));
}

function markdownPrefixLength(line: string): number | "next-line" {
  let index = 0;
  while (index < line.length && index < 3 && line[index] === " ") index += 1;
  while (line[index] === ">") {
    index += 1;
    if (line[index] === " ") index += 1;
    while (line[index] === " ") index += 1;
  }
  const heading = /#{1,6}[ \t]+/.exec(line.slice(index));
  if (heading?.index === 0) return index + heading[0].length;
  const list = /(?:[*+-]|\d{1,9}[.)])[ \t]+/.exec(line.slice(index));
  if (list?.index === 0) return index + list[0].length;
  if (/^(?:`{3,}|~{3,})/.test(line.slice(index)) || /^(?:\*\s*){3,}$|^(?:-\s*){3,}$|^(?:_\s*){3,}$/.test(line.slice(index))) return "next-line";
  return index;
}

function normalizePatchMarkers(value: string): string {
  const lines = value.split("\n");
  const protectedLines = new Set<number>();
  for (const token of markdown.parse(stripPatchMarkers(value), {})) {
    if ((token.type !== "fence" && token.type !== "code_block") || !token.map) continue;
    const openingLine = token.map[0];
    const closingLine = token.map[1] - 1;
    const lineMarkers = (line: string) => {
      return [...line.matchAll(new RegExp(PATCH_MARKER_RE.source, "g"))].map((match) => match[0]);
    };
    const openingMarkers = lineMarkers(lines[openingLine] || "").filter((marker) => marker.includes("-start-"));
    let closingMarkers = lineMarkers(lines[closingLine] || "").filter((marker) => marker.includes("-end-"));
    let closingMarkerLine = closingLine;
    const trailingLine = closingLine + 1;
    if (!closingMarkers.length && stripPatchMarkers(lines[trailingLine] || "").trim() === "") {
      const trailingMarkers = lineMarkers(lines[trailingLine] || "").filter((marker) => marker.includes("-end-"));
      if (trailingMarkers.length) {
        closingMarkers = trailingMarkers;
        closingMarkerLine = trailingLine;
      }
    }
    if (!openingMarkers.length && !closingMarkers.length) continue;
    lines[openingLine] = stripPatchMarkers(lines[openingLine]);
    lines[closingMarkerLine] = stripPatchMarkers(lines[closingMarkerLine]);
    for (let index = openingLine; index <= closingMarkerLine; index += 1) protectedLines.add(index);
    if (token.type === "fence") {
      if (closingLine > openingLine + 1) {
        if (openingMarkers.length) lines[openingLine + 1] = openingMarkers.join("") + lines[openingLine + 1];
        if (closingMarkers.length) lines[closingLine - 1] += closingMarkers.join("");
      } else {
        lines.splice(closingLine, 0, [...openingMarkers, ...closingMarkers].join(""));
      }
    } else {
      const clean = lines[openingLine];
      const indent = clean.match(/^(?: {4}|\t)/)?.[0] || "";
      lines[openingLine] = indent + openingMarkers.join("") + clean.slice(indent.length);
      if (closingLine === openingLine) lines[openingLine] += closingMarkers.join("");
      else if (closingMarkers.length) lines[closingLine] += closingMarkers.join("");
    }
  }
  for (let index = 0; index < lines.length; index += 1) {
    if (protectedLines.has(index)) continue;
    const matches = [...lines[index].matchAll(new RegExp(PATCH_MARKER_RE.source, "g"))];
    if (!matches.length) continue;
    const clean = stripPatchMarkers(lines[index]);
    const prefix = markdownPrefixLength(clean);
    if (prefix === "next-line") {
      const before: string[] = [];
      const after: string[] = [];
      const inline: Array<{ position: number; marker: string }> = [];
      for (const match of matches) {
        const position = Array.from(stripPatchMarkers(lines[index].slice(0, match.index))).length;
        if (position === 0) before.push(match[0]);
        else if (position >= Array.from(clean).length) after.push(match[0]);
        else inline.push({ position, marker: match[0] });
      }
      lines[index] = clean;
      if (before.length) {
        lines.splice(index, 0, before.join(""));
        index += 1;
      }
      for (let inlineIndex = inline.length - 1; inlineIndex >= 0; inlineIndex -= 1) {
        const item = inline[inlineIndex];
        lines[index] = lines[index].slice(0, item.position) + item.marker + lines[index].slice(item.position);
      }
      if (after.length) lines.splice(index + 1, 0, after.join(""));
    } else {
      const insertions = new Map<number, string[]>();
      for (const match of matches) {
        let position = Array.from(stripPatchMarkers(lines[index].slice(0, match.index))).length;
        if (position === 0 && prefix > 0) position = prefix;
        if (!insertions.has(position)) insertions.set(position, []);
        insertions.get(position)!.push(match[0]);
      }
      lines[index] = clean;
      for (const position of [...insertions.keys()].sort((a, b) => b - a)) {
        lines[index] = lines[index].slice(0, position) + insertions.get(position)!.join("") + lines[index].slice(position);
      }
    }
  }
  return lines.join("\n");
}

function protectImageWidthBars(value: string): { source: string; token: string } {
  let token = "GUIN_IMAGE_BAR_";
  while (value.includes(token)) token += "_";
  const codeSpans = markdownCodeSpans(value);
  const inCode = (start: number, end: number) => {
    const startPoint = codePointOffset(value, start);
    const endPoint = codePointOffset(value, end);
    return codeSpans.some(([codeStart, codeEnd]) => startPoint < codeEnd && codeStart < endPoint);
  };
  let result = "";
  let cursor = 0;
  for (const match of value.matchAll(/!\[[^\]\n]*\|(\d+)\](?=\(|\[)/g)) {
    const bar = (match.index || 0) + match[0].lastIndexOf("|", match[0].length - 1);
    if (inCode(match.index || 0, bar + 1)) continue;
    result += value.slice(cursor, bar) + token;
    cursor = bar + 1;
  }
  return { source: result + value.slice(cursor), token };
}

function walkTokens(tokens: Token[], visit: (token: Token) => void, insideLink = false): void {
  let linkDepth = insideLink ? 1 : 0;
  for (const token of tokens) {
    if (!(linkDepth > 0 && token.type === "image")) visit(token);
    if (token.children) walkTokens(token.children, visit, linkDepth > 0 || token.type === "link_open");
    if (token.type === "link_open") linkDepth += 1;
    if (token.type === "link_close") linkDepth = Math.max(0, linkDepth - 1);
  }
}

function validateHttpAddress(address: string, file: string): void {
  if (!/^https?:\/\/\S+$/.test(address)) fail(file);
}

function validateMarkdown(value: string, root: string, file: string): Token[] {
  const codeSpans = markdownCodeSpans(value);
  for (const candidate of markdownLinkCandidates(value, codeSpans)) if (candidate.address !== undefined) validateHttpAddress(candidate.address, file);
  const protectedMarkdown = protectImageWidthBars(value);
  const tokens = markdown.parse(protectedMarkdown.source, {});
  walkTokens(tokens, (token) => {
    if (token.type === "link_open") validateHttpAddress(token.attrGet("href") || "", file);
    if (token.type === "image") {
      const source = token.attrGet("src") || "";
      imageSource(root, source, file);
      imageWidth((token.attrGet("alt") || token.content).replaceAll(protectedMarkdown.token, "|"), file);
    }
  });
  return tokens;
}

function literalizeLinkChildren(tokens: Token[], candidates: LinkCandidate[]): void {
  let candidateIndex = 0;
  const rewrite = (children: Token[]): Token[] => {
    const result: Token[] = [];
    for (let index = 0; index < children.length; index += 1) {
      const token = children[index];
      if (token.type !== "link_open") {
        if (token.children) token.children = rewrite(token.children);
        result.push(token);
        continue;
      }
      let depth = 1;
      let close = index + 1;
      while (close < children.length && depth > 0) {
        if (children[close].type === "link_open") depth += 1;
        if (children[close].type === "link_close") depth -= 1;
        close += 1;
      }
      const candidate = candidates[candidateIndex++];
      if (candidate && close > index + 1) token.meta = { ...(token.meta || {}), literalLabel: candidate.label };
      result.push(token);
      if (close <= children.length) result.push(children[close - 1]);
      index = close - 1;
    }
    return result;
  };
  for (const token of tokens) if (token.children) token.children = rewrite(token.children);
}

function renderMarkdown(value: string, environment: MarkdownEnvironment): string {
  const protectedMarkdown = protectImageWidthBars(value);
  environment.imageBarToken = protectedMarkdown.token;
  const tokens = markdown.parse(protectedMarkdown.source, environment);
  literalizeLinkChildren(tokens, markdownLinkCandidates(stripPatchMarkers(value)));
  return markdown.renderer.render(tokens, markdown.options, environment);
}

function compactOpen(tag: string): (_tokens: Token[], _index: number) => string {
  return () => `<${tag}>`;
}

function compactClose(tag: string): (_tokens: Token[], _index: number) => string {
  return () => `</${tag}>`;
}

function renderedAttrs(token: Token): string {
  return (token.attrs || []).map(([name, value]) => {
    const style = /^text-align:(left|center|right)$/.exec(value);
    const renderedValue = name === "style" && style ? `text-align: ${style[1]}` : value;
    return ` ${name}="${htmlEscape(renderedValue, true)}"`;
  }).join("");
}

function renderSentinelPattern(prefix: string): RegExp {
  const escaped = prefix.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`${escaped}(?:PATCHSTART|PATCHEND)\\d+X`, "g");
}

function stripRenderSentinels(value: string, prefix?: string): string {
  return prefix ? value.replace(renderSentinelPattern(prefix), "") : value;
}

function wrapWithRenderSentinels(value: string, markup: string, prefix?: string): string {
  if (!prefix) return markup;
  const markers = [...value.matchAll(renderSentinelPattern(prefix))].map((match) => match[0]);
  if (!markers.length) return markup;
  return markers.filter((marker) => marker.includes("PATCHSTART")).join("")
    + markup
    + markers.filter((marker) => marker.includes("PATCHEND")).join("");
}

function renderedImageAlt(token: Token, environment: MarkdownEnvironment): string {
  return stripRenderSentinels(token.attrGet("alt") || token.content, environment.sentinelPrefix)
    .replaceAll(environment.imageBarToken || "\u0000never-image-bar-token\u0000", "|");
}

function markerOnlyParagraph(tokens: Token[], index: number, environment: MarkdownEnvironment | undefined, inlineIndex: number): boolean {
  const prefix = environment?.sentinelPrefix;
  if (!prefix || !tokens[inlineIndex] || tokens[inlineIndex].type !== "inline") return false;
  const escapedPrefix = prefix.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`^(?:${escapedPrefix}(?:PATCHSTART|PATCHEND)\\d+X\\s*)+$`).test(tokens[inlineIndex].content.trim());
}

markdown.renderer.rules.blockquote_open = () => "<blockquote>";
markdown.renderer.rules.blockquote_close = () => "</blockquote>";
markdown.renderer.rules.paragraph_open = (tokens, index, _options, environment) => tokens[index].hidden || markerOnlyParagraph(tokens, index, environment as MarkdownEnvironment | undefined, index + 1) ? "" : "<p>";
markdown.renderer.rules.paragraph_close = (tokens, index, _options, environment) => tokens[index].hidden || markerOnlyParagraph(tokens, index, environment as MarkdownEnvironment | undefined, index - 1) ? "" : "</p>";
markdown.renderer.rules.heading_open = (tokens, index) => `<h${tokens[index].tag.slice(1)}>`;
markdown.renderer.rules.heading_close = (tokens, index) => `</h${tokens[index].tag.slice(1)}>`;
markdown.renderer.rules.bullet_list_open = compactOpen("ul");
markdown.renderer.rules.bullet_list_close = compactClose("ul");
markdown.renderer.rules.ordered_list_open = (tokens, index) => {
  const start = tokens[index].attrGet("start");
  return start && String(start) !== "1" ? `<ol start="${htmlEscape(String(start), true)}">` : "<ol>";
};
markdown.renderer.rules.ordered_list_close = compactClose("ol");
markdown.renderer.rules.list_item_open = compactOpen("li");
markdown.renderer.rules.list_item_close = compactClose("li");
markdown.renderer.rules.table_open = compactOpen("table");
markdown.renderer.rules.table_close = compactClose("table");
markdown.renderer.rules.thead_open = compactOpen("thead");
markdown.renderer.rules.thead_close = compactClose("thead");
markdown.renderer.rules.tbody_open = compactOpen("tbody");
markdown.renderer.rules.tbody_close = compactClose("tbody");
markdown.renderer.rules.tr_open = compactOpen("tr");
markdown.renderer.rules.tr_close = compactClose("tr");
markdown.renderer.rules.th_open = (tokens, index) => `<th${renderedAttrs(tokens[index])}>`;
markdown.renderer.rules.th_close = compactClose("th");
markdown.renderer.rules.td_open = (tokens, index) => `<td${renderedAttrs(tokens[index])}>`;
markdown.renderer.rules.td_close = compactClose("td");
markdown.renderer.rules.text = (tokens, index) => htmlEscape(tokens[index].content);
markdown.renderer.rules.code_inline = (tokens, index) => `<code>${htmlEscape(tokens[index].content)}</code>`;
markdown.renderer.rules.hr = () => "<hr>";
markdown.renderer.rules.softbreak = () => "<br>\n";
markdown.renderer.rules.fence = (tokens, index) => {
  const token = tokens[index];
  const info = token.info.trim().split(/\s+/, 1)[0];
  const language = info ? ` class="language-${htmlEscape(info, true)}"` : "";
  return `<pre><code${language}>${htmlEscape(token.content)}</code></pre>`;
};
markdown.renderer.rules.code_block = (tokens, index) => `<pre><code>${htmlEscape(tokens[index].content)}</code></pre>`;
markdown.renderer.rules.link_open = (tokens, index, _options, environment) => {
  const token = tokens[index];
  const href = token.attrGet("href") || "";
  validateHttpAddress(href, (environment as MarkdownEnvironment).file);
  const label = token.meta?.literalLabel;
  return `<a href="${htmlEscape(href, true)}">${label === undefined ? "" : htmlEscape(label)}`;
};
markdown.renderer.rules.link_close = () => "</a>";
markdown.renderer.rules.image = (tokens, index, _options, environment) => {
  const token = tokens[index];
  const context = environment as MarkdownEnvironment;
  const rawSource = token.attrGet("src") || "";
  const source = stripRenderSentinels(rawSource, context.sentinelPrefix);
  const image = imageWidth(renderedImageAlt(token, context), context.file);
  imageSource(context.root, source, context.file);
  const imageUrl = context.imagePrefix + source.slice("images/".length);
  const imageMarkup = `<img src="${htmlEscape(imageUrl, true)}" alt="${htmlEscape(image.alt, true)}"${image.width ? ` width="${image.width}"` : ""}>`;
  const wrappedImage = context.wrapImages ? `<a class="image-zoom" href="${htmlEscape(imageUrl, true)}">${imageMarkup}</a>` : imageMarkup;
  return wrapWithRenderSentinels(`${token.content} ${rawSource}`, wrappedImage, context.sentinelPrefix);
};

function renderSentinelSource(value: string): { source: string; prefix: string } {
  let prefix = "GUIN_SENTINEL_";
  while (value.includes(prefix)) prefix += "_";
  return { source: value
    .replace(PATCH_MARKER_RE, (marker) => {
      const index = marker.match(/-(?:start|end)-(\d+)\u0000$/)?.[1] || "0";
      return marker.includes("-start-") ? `${prefix}PATCHSTART${index}X` : `${prefix}PATCHEND${index}X`;
    })
    .replace(/\u0000guin-link-(\d+)\u0000/g, (_marker, index) => `${prefix}LINK${index}X`), prefix };
}

function restoreRenderSentinels(value: string, prefix: string): string {
  return value
    .replace(new RegExp(`${prefix}PATCHSTART(\\d+)X`, "g"), (_marker, index) => patchStart(Number(index)))
    .replace(new RegExp(`${prefix}PATCHEND(\\d+)X`, "g"), (_marker, index) => patchEnd(Number(index)))
    .replace(new RegExp(`${prefix}LINK(\\d+)X`, "g"), (_marker, index) => `\u0000guin-link-${index}\u0000`);
}

function applyAnchorReplacements(body: string, replacements: Array<[string, string]>, file: string): string {
  const visiblePositions: number[] = [];
  let index = 0;
  while (index < body.length) {
    PATCH_MARKER_RE.lastIndex = index;
    const marker = PATCH_MARKER_RE.exec(body);
    if (marker && marker.index === index) {
      index += marker[0].length;
      continue;
    }
    visiblePositions.push(index++);
  }
  const visible = visiblePositions.map((position) => body[position]).join("");
  const toReplace: Array<{ start: number; end: number; replacement: string }> = [];
  for (const [anchor, replacement] of replacements) {
    const position = visible.indexOf(anchor);
    if (position < 0 || !anchor) fail(file);
    const start = visiblePositions[position];
    const end = visiblePositions[position + anchor.length - 1] + 1;
    toReplace.push({ start, end, replacement });
  }
  toReplace.sort((a, b) => a.start - b.start);
  const pieces: string[] = [];
  let cursor = 0;
  for (const [replacementIndex, occurrence] of toReplace.entries()) {
    if (occurrence.start < cursor) fail(file);
    const token = `\u0000guin-link-${replacementIndex}\u0000`;
    const inner = [...body.slice(occurrence.start, occurrence.end).matchAll(PATCH_MARKER_RE)].map((match) => match[0]);
    pieces.push(body.slice(cursor, occurrence.start), ...inner.filter((marker) => marker.includes("-start-")), token, ...inner.filter((marker) => marker.includes("-end-")));
    cursor = occurrence.end;
  }
  pieces.push(body.slice(cursor));
  return pieces.join("");
}

function renderBodyHtml(body: string, root: string, file: string, imagePrefix: string, wrapImages: boolean, state?: PatchState, replacements: Array<[string, string]> = []): string {
  let sourceBody = body;
  if (state?.hasPatches) {
    sourceBody = state.markedBody().body;
  }
  if (replacements.length) {
    sourceBody = applyAnchorReplacements(sourceBody, replacements, file);
  }
  const cleanBody = stripPatchMarkers(sourceBody);
  validateMarkdown(cleanBody, root, file);
  const sentinels = renderSentinelSource(normalizePatchMarkers(sourceBody));
  const rendered = restoreRenderSentinels(renderMarkdown(sentinels.source, { root, file, imagePrefix, wrapImages, sentinelPrefix: sentinels.prefix }), sentinels.prefix);
  return rendered || (sourceBody.includes("\u0000guin-patch-") ? sourceBody : "");
}

function firstParagraphText(body: string, root: string, file: string): string {
  const cleanBody = stripPatchMarkers(body);
  const tokens = validateMarkdown(cleanBody, root, file);
  literalizeLinkChildren(tokens, markdownLinkCandidates(cleanBody));
  const environment = { root, file, imagePrefix: "", wrapImages: false, imageBarToken: protectImageWidthBars(cleanBody).token };
  for (let index = 0; index + 1 < tokens.length; index += 1) {
    if (tokens[index].type !== "paragraph_open" || tokens[index].hidden || tokens[index + 1].type !== "inline") continue;
    return visibleText(markdown.renderer.renderInline(tokens[index + 1].children || [], markdown.options, environment));
  }
  return "";
}

export function formatUtc(written: string): string {
  return `${written.slice(0, 16).replace("T", " ")} UTC`;
}

export function feedPosts(site: SiteData): Post[] {
  return [...site.posts].sort((a, b) => b.written.localeCompare(a.written) || b.id.localeCompare(a.id));
}

export function feedTitle(post: Post): string {
  if (post.title) return post.title;
  return post.firstText.slice(0, 80) + (post.firstText.length > 80 ? "…" : "");
}

export function taggedPosts(site: SiteData, tag: string): Post[] {
  return site.posts.filter((post) => (site.taggings.get(post.id) || []).some((item) => item.tag === tag)).sort((a, b) => b.written.localeCompare(a.written));
}

export function postTags(site: SiteData, post: Post): Tagging[] {
  return [...(site.taggings.get(post.id) || [])].sort((a, b) => a.tag.localeCompare(b.tag));
}

export interface TagCount {
  tag: string;
  count: number;
  size: number;
}

export function tagCounts(site: SiteData): TagCount[] {
  const counts = new Map<string, number>();
  for (const items of site.taggings.values()) for (const item of items) counts.set(item.tag, (counts.get(item.tag) || 0) + 1);
  if (!counts.size) return [];
  const values = [...counts.values()];
  const low = Math.min(...values);
  const high = Math.max(...values);
  return [...counts.keys()].sort().map((tag) => {
    const count = counts.get(tag) || 0;
    return { tag, count, size: 0.9 + (high > low ? 0.7 * (count - low) / (high - low) : 0.2) };
  });
}

export function renderFeedBody(site: SiteData, post: Post, root: string): string {
  return renderBodyHtml(site.patchStates.get(post.id)!.body, site.contentRoot, post.source, `${root}images/`, false);
}

export function renderAboutBody(site: SiteData, root: string): string {
  return renderBodyHtml(site.aboutBody, site.contentRoot, site.aboutPath, `${root}images/`, true);
}

export function renderPostBody(site: SiteData, post: Post, root: string): PostBodyMarkup {
  const state = site.patchStates.get(post.id)!;
  const outgoing = site.links.filter((link) => link.active && link.fromId === post.id).sort((a, b) => {
    const position = state.body.indexOf(a.anchor) - state.body.indexOf(b.anchor);
    return position || a.id.localeCompare(b.id);
  });
  const links = outgoing.map((link, index) => ({
    token: `\u0000guin-link-${index}\u0000`,
    href: `../${link.toId}/`,
    label: link.anchor,
    number: index + 1,
  }));
  const replacements: Array<[string, string]> = outgoing.map((link, index) => [link.anchor, links[index].token]);
  const marked = state.markedBody();
  return {
    html: renderBodyHtml(state.body, site.contentRoot, post.source, `${root}images/`, true, state, replacements),
    links,
    regions: marked.regions,
  };
}

export function patchData(state: PatchState): { body: string; patches: Array<Record<string, unknown>>; regions: Array<Record<string, unknown>>; "region-data": Array<Record<string, unknown>>; "patch-history": boolean } {
  const marked = state.markedBody();
  const record = (patch: Patch): Record<string, unknown> => ({
    id: patch.id,
    at: patch.at,
    why: patch.why,
    op: patch.op,
    anchor: patch.anchor,
    previous: patch.op === "replace" || patch.op === "delete" ? patch.anchor : "새로 넣음",
    previous_text: patch.op === "replace" || patch.op === "delete" ? patch.anchor : "새로 넣음",
    ...(patch.text === undefined ? {} : { text: patch.text }),
  });
  return {
    body: state.body,
    patches: state.patches.map(record),
    regions: marked.regions.map((region) => ({ id: region.id, deleted: region.deleted, patches: region.history.map(record) })),
    "region-data": marked.regions.map((region) => ({ id: region.id, deleted: region.deleted })),
    "patch-history": true,
  };
}

export function loadSite(): SiteData {
  const root = rootPath();
  const about = parseAbout(root);
  const posts = parsePosts(root);
  const patchStates = applyPatches(posts, parsePatches(root, posts));
  validatePatchCodeOverlaps(patchStates);
  validatePatchImageOverlaps(patchStates);
  validatePatchExternalOverlaps(patchStates);
  validatePatchSyntaxOverlaps(patchStates);
  const links = parseLinks(root, posts, patchStates);
  const site: SiteData = { contentRoot: root, aboutPath: path.join(root, "about.md"), aboutBody: about.body, posts, links, patchStates, shares: parseShares(root, posts), taggings: parseTags(root, posts) };
  for (const post of posts) post.firstText = firstParagraphText(patchStates.get(post.id)!.body, root, post.source);
  return site;
}
