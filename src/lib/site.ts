import fs from "node:fs";
import path from "node:path";

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
const INLINE_RE = /!\[([^\]]*)\]\(([^)]*)\)|\*\*(.+?)\*\*|`([^`]+)`|\*(?!\s)(.+?)(?<!\s)\*/g;
const INLINE_WITH_LINKS_RE = new RegExp(`${INLINE_RE.source}|\\[([^\\]]*)\\]\\(([^)]*)\\)`, "g");
const HEADING_RE = /^(#{1,3})[ \t]+(.*)$/;
const PATCH_MARKER_RE = /\u0000guin-patch-(?:start|end)-\d+\u0000/g;

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
  const match = /^(.*)\|(\d{1,4})$/s.exec(alt);
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
    patches.push({ source: row.file, line: row.line, id, postId, at, why, op: op as PatchOp, anchor, ...(text === undefined ? {} : { text }) });
  }
  return patches;
}

function applyPatches(posts: Post[], patches: Patch[]): Map<string, PatchState> {
  const states = new Map(posts.map((post) => [post.id, new PatchState(post)]));
  for (const patch of [...patches].sort((a, b) => a.at.localeCompare(b.at) || a.id.localeCompare(b.id))) states.get(patch.postId)!.apply(patch);
  return states;
}

export function externalLinkSpans(text: string): Array<[number, number]> {
  const spans: Array<[number, number]> = [];
  for (const match of text.matchAll(INLINE_WITH_LINKS_RE)) {
    if (match[6] === undefined) continue;
    const start = codePointOffset(text, match.index || 0);
    spans.push([start, start + Array.from(match[0]).length]);
  }
  return spans;
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
  return { path: file, body };
}

function stripPatchMarkers(value: string): string {
  return value.replace(PATCH_MARKER_RE, "");
}

function removeVisiblePrefix(value: string, count: number): string {
  let consumed = 0;
  let index = 0;
  let result = "";
  while (index < value.length && consumed < count) {
    PATCH_MARKER_RE.lastIndex = index;
    const marker = PATCH_MARKER_RE.exec(value);
    if (marker && marker.index === index) {
      result += marker[0];
      index = marker.index + marker[0].length;
      continue;
    }
    consumed += 1;
    index += 1;
  }
  return result + value.slice(index);
}

type MarkdownBlock = { kind: "heading"; level: number; text: string } | { kind: "list"; items: string[] } | { kind: "quote"; lines: string[] } | { kind: "paragraph"; lines: string[] };

function markdownBlocks(body: string): MarkdownBlock[] {
  const lines = body.replace(/^\n+|\n+$/g, "").split("\n");
  const blocks: MarkdownBlock[] = [];
  let index = 0;
  while (index < lines.length) {
    const clean = stripPatchMarkers(lines[index]);
    if (!clean.trim()) {
      if (lines[index] !== clean) blocks.push({ kind: "paragraph", lines: [lines[index++]] });
      else index += 1;
      continue;
    }
    const heading = HEADING_RE.exec(clean);
    if (heading) {
      let prefix = heading[1].length;
      while (prefix < clean.length && " \t".includes(clean[prefix])) prefix += 1;
      blocks.push({ kind: "heading", level: heading[1].length, text: removeVisiblePrefix(lines[index++], prefix) });
      continue;
    }
    if (clean.startsWith("- ")) {
      const items: string[] = [];
      while (index < lines.length && stripPatchMarkers(lines[index]).startsWith("- ")) items.push(removeVisiblePrefix(lines[index++], 2));
      blocks.push({ kind: "list", items });
      continue;
    }
    if (clean.startsWith("> ")) {
      const quote: string[] = [];
      while (index < lines.length && stripPatchMarkers(lines[index]).startsWith("> ")) quote.push(removeVisiblePrefix(lines[index++], 2));
      blocks.push({ kind: "quote", lines: quote });
      continue;
    }
    const paragraph: string[] = [];
    while (index < lines.length && stripPatchMarkers(lines[index]).trim()) paragraph.push(lines[index++]);
    blocks.push({ kind: "paragraph", lines: paragraph });
  }
  return blocks;
}

function inlineMarkdown(text: string, root: string, file: string, imagePrefix: string, wrapImages: boolean): string {
  const pieces: string[] = [];
  let cursor = 0;
  for (const match of text.matchAll(INLINE_WITH_LINKS_RE)) {
    const start = match.index || 0;
    pieces.push(htmlEscape(text.slice(cursor, start)));
    if (match[6] !== undefined) {
      const addressWithMarkers = match[7].trim();
      const address = addressWithMarkers.replace(PATCH_MARKER_RE, "");
      if (!/^https?:\/\/\S+$/.test(address)) fail(file);
      pieces.push(...(addressWithMarkers.match(PATCH_MARKER_RE) || []));
      pieces.push(`<a href="${htmlEscape(address, true)}">${htmlEscape(match[6])}</a>`);
    } else if (match[1] !== undefined) {
      const image = imageWidth(match[1], file);
      const source = match[2];
      imageSource(root, source, file);
      const imageUrl = imagePrefix + source.slice("images/".length);
      const imageMarkup = `<img src="${htmlEscape(imageUrl, true)}" alt="${htmlEscape(image.alt, true)}"${image.width ? ` width="${image.width}"` : ""}>`;
      pieces.push(wrapImages ? `<a class="image-zoom" href="${htmlEscape(imageUrl, true)}">${imageMarkup}</a>` : imageMarkup);
    } else if (match[3] !== undefined) {
      pieces.push(`<strong>${htmlEscape(match[3])}</strong>`);
    } else if (match[4] !== undefined) {
      pieces.push(`<code>${htmlEscape(match[4])}</code>`);
    } else {
      pieces.push(`<em>${htmlEscape(match[5] || "")}</em>`);
    }
    cursor = start + match[0].length;
  }
  pieces.push(htmlEscape(text.slice(cursor)));
  return pieces.join("");
}

function renderBlock(block: MarkdownBlock, root: string, file: string, imagePrefix: string, wrapImages: boolean): string {
  const inline = (text: string) => inlineMarkdown(text, root, file, imagePrefix, wrapImages);
  const lines = (values: string[]) => inline(values.join("\n")).replace(/\n/g, "<br>\n");
  if (block.kind === "heading") return `<h${block.level}>${inline(block.text)}</h${block.level}>`;
  if (block.kind === "list") return `<ul>${block.items.map((item) => `<li>${inline(item)}</li>`).join("")}</ul>`;
  if (block.kind === "quote") return `<blockquote>${lines(block.lines)}</blockquote>`;
  return `<p>${lines(block.lines)}</p>`;
}

function visibleText(value: string): string {
  const withAlt = value.replace(/<img\b[^>]*\balt="([^"]*)"[^>]*>/gi, "$1");
  return withAlt.replace(/<[^>]+>/g, "").replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"');
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

function blockContentBounds(rendered: string): [number, number] {
  const openingEnd = rendered.indexOf(">");
  const closingStart = rendered.lastIndexOf("</");
  return openingEnd < 0 || closingStart <= openingEnd ? [0, rendered.length] : [openingEnd + 1, closingStart];
}

function markBlockContent(rendered: string, opening: string, closing: string): string {
  const [start, end] = blockContentBounds(rendered);
  return rendered.slice(0, start) + opening + rendered.slice(start, end) + closing + rendered.slice(end);
}

function renderPatchedBlocks(renderedBlocks: string[]): string[] {
  const markerPattern = /\u0000guin-patch-(?:start|end)-(\d+)\u0000/g;
  let active: number | undefined;
  return renderedBlocks.map((original) => {
    let rendered = original;
    const markers = [...rendered.matchAll(markerPattern)];
    if (active !== undefined) {
      const endToken = patchEnd(active);
      if (rendered.includes(endToken)) {
        const [start] = blockContentBounds(rendered);
        rendered = rendered.slice(0, start) + patchStart(active) + rendered.slice(start);
        active = undefined;
      } else {
        rendered = markBlockContent(rendered, patchStart(active), patchEnd(active));
        return rendered;
      }
    }
    for (const marker of markers) {
      if (!marker[0].includes("-start-")) continue;
      const index = Number(marker[1]);
      if (!rendered.includes(patchEnd(index))) {
        const [, end] = blockContentBounds(rendered);
        rendered = rendered.slice(0, end) + patchEnd(index) + rendered.slice(end);
        active = index;
      }
      break;
    }
    return rendered;
  });
}

function renderBodyHtml(body: string, root: string, file: string, imagePrefix: string, wrapImages: boolean, state?: PatchState, replacements: Array<[string, string]> = []): string {
  let sourceBody = body;
  if (state?.hasPatches) {
    sourceBody = state.markedBody().body;
  }
  if (replacements.length) {
    sourceBody = applyAnchorReplacements(sourceBody, replacements, file);
  }
  return renderPatchedBlocks(markdownBlocks(sourceBody).map((block) => renderBlock(block, root, file, imagePrefix, wrapImages))).join("\n");
}

function firstParagraphText(body: string, root: string, file: string): string {
  const blocks = markdownBlocks(body);
  const first = blocks.find((block) => block.kind === "paragraph") || blocks[0];
  return first ? visibleText(renderBlock(first, root, file, "", false)) : "";
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
  validatePatchExternalOverlaps(patchStates);
  const links = parseLinks(root, posts, patchStates);
  const site: SiteData = { contentRoot: root, aboutPath: path.join(root, "about.md"), aboutBody: about.body, posts, links, patchStates, shares: parseShares(root, posts), taggings: parseTags(root, posts) };
  for (const post of posts) post.firstText = firstParagraphText(patchStates.get(post.id)!.body, root, post.source);
  return site;
}
