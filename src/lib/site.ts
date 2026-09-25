import fs from "node:fs";
import path from "node:path";

export class BuildError extends Error {}

export type InlineNode =
  | { kind: "text"; value: string }
  | { kind: "strong"; value: string }
  | { kind: "emphasis"; value: string }
  | { kind: "code"; value: string }
  | { kind: "link"; label: string; href: string }
  | { kind: "image"; alt: string; src: string; width?: number };

export type MarkdownBlock =
  | { kind: "heading"; level: number; content: InlineNode[] }
  | { kind: "list"; items: InlineNode[][] }
  | { kind: "quote"; lines: InlineNode[][] }
  | { kind: "paragraph"; lines: InlineNode[][] };

export interface Post {
  id: string;
  source: string;
  fields: Record<string, string>;
  body: string;
  blocks: MarkdownBlock[];
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

export interface SiteData {
  contentRoot: string;
  aboutPath: string;
  about: MarkdownBlock[];
  posts: Post[];
  shares: Map<string, Share[]>;
  taggings: Map<string, Tagging[]>;
}

const TABLES = new Set(["links.jsonl", "patches.jsonl", "shares.jsonl", "tags.jsonl"]);
export const SHARE_PLACES: Record<string, [string, string]> = {
  x: ["X", "x.svg"],
  threads: ["Threads", "threads.svg"],
  linkedin: ["LinkedIn", "linkedin.png"],
  substack: ["Substack", "substack.png"],
  bluesky: ["Bluesky", "bluesky.svg"],
};
const WRITTEN_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/;

function contentRoot(): string {
  return path.resolve(process.env.GUIN_CONTENT_ROOT || path.join(process.cwd(), "content"));
}

function fail(file: string): never {
  throw new BuildError(file);
}

function readUtf8(file: string): string {
  try {
    return fs.readFileSync(file, "utf8");
  } catch {
    fail(file);
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseWritten(value: string, file: string): string {
  if (!WRITTEN_RE.test(value)) fail(file);
  const date = new Date(value);
  if (Number.isNaN(date.getTime()) || date.toISOString().replace(".000Z", "Z") !== value) fail(file);
  return value;
}

function timeId(written: string): string {
  return `${written.slice(0, 4)}${written.slice(5, 7)}${written.slice(8, 10)}-${written.slice(11, 13)}${written.slice(14, 16)}${written.slice(17, 19)}`;
}

function allFiles(directory: string): string[] {
  let entries: fs.Dirent[];
  try {
    entries = fs.readdirSync(directory, { withFileTypes: true });
  } catch (error) {
    if (error?.code === "ENOENT") return [];
    throw error;
  }
  return entries.flatMap((entry) => {
    const full = path.join(directory, entry.name);
    return entry.isDirectory() ? allFiles(full) : entry.isFile() ? [full] : [];
  });
}

function imageInfo(alt: string, file: string): { alt: string; width?: number } {
  const match = /^(.*)\|([0-9]+)$/.exec(alt);
  if (!match) return { alt };
  const width = Number(match[2]);
  if (width < 1 || width > 9999) fail(file);
  return { alt: match[1], width };
}

function imageSource(root: string, source: string, file: string): void {
  const parts = source.split("/");
  if (source.startsWith("/") || parts.length < 2 || parts[0] !== "images" || parts.some((part) => !part || part === "." || part === "..")) fail(file);
  const candidate = path.join(root, ...parts);
  try {
    if (!fs.statSync(candidate).isFile()) fail(file);
  } catch {
    fail(file);
  }
}

const INLINE = /!\[([^\]]*)\]\(([^)]*)\)|\*\*(.+?)\*\*|`([^`]+)`|\*(?!\s)(.+?)(?<!\s)\*/g;
const INLINE_WITH_LINKS = new RegExp(String.raw`${INLINE.source}|\[([^\]]*)\]\(([^)]*)\)`, "g");
const HEADING = /^(#{1,3})[ \t]+(.*)$/;

function parseInline(text: string, root: string, file: string): InlineNode[] {
  const nodes: InlineNode[] = [];
  let cursor = 0;
  for (const match of text.matchAll(INLINE_WITH_LINKS)) {
    const start = match.index ?? 0;
    if (start > cursor) nodes.push({ kind: "text", value: text.slice(cursor, start) });
    if (match[6] !== undefined) {
      const href = match[7].trim();
      if (!/^https?:\/\/\S+$/.test(href)) fail(file);
      nodes.push({ kind: "link", label: match[6], href });
    } else if (match[1] !== undefined) {
      const image = imageInfo(match[1], file);
      imageSource(root, match[2], file);
      nodes.push({ kind: "image", alt: image.alt, src: match[2], ...(image.width ? { width: image.width } : {}) });
    } else if (match[3] !== undefined) {
      nodes.push({ kind: "strong", value: match[3] });
    } else if (match[4] !== undefined) {
      nodes.push({ kind: "code", value: match[4] });
    } else {
      nodes.push({ kind: "emphasis", value: match[5] || "" });
    }
    cursor = start + match[0].length;
  }
  if (cursor < text.length) nodes.push({ kind: "text", value: text.slice(cursor) });
  return nodes;
}

function inlineText(nodes: InlineNode[]): string {
  return nodes.map((node) => {
    if (node.kind === "image") return node.alt;
    if (node.kind === "link") return node.label;
    return node.value;
  }).join("");
}

function markdownBlocks(body: string, root: string, file: string): MarkdownBlock[] {
  const lines = body.replace(/^\n+|\n+$/g, "").split("\n");
  const blocks: MarkdownBlock[] = [];
  let index = 0;
  while (index < lines.length) {
    if (!lines[index].trim()) {
      index += 1;
      continue;
    }
    const heading = HEADING.exec(lines[index]);
    if (heading) {
      blocks.push({ kind: "heading", level: heading[1].length, content: parseInline(heading[2], root, file) });
      index += 1;
      continue;
    }
    if (lines[index].startsWith("- ")) {
      const items: InlineNode[][] = [];
      while (index < lines.length && lines[index].startsWith("- ")) items.push(parseInline(lines[index++].slice(2), root, file));
      blocks.push({ kind: "list", items });
      continue;
    }
    if (lines[index].startsWith("> ")) {
      const quoted: InlineNode[][] = [];
      while (index < lines.length && lines[index].startsWith("> ")) quoted.push(parseInline(lines[index++].slice(2), root, file));
      blocks.push({ kind: "quote", lines: quoted });
      continue;
    }
    const paragraph: InlineNode[][] = [];
    while (index < lines.length && lines[index].trim()) paragraph.push(parseInline(lines[index++], root, file));
    blocks.push({ kind: "paragraph", lines: paragraph });
  }
  return blocks;
}

function firstText(blocks: MarkdownBlock[]): string {
  const first = blocks.find((block) => block.kind === "paragraph");
  return first ? first.lines.map(inlineText).join("\n") : "";
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
  const blocks = markdownBlocks(body, root, file);
  return {
    id,
    source: file,
    fields,
    body,
    blocks,
    firstText: firstText(blocks),
    type: fields.type as Post["type"],
    written: fields.written,
    title: fields.title || "",
  };
}

function parsePosts(root: string): Post[] {
  const posts: Post[] = [];
  const byId = new Map<string, string>();
  for (const file of allFiles(root).sort()) {
    const relative = path.relative(root, file).split(path.sep);
    const relativeName = relative.join("/");
    if (relative[0] === "images" || relativeName === "about.md" || TABLES.has(relativeName)) continue;
    const post = parsePost(file, root);
    if (byId.has(post.id)) fail(file);
    byId.set(post.id, file);
    posts.push(post);
  }
  return posts;
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

function validTag(tag: string): boolean {
  return tag.length > 0 && tag.length <= 40 && tag === tag.trim() && ![".", ".."].includes(tag) && !(/[\\/\n\r]/.test(tag));
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
    const post = key.split("\u0000", 1)[0];
    result.set(post, [...(result.get(post) || []), { tag: key.slice(post.length + 1), at: value.at, why: value.why }]);
  }
  return result;
}

function parseAbout(root: string): { path: string; blocks: MarkdownBlock[] } {
  const file = path.join(root, "about.md");
  if (!fs.existsSync(file)) fail(file);
  const body = readUtf8(file);
  if (!body.trim()) fail(file);
  return { path: file, blocks: markdownBlocks(body, root, file) };
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
  return site.posts
    .filter((post) => (site.taggings.get(post.id) || []).some((item) => item.tag === tag))
    .sort((a, b) => b.written.localeCompare(a.written));
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

export function loadSite(): SiteData {
  const root = contentRoot();
  const about = parseAbout(root);
  const posts = parsePosts(root);
  return {
    contentRoot: root,
    aboutPath: about.path,
    about: about.blocks,
    posts,
    shares: parseShares(root, posts),
    taggings: parseTags(root, posts),
  };
}
