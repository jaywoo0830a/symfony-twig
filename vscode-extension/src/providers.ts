import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { execFile } from 'child_process';
import { promisify } from 'util';

const execFileAsync = promisify(execFile);
import { CliCommand } from './extension';
import { findAnalyzerCommand } from './extension';
import { isTwigFile, isInsideTwigTag, isInsideHtmlTag } from './extension';

// ── Data loaded from YAML-generated JSON ──
import hoverDataJson from './data/hover-data.json';
import signaturesJson from './data/signatures.json';
import completionNamesJson from './data/completion-names.json';
import endTagMapJson from './data/end-tag-map.json';
import htmlHoverJson from './data/html-hover.json';

// 9. Formatting provider
// ═══════════════════════════════════════════════════════════════════════

export class TwigFormattingProvider implements vscode.DocumentFormattingEditProvider {
    async provideDocumentFormattingEdits(
        document: vscode.TextDocument,
        _options: vscode.FormattingOptions,
        _token: vscode.CancellationToken,
    ): Promise<vscode.TextEdit[]> {
        const cmd = findAnalyzerCommand();
        const formatted = await this.formatWithCli(cmd, document);

        if (formatted === undefined) return [];

        const fullRange = new vscode.Range(
            document.positionAt(0),
            document.positionAt(document.getText().length),
        );
        return [vscode.TextEdit.replace(fullRange, formatted)];
    }

    private async formatWithCli(
        cmd: CliCommand,
        document: vscode.TextDocument,
    ): Promise<string | undefined> {
        // Docker stdin mode: pipe content through container
        const formatArgs = [...cmd.args, 'format', '--stdin'];
        try {
            const cp = require('child_process');
            const result = cp.spawnSync(cmd.cmd, formatArgs, {
                input: document.getText(),
                timeout: 30000,
                env: cmd.env,
                encoding: 'utf-8',
            });
            if (result.status === 0 && result.stdout) {
                return result.stdout;
            }
            return undefined;
        } catch {
            return undefined;
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════
// 10. Hover provider — Twig built-in documentation
// ═══════════════════════════════════════════════════════════════════════

interface BuiltinEntry {
    readonly description: string;
    readonly since: string;
    readonly example: string;
    readonly link: string;
}

export const TWIG_DOCS = 'https://twig.symfony.com/doc/3.x';

// Loaded from YAML-generated JSON (see scripts/generate-vscode-data.py)
export const BUILTIN_HOVER_DATA: Record<string, BuiltinEntry> = hoverDataJson as Record<string, BuiltinEntry>;

// End-tag map is auto-derived from block tags in the YAML
export const END_TAG_MAP: Record<string, string> = (endTagMapJson as any).endTagMap as Record<string, string>;

export class TwigHoverProvider implements vscode.HoverProvider {
    provideHover(
        document: vscode.TextDocument,
        position: vscode.Position,
    ): vscode.ProviderResult<vscode.Hover> {
        // Try exact word at cursor first, then broaden to dot-paths
        let range = document.getWordRangeAtPosition(position, /\w+/);
        if (range === undefined) {
            // fallback: dot-separated paths like node.author.credentials
            range = document.getWordRangeAtPosition(position, /[\w.]+/);
        }
        if (range === undefined) return null;

        const word = document.getText(range);

        // Use end of the word range (not cursor) so hover over "da" finds "date"
        const lineUpToWord = document.lineAt(range.end.line).text.substring(0, range.end.character);

        // Check for filter: word after | with optional whitespace
        const filterMatch = lineUpToWord.match(/\|\s*([\w.]+)$/);
        const lookup = filterMatch !== null ? filterMatch[1] : word;

        const entry = BUILTIN_HOVER_DATA[lookup];
        if (entry === undefined) return null;

        const content = new vscode.MarkdownString(
            `### \`${lookup}\`\n\n${entry.description}\n\n` +
            `> Since Twig ${entry.since}  \n` +
            `> Example: \`${entry.example}\`  \n\n` +
            `[📖 Twig Docs](${entry.link})`,
        );
        content.isTrusted = true;

        return new vscode.Hover(content, range);
    }
}

// ═══════════════════════════════════════════════════════════════════════
// 10b. HTML Hover provider — MDN documentation for HTML5 elements/attributes
// ═══════════════════════════════════════════════════════════════════════

interface HtmlHoverEntry {
    readonly description: string;
    readonly category?: string;
    readonly link: string;
}

const HTML_ELEMENTS: Record<string, HtmlHoverEntry> = (htmlHoverJson as any).elements;
const HTML_ATTRS: Record<string, HtmlHoverEntry> = (htmlHoverJson as any).attributes;

export class HtmlHoverProvider implements vscode.HoverProvider {
    provideHover(
        document: vscode.TextDocument,
        position: vscode.Position,
    ): vscode.ProviderResult<vscode.Hover> {
        // Check if we're inside an HTML tag (not inside {{ }} or {% %})
        const linePrefix = document.lineAt(position).text.substring(0, position.character);
        if (isInsideTwigTag(linePrefix)) return null;

        // Try to match an HTML tag name at cursor
        const tagRange = document.getWordRangeAtPosition(position, /<\w+|[a-zA-Z][\w-]*/);
        if (!tagRange) return null;

        const word = document.getText(tagRange);
        // Strip leading < if present
        const name = word.startsWith('<') ? word.slice(1).toLowerCase() : word.toLowerCase();

        // Check elements
        const elementEntry = HTML_ELEMENTS[name];
        if (elementEntry) {
            const category = elementEntry.category ? `\n\n*Category:* ${elementEntry.category}` : '';
            const content = new vscode.MarkdownString(
                `### <${name}>\n\n${elementEntry.description}${category}\n\n[📖 MDN Docs](${elementEntry.link})`,
            );
            content.isTrusted = true;
            return new vscode.Hover(content, tagRange);
        }

        // Check attributes (after space inside an HTML tag)
        if (isInsideHtmlTag(linePrefix)) {
            const attrEntry = HTML_ATTRS[name] || HTML_ATTRS[word.replace(/^data-.*/, 'data-*')] || HTML_ATTRS[word.replace(/^aria-.*/, 'aria-*')];
            if (attrEntry) {
                const content = new vscode.MarkdownString(
                    `### ${word}\n\n${attrEntry.description}\n\n[📖 MDN Docs](${attrEntry.link})`,
                );
                content.isTrusted = true;
                return new vscode.Hover(content, tagRange);
            }
        }

        return null;
    }
}

// ═══════════════════════════════════════════════════════════════════════
// 11. Definition provider — go-to template for extends/include/embed
// ═══════════════════════════════════════════════════════════════════════

export const TEMPLATE_PATH_TAGS = new Set(['extends', 'include', 'embed', 'import', 'from', 'use']);

// Tags/functions that reference template paths
const TEMPLATE_PATH_FUNCTIONS = new Set(['include', 'source', 'block']);

export class TwigDefinitionProvider implements vscode.DefinitionProvider {
    provideDefinition(
        document: vscode.TextDocument,
        position: vscode.Position,
    ): vscode.ProviderResult<vscode.Definition | vscode.LocationLink[]> {
        const line = document.lineAt(position).text;
        const beforeCursor = line.substring(0, position.character);
        const afterCursor = line.substring(position.character);

        // 1. {% tag 'path' %} — template path in tag
        const tagMatch = beforeCursor.match(/\{%\s*(\w+)\s*(['"])([^'"]*)$/);
        if (tagMatch !== null && TEMPLATE_PATH_TAGS.has(tagMatch[1])) {
            return this.resolveTemplatePath(document, beforeCursor, afterCursor, tagMatch[3]);
        }

        // 2. {{ include('path') }} — template path in function call
        const funcMatch = beforeCursor.match(/\b(include|source)\s*\(\s*(['"])([^'"]*)$/);
        if (funcMatch !== null) {
            return this.resolveTemplatePath(document, beforeCursor, afterCursor, funcMatch[3]);
        }

        // 3. {{ path('route_name') }} — route name (navigate to route definition if found)
        const routeMatch = beforeCursor.match(/\b(?:path|url)\s*\(\s*(['"])([^'"]*)$/);
        if (routeMatch !== null) {
            return this.resolveRouteName(document, beforeCursor, afterCursor, routeMatch[2]);
        }

        // 4. {{ asset('path') }} — asset path
        const assetMatch = beforeCursor.match(/\basset\s*\(\s*(['"])([^'"]*)$/);
        if (assetMatch !== null) {
            return this.resolveAssetPath(document, beforeCursor, afterCursor, assetMatch[2]);
        }

        return null;
    }

    private resolveTemplatePath(
        document: vscode.TextDocument,
        before: string, after: string, partial: string,
    ): vscode.ProviderResult<vscode.Definition | vscode.LocationLink[]> {
        const restMatch = after.match(/^([^'"]*)(['"])/);
        const fullPath = restMatch !== null ? partial + restMatch[1] : partial;

        const clean = fullPath.replace(/^['"]|['"]$/g, '');
        const baseDir = path.dirname(document.uri.fsPath);
        const workspaceDir = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? baseDir;

        // Strategy 1: @Bundle notation → convert to paths
        if (clean.startsWith('@')) {
            const atPath = clean.replace(/^@(\w+)\//, 'bundles/$1/');
            const twigDir = path.join(workspaceDir, 'templates', atPath);
            if (fs.existsSync(twigDir)) return new vscode.Location(vscode.Uri.file(twigDir), new vscode.Position(0, 0));
            const srcDir = path.join(workspaceDir, 'src', atPath, 'Resources', 'views');
            if (fs.existsSync(srcDir)) return new vscode.Location(vscode.Uri.file(srcDir), new vscode.Position(0, 0));
        }

        // Strategy 2: Relative to current file
        const relative = path.join(baseDir, clean);
        if (fs.existsSync(relative)) return new vscode.Location(vscode.Uri.file(relative), new vscode.Position(0, 0));

        // Strategy 3: With .twig extensions
        if (!clean.endsWith('.twig') && !clean.endsWith('.html.twig')) {
            for (const ext of ['.twig', '.html.twig']) {
                const p = path.join(baseDir, clean + ext);
                if (fs.existsSync(p)) return new vscode.Location(vscode.Uri.file(p), new vscode.Position(0, 0));
            }
        }

        // Strategy 4: templates/ directory (Symfony convention)
        for (const templatesDir of ['templates', 'Resources/views']) {
            const p = path.join(workspaceDir, templatesDir, clean);
            if (fs.existsSync(p)) return new vscode.Location(vscode.Uri.file(p), new vscode.Position(0, 0));
            if (!clean.endsWith('.twig')) {
                for (const ext of ['.twig', '.html.twig']) {
                    const pe = path.join(workspaceDir, templatesDir, clean + ext);
                    if (fs.existsSync(pe)) return new vscode.Location(vscode.Uri.file(pe), new vscode.Position(0, 0));
                }
            }
        }

        // Strategy 5: Namespaced paths (e.g., 'admin/template' → templates/admin/template.html.twig)
        if (clean.includes('/')) {
            for (const templatesDir of ['templates', 'Resources/views']) {
                const p = path.join(workspaceDir, templatesDir, clean);
                if (fs.existsSync(p)) return new vscode.Location(vscode.Uri.file(p), new vscode.Position(0, 0));
                for (const ext of ['.twig', '.html.twig']) {
                    const pe = path.join(workspaceDir, templatesDir, clean + ext);
                    if (fs.existsSync(pe)) return new vscode.Location(vscode.Uri.file(pe), new vscode.Position(0, 0));
                }
            }
        }

        return null;
    }

    private resolveRouteName(
        document: vscode.TextDocument,
        before: string, after: string, partial: string,
    ): vscode.ProviderResult<vscode.Definition | vscode.LocationLink[]> {
        // Find route definitions in YAML/PHP/Attribute files
        const restMatch = after.match(/^([^'"]*)(['"])/);
        const routeName = restMatch !== null ? partial + restMatch[1] : partial;
        const workspaceDir = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;

        if (workspaceDir === undefined) return null;

        // Search for route definition in common locations
        const searchPaths = [
            path.join(workspaceDir, 'config', 'routes'),
            path.join(workspaceDir, 'config'),
            path.join(workspaceDir, 'src'),
        ];

        for (const searchPath of searchPaths) {
            if (!fs.existsSync(searchPath)) continue;
            try {
                const files = this.findRouteDefinition(searchPath, routeName);
                if (files.length > 0) {
                    return new vscode.Location(vscode.Uri.file(files[0]), new vscode.Position(0, 0));
                }
            } catch { /* ignore */ }
        }

        return null;
    }

    private findRouteDefinition(dir: string, routeName: string): string[] {
        const results: string[] = [];
        try {
            const entries = fs.readdirSync(dir, { withFileTypes: true });
            for (const entry of entries) {
                const fullPath = path.join(dir, entry.name);
                if (entry.isDirectory()) {
                    results.push(...this.findRouteDefinition(fullPath, routeName));
                } else if (entry.isFile() && /\.(yaml|yml|php|xml)$/.test(entry.name)) {
                    const content = fs.readFileSync(fullPath, 'utf-8');
                    // YAML: name: or path: pattern
                    // PHP: #[Route('/path', name: 'route_name')]
                    // XML: <route id="route_name"
                    if (content.includes(`'${routeName}'`) ||
                        content.includes(`"${routeName}"`) ||
                        content.includes(`name: ${routeName}`) ||
                        content.includes(`id="${routeName}"`)) {
                        results.push(fullPath);
                    }
                }
            }
        } catch { /* ignore */ }
        return results;
    }

    private resolveAssetPath(
        document: vscode.TextDocument,
        before: string, after: string, partial: string,
    ): vscode.ProviderResult<vscode.Definition | vscode.LocationLink[]> {
        const restMatch = after.match(/^([^'"]*)(['"])/);
        const assetPath = restMatch !== null ? partial + restMatch[1] : partial;
        const workspaceDir = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;

        if (workspaceDir === undefined) return null;

        // Look in public/ directory (Symfony convention)
        const publicPath = path.join(workspaceDir, 'public', assetPath);
        if (fs.existsSync(publicPath)) {
            return new vscode.Location(vscode.Uri.file(publicPath), new vscode.Position(0, 0));
        }

        // Also try assets/ directory
        const assetsPath = path.join(workspaceDir, 'assets', assetPath);
        if (fs.existsSync(assetsPath)) {
            return new vscode.Location(vscode.Uri.file(assetsPath), new vscode.Position(0, 0));
        }

        return null;
    }
}

// ═══════════════════════════════════════════════════════════════════════
// 12. Completion provider — Twig keywords
// ═══════════════════════════════════════════════════════════════════════

// ── context scanner: walks backward from cursor to find which Twig scope we're in ──
type TwigContext = 'tag' | 'expression' | 'filter' | 'html';

function getTwigContext(document: vscode.TextDocument, position: vscode.Position): TwigContext {
    const text = document.getText();
    const offset = document.offsetAt(position);

    // scan backward to find the nearest unclosed {{, {%, or | pipe
    let depth = 0;
    let tagStart = -1;
    let pipePos = -1;

    for (let i = offset - 1; i >= 0; i--) {
        const ch = text[i];
        if (ch === '}' && i > 0 && text[i - 1] === '}') {
            // }} closes expression — skip past it
            depth++;
            i--; // skip second }
            continue;
        }
        if (ch === '%' && i > 0 && text[i - 1] === '%') {
            // %} closes tag — skip
            depth++;
            i--;
            continue;
        }
        if (ch === '{' && i > 0 && text[i - 1] === '{') {
            // {{ opens expression
            if (depth > 0) { depth--; i--; continue; }
            tagStart = i - 1; // position of first {
            break;
        }
        if (ch === '%' && i > 0 && text[i - 1] === '{') {
            // {% opens tag
            if (depth > 0) { depth--; i--; continue; }
            tagStart = i - 1;
            break;
        }
        if (ch === '|' && pipePos < 0) {
            pipePos = i;
        }
    }

    // Determine context
    if (tagStart >= 0 && text[tagStart + 1] === '%') {
        return 'tag';           // inside {% ... %}
    }
    if (tagStart >= 0 && text[tagStart + 1] === '{') {
        if (pipePos >= 0 && pipePos > tagStart) return 'filter'; // after | inside {{
        return 'expression';    // inside {{ ... }}
    }
    return 'html';              // outside any twig tag
}

// ── completion item builders (with hover-doc integration) ──

function makeTagItem(name: string, block: boolean): vscode.CompletionItem {
    const item = new vscode.CompletionItem(name, vscode.CompletionItemKind.Keyword);
    item.detail = block ? 'Twig Block Tag' : 'Twig Tag';
    item.filterText = name;
    item.sortText = '0_' + name;
    if (block) {
        item.insertText = new vscode.SnippetString(`${name} $1 %}\n$0\n{% end${name} %}`);
    } else {
        item.insertText = new vscode.SnippetString(`${name} $1 %}`);
    }
    const doc = BUILTIN_HOVER_DATA[name];
    if (doc) item.documentation = new vscode.MarkdownString(`**${doc.description}**\n\n${doc.example}\n\nSince: ${doc.since}\n\n[📖 Docs](${doc.link})`);
    return item;
}

function makeFilterItem(name: string): vscode.CompletionItem {
    const item = new vscode.CompletionItem(name, vscode.CompletionItemKind.Method);
    item.detail = 'Twig Filter';
    item.filterText = name;
    item.sortText = '1_' + name;
    item.insertText = name;
    const doc = BUILTIN_HOVER_DATA[name];
    if (doc) item.documentation = new vscode.MarkdownString(`**${doc.description}**\n\n${doc.example}\n\nSince: ${doc.since}\n\n[📖 Docs](${doc.link})`);
    return item;
}

function makeFunctionItem(name: string): vscode.CompletionItem {
    const item = new vscode.CompletionItem(name, vscode.CompletionItemKind.Function);
    item.detail = 'Twig Function';
    item.filterText = name;
    item.sortText = '2_' + name;
    item.insertText = new vscode.SnippetString(`${name}($1)`);
    const doc = BUILTIN_HOVER_DATA[name];
    if (doc) item.documentation = new vscode.MarkdownString(`**${doc.description}**\n\n${doc.example}\n\nSince: ${doc.since}\n\n[📖 Docs](${doc.link})`);
    return item;
}

// ── static completion lists (from YAML-generated JSON) ──

const BLOCK_TAGS: readonly string[] = (completionNamesJson as any).blockTags;
const INLINE_TAGS: readonly string[] = (completionNamesJson as any).inlineTags;
const TAG_COMPLETIONS: vscode.CompletionItem[] = [
    ...BLOCK_TAGS.map(t => makeTagItem(t, true)),
    ...INLINE_TAGS.map(t => makeTagItem(t, false)),
];

const FILTER_NAMES: readonly string[] = (completionNamesJson as any).filterNames;
const FILTER_COMPLETIONS: vscode.CompletionItem[] = FILTER_NAMES.map(makeFilterItem);

const FUNCTION_NAMES: readonly string[] = (completionNamesJson as any).functionNames;
const FUNCTION_COMPLETIONS: vscode.CompletionItem[] = FUNCTION_NAMES.map(makeFunctionItem);

// ── provider ──

export class TwigCompletionProvider implements vscode.CompletionItemProvider {
    provideCompletionItems(
        document: vscode.TextDocument,
        position: vscode.Position,
        _token: vscode.CancellationToken,
    ): vscode.ProviderResult<vscode.CompletionItem[]> {
        const ctx = getTwigContext(document, position);

        switch (ctx) {
            case 'tag':
                // inside {% %} — suggest tags, with "end*" variants
                return [
                    ...TAG_COMPLETIONS,
                    ...BLOCK_TAGS.map(t => {
                        const item = new vscode.CompletionItem(`end${t}`, vscode.CompletionItemKind.Keyword);
                        item.detail = 'Twig End Tag';
                        item.filterText = `end${t}`;
                        item.sortText = '9_' + t;
                        item.insertText = new vscode.SnippetString(`end${t} %}`);
                        return item;
                    }),
                ];
            case 'filter':
                // after | pipe — suggest filters only
                return FILTER_COMPLETIONS;
            case 'expression':
                // inside {{ }} but not after | — suggest functions + filters
                return [...FUNCTION_COMPLETIONS, ...FILTER_COMPLETIONS];
            default:
                // outside twig tags (HTML) — suggest tags
                return TAG_COMPLETIONS;
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════
// 13. Symbol + Folding providers
// ═══════════════════════════════════════════════════════════════════════

export class TwigSymbolProvider implements vscode.DocumentSymbolProvider {
    provideDocumentSymbols(document: vscode.TextDocument): vscode.ProviderResult<vscode.SymbolInformation[] | vscode.DocumentSymbol[]> {
        const symbols: vscode.DocumentSymbol[] = [];
        for (let i = 0; i < document.lineCount; i++) {
            const line = document.lineAt(i).text;
            const blockMatch = line.match(/\{%-?\s*block\s+(\w+)/);
            const macroMatch = line.match(/\{%-?\s*macro\s+(\w+)/);
            if (blockMatch) {
                const range = new vscode.Range(i, 0, i, line.length);
                symbols.push(new vscode.DocumentSymbol(blockMatch[1], 'Block', vscode.SymbolKind.Module, range, range));
            } else if (macroMatch) {
                const range = new vscode.Range(i, 0, i, line.length);
                symbols.push(new vscode.DocumentSymbol(macroMatch[1], 'Macro', vscode.SymbolKind.Function, range, range));
            }
        }
        return symbols;
    }
}

export class TwigFoldingProvider implements vscode.FoldingRangeProvider {
    provideFoldingRanges(document: vscode.TextDocument): vscode.ProviderResult<vscode.FoldingRange[]> {
        const folds: vscode.FoldingRange[] = [];
        const stack: { start: number; tag: string }[] = [];
        const startRe = /\{%-?\s*(block|for|if|macro|apply|autoescape|embed|cache|deprecated|guard|sandbox|set|verbatim|with)\b/;
        const endRe = /\{%-?\s*(endblock|endfor|endif|endmacro|endapply|endautoescape|endembed|endcache|enddeprecated|endguard|endsandbox|endset|endverbatim|endwith)\b/;
        for (let i = 0; i < document.lineCount; i++) {
            const line = document.lineAt(i).text;
            const sm = line.match(startRe);
            if (sm && !(sm[1] === 'set' && line.includes('endset'))) stack.push({ start: i, tag: sm[1] });
            const em = line.match(endRe);
            if (em && stack.length > 0) {
                const o = stack.pop()!;
                if (o.start < i) folds.push(new vscode.FoldingRange(o.start, i, vscode.FoldingRangeKind.Region));
            }
        }
        return folds;
    }
}

// ═══════════════════════════════════════════════════════════════════════
// 14. Signature help
// ═══════════════════════════════════════════════════════════════════════

// ── Signatures loaded from YAML-generated JSON ──
const _sigData: Record<string, { label: string; params: { name: string; description: string }[] }> = signaturesJson as any;

const TWIG_SIGNATURES: Record<string, { label: string; params: vscode.ParameterInformation[] }> = {};
for (const [name, info] of Object.entries(_sigData)) {
    TWIG_SIGNATURES[name] = {
        label: info.label,
        params: (info.params || []).map((p: any) => new vscode.ParameterInformation(p.name, p.description)),
    };
}

export class TwigSignatureHelpProvider implements vscode.SignatureHelpProvider {
    provideSignatureHelp(document: vscode.TextDocument, position: vscode.Position): vscode.ProviderResult<vscode.SignatureHelp> {
        const lp = document.lineAt(position).text.substring(0, position.character);
        const m = lp.match(/(\w+)\s*\($/);
        if (!m) return null;
        const s = TWIG_SIGNATURES[m[1]];
        if (!s) return null;
        const h = new vscode.SignatureHelp();
        h.signatures = [new vscode.SignatureInformation(s.label, new vscode.MarkdownString(`**${m[1]}** — Twig function`))];
        h.signatures[0].parameters = s.params;
        h.activeSignature = 0;
        h.activeParameter = Math.min((lp.substring(m[0].length).match(/,/g) ?? []).length, s.params.length - 1);
        return h;
    }
}

// ═══════════════════════════════════════════════════════════════════════
// 15. Code Actions (Quick Fix)
// ═══════════════════════════════════════════════════════════════════════

export class TwigCodeActionProvider implements vscode.CodeActionProvider {
    provideCodeActions(
        document: vscode.TextDocument,
        range: vscode.Range | vscode.Selection,
        context: vscode.CodeActionContext,
    ): vscode.ProviderResult<(vscode.CodeAction | vscode.Command)[]> {
        const actions: vscode.CodeAction[] = [];

        for (const diag of context.diagnostics) {
            if (diag.source !== 'twig-analyzer') continue;

            const code = typeof diag.code === 'string' ? diag.code : '';

            // Quick fix: add |e escape filter
            if (code === 'TWIG-RAW-FILTER' || code === 'TWIG-MISSING-ESCAPE') {
                const fix = new vscode.CodeAction('Add |e escape filter', vscode.CodeActionKind.QuickFix);
                fix.diagnostics = [diag];
                fix.edit = new vscode.WorkspaceEdit();
                const line = document.lineAt(diag.range.end.line);
                const afterEnd = line.text.substring(diag.range.end.character);
                // Find }} to insert before
                const endPos = line.text.indexOf('}}', diag.range.end.character);
                if (endPos >= 0) {
                    fix.edit.insert(document.uri, new vscode.Position(diag.range.end.line, endPos), '|e');
                }
                actions.push(fix);
            }

            // Quick fix: wrap in {% if defined %}
            if (code === 'TWIG-UNDEFINED-VAR') {
                const fix = new vscode.CodeAction('Wrap in {% if defined %}', vscode.CodeActionKind.QuickFix);
                fix.diagnostics = [diag];
                fix.edit = new vscode.WorkspaceEdit();
                const line = document.lineAt(diag.range.start.line);
                fix.edit.insert(document.uri, new vscode.Position(diag.range.start.line, 0),
                    `{% if ${document.getText(diag.range)} is defined %}\n`);
                fix.edit.insert(document.uri, new vscode.Position(diag.range.end.line, line.text.length),
                    `\n{% endif %}`);
                actions.push(fix);
            }

            // Quick fix: disable rule
            if (code !== 'TWIG-PARSE-ERROR' && code !== 'TWIG-INTERNAL-ERROR') {
                const disable = new vscode.CodeAction(`Disable rule '${code}'`, vscode.CodeActionKind.QuickFix);
                disable.command = {
                    command: 'workbench.action.openSettings',
                    title: 'Disable Rule',
                    arguments: ['twigAnalyzer.disabledRules'],
                };
                disable.diagnostics = [diag];
                actions.push(disable);
            }
        }

        return actions;
    }
}

// ═══════════════════════════════════════════════════════════════════════
// 16. Document Highlight — matching {% if %} ↔ {% endif %}
// ═══════════════════════════════════════════════════════════════════════

// ── Highlight pairs derived from end-tag-map ──
const HIGHLIGHT_PAIRS: Record<string, string> = {};
const _etm: Record<string, string> = (endTagMapJson as any).endTagMap || {};
for (const [start, end] of Object.entries(_etm)) {
    HIGHLIGHT_PAIRS[start] = end;
    HIGHLIGHT_PAIRS[end] = start;
}

export class TwigHighlightProvider implements vscode.DocumentHighlightProvider {
    provideDocumentHighlights(
        document: vscode.TextDocument,
        position: vscode.Position,
    ): vscode.ProviderResult<vscode.DocumentHighlight[]> {
        const wordRange = document.getWordRangeAtPosition(position, /\w+/);
        if (!wordRange) return [];
        const word = document.getText(wordRange);
        const pair = HIGHLIGHT_PAIRS[word];
        if (!pair) return [];

        const highlights: vscode.DocumentHighlight[] = [];
        highlights.push(new vscode.DocumentHighlight(wordRange, vscode.DocumentHighlightKind.Read));

        // Find matching pair
        const pattern = new RegExp(`\\{%-?\\s*${pair}\\b`, 'g');
        for (let i = 0; i < document.lineCount; i++) {
            const line = document.lineAt(i).text;
            let match: RegExpExecArray | null;
            while ((match = pattern.exec(line)) !== null) {
                const start = match.index + match[0].indexOf(pair);
                const r = new vscode.Range(i, start, i, start + pair.length);
                highlights.push(new vscode.DocumentHighlight(r, vscode.DocumentHighlightKind.Text));
            }
        }

        return highlights;
    }
}

// ═══════════════════════════════════════════════════════════════════════
// 17. Rename Provider — rename blocks/macros (F2)
// ═══════════════════════════════════════════════════════════════════════

export class TwigRenameProvider implements vscode.RenameProvider {
    provideRenameEdits(
        document: vscode.TextDocument,
        position: vscode.Position,
        newName: string,
    ): vscode.ProviderResult<vscode.WorkspaceEdit> {
        const wordRange = document.getWordRangeAtPosition(position, /\w+/);
        if (!wordRange) return null;
        const word = document.getText(wordRange);

        // Check context: is this in {% block NAME %} or {% endblock NAME %}?
        const line = document.lineAt(position).text;
        const isBlockName = /\{%-?\s*(?:block|endblock)\s+\w*$/.test(line.substring(0, position.character)) ||
                            /\{%-?\s*(?:macro|endmacro)\s+\w*$/.test(line.substring(0, position.character));

        if (!isBlockName) return null;

        const edit = new vscode.WorkspaceEdit();
        const pattern = new RegExp(`(\\{%-?\\s*(?:block|endblock)\\s+)${word}\\b`, 'g');

        for (let i = 0; i < document.lineCount; i++) {
            const lineText = document.lineAt(i).text;
            let match: RegExpExecArray | null;
            while ((match = pattern.exec(lineText)) !== null) {
                const start = match.index + match[1].length;
                const r = new vscode.Range(i, start, i, start + word.length);
                edit.replace(document.uri, r, newName);
            }
        }

        return edit;
    }

    prepareRename?(
        document: vscode.TextDocument,
        position: vscode.Position,
    ): vscode.ProviderResult<vscode.Range | { range: vscode.Range; placeholder: string }> {
        const wordRange = document.getWordRangeAtPosition(position, /\w+/);
        if (!wordRange) throw new Error('Cannot rename');
        const word = document.getText(wordRange);
        const line = document.lineAt(position).text;
        if (/\{%-?\s*(?:block|endblock|macro|endmacro)\s+\w*$/.test(line.substring(0, position.character))) {
            return wordRange;
        }
        throw new Error('Cannot rename');
    }
}

// ═══════════════════════════════════════════════════════════════════════
// 18. Color Provider — CSS color previews in Twig
// ═══════════════════════════════════════════════════════════════════════

export class TwigColorProvider implements vscode.DocumentColorProvider {
    provideDocumentColors(document: vscode.TextDocument): vscode.ProviderResult<vscode.ColorInformation[]> {
        const colors: vscode.ColorInformation[] = [];
        const hexRe = /#[0-9a-fA-F]{3,8}\b/g;
        const rgbRe = /rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)/g;
        const rgbaRe = /rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)/g;

        for (let i = 0; i < document.lineCount; i++) {
            const line = document.lineAt(i).text;
            
            for (const re of [hexRe, rgbRe]) {
                let match: RegExpExecArray | null;
                while ((match = re.exec(line)) !== null) {
                    const color = this.parseColor(match[0]);
                    if (color) {
                        const start = match.index;
                        const end = start + match[0].length;
                        colors.push(new vscode.ColorInformation(
                            new vscode.Range(i, start, i, end), color,
                        ));
                    }
                }
            }
        }
        return colors;
    }

    provideColorPresentations(
        color: vscode.Color,
    ): vscode.ProviderResult<vscode.ColorPresentation[]> {
        const r = Math.round(color.red * 255);
        const g = Math.round(color.green * 255);
        const b = Math.round(color.blue * 255);
        return [{ label: `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}` }];
    }

    private parseColor(text: string): vscode.Color | undefined {
        if (text.startsWith('#')) {
            const h = text.substring(1);
            if (h.length === 3) {
                return new vscode.Color(
                    parseInt(h[0]+h[0], 16) / 255,
                    parseInt(h[1]+h[1], 16) / 255,
                    parseInt(h[2]+h[2], 16) / 255, 1,
                );
            }
            if (h.length === 6) {
                return new vscode.Color(
                    parseInt(h.substring(0,2), 16) / 255,
                    parseInt(h.substring(2,4), 16) / 255,
                    parseInt(h.substring(4,6), 16) / 255, 1,
                );
            }
            if (h.length === 8) {
                return new vscode.Color(
                    parseInt(h.substring(0,2), 16) / 255,
                    parseInt(h.substring(2,4), 16) / 255,
                    parseInt(h.substring(4,6), 16) / 255,
                    parseInt(h.substring(6,8), 16) / 255,
                );
            }
        }
        if (text.startsWith('rgb')) {
            const m = text.match(/[\d.]+/g);
            if (m && m.length >= 3) {
                return new vscode.Color(
                    parseInt(m[0]) / 255, parseInt(m[1]) / 255, parseInt(m[2]) / 255,
                    m.length >= 4 ? parseFloat(m[3]) : 1,
                );
            }
        }
        return undefined;
    }
}
