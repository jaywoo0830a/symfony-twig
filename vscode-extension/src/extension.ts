import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { execFile } from 'child_process';
import { promisify } from 'util';

import { TwigFormattingProvider, TwigHoverProvider, TwigDefinitionProvider, TwigCompletionProvider, TwigSymbolProvider, TwigFoldingProvider, TwigSignatureHelpProvider, TwigCodeActionProvider, TwigHighlightProvider, TwigRenameProvider, TwigColorProvider, HtmlHoverProvider } from './providers';

// ── Data loaded from JSON ──
import htmlCompletions from './data/html-completions.json';

// ═══════════════════════════════════════════════════════════════════════
// 1. Types — algebraic, immutable data descriptions
// ═══════════════════════════════════════════════════════════════════════

// ---- LSP protocol types ----

interface LspPosition {
    readonly line: number;
    readonly character: number;
}

interface LspRange {
    readonly start: LspPosition;
    readonly end: LspPosition;
}

interface LspDiagnostic {
    readonly message: string;
    readonly severity: number; // LSP: 1=Error, 2=Warning, 3=Info, 4=Hint
    readonly range: LspRange;
    readonly code: string;
    readonly source: string;
}

interface AnalyzerOutput {
    readonly files: Record<string, readonly LspDiagnostic[]>;
    readonly diagnostics: readonly LspDiagnostic[];
    readonly summary: {
        readonly total: number;
        readonly errors: number;
        readonly warnings: number;
        readonly info: number;
        readonly hints: number;
    };
}

// ---- CLI command representation ----

export interface CliCommand {
    readonly cmd: string;
    readonly args: readonly string[];
    readonly env: NodeJS.ProcessEnv;
}

// ---- Result type — eliminates try-catch in control flow ----

type Result<T, E = string> =
    | { readonly ok: true;  readonly value: T }
    | { readonly ok: false; readonly error: E };

const ok = <T>(value: T): Result<T, never> => ({ ok: true, value });
const fail = <E = string>(error: E): Result<never, E> => ({ ok: false, error });

// ---- Error discriminants — no `any` types ----

type CliError =
    | { readonly type: 'ENOENT'; readonly path: string }
    | { readonly type: 'timeout' }
    | { readonly type: 'module_not_found'; readonly stderr: string }
    | { readonly type: 'no_output'; readonly message: string }
    | { readonly type: 'exit_code'; readonly code: number };

const cliErrorLabel: Record<CliError['type'], string> = {
    ENOENT: 'Python not found or twig_analyzer not installed',
    timeout: 'Analysis timed out',
    module_not_found: 'twig_analyzer module not found',
    no_output: 'CLI produced no output',
    exit_code: 'CLI exited with non-zero code',
};

// ---- Diagnostic partition (pure) ----

interface DiagnosticPartition {
    readonly errors: readonly vscode.Diagnostic[];
    readonly warnings: readonly vscode.Diagnostic[];
    readonly infos: readonly vscode.Diagnostic[];
    readonly hints: readonly vscode.Diagnostic[];
    readonly total: number;
}

// ═══════════════════════════════════════════════════════════════════════
// 2. Pure functions — no side effects, deterministic, explicit returns
// ═══════════════════════════════════════════════════════════════════════

// ---- File detection (pure predicate) ----

export const isTwigFile = (doc: Pick<vscode.TextDocument, 'languageId' | 'fileName'>): boolean => {
    const config = vscode.workspace.getConfiguration('twigAnalyzer');
    const extensions: readonly string[] = config.get<string[]>('fileExtensions', ['.twig', '.html.twig']);

    if (doc.languageId === 'twig') return true;
    return extensions.some(ext => doc.fileName.endsWith(ext));
};

// ---- Severity mapping (pure, exhaustive) ----

const SEVERITY_MAP = new Map<number, vscode.DiagnosticSeverity>([
    [1, vscode.DiagnosticSeverity.Error],
    [2, vscode.DiagnosticSeverity.Warning],
    [3, vscode.DiagnosticSeverity.Information],
    [4, vscode.DiagnosticSeverity.Hint],
]);

const lspSeverityToVsCode = (lspSeverity: number): vscode.DiagnosticSeverity =>
    SEVERITY_MAP.get(lspSeverity) ?? vscode.DiagnosticSeverity.Warning;

// ---- Range conversion (pure) ----

const lspRangeToVsCodeRange = (r: LspRange): vscode.Range =>
    new vscode.Range(
        new vscode.Position(r.start.line, r.start.character),
        new vscode.Position(r.end.line, r.end.character),
    );

// ---- Diagnostic conversion (pure) ----

const lspDiagToVsCodeDiag = (d: LspDiagnostic): vscode.Diagnostic => {
    const diag = new vscode.Diagnostic(
        lspRangeToVsCodeRange(d.range),
        d.message,
        lspSeverityToVsCode(d.severity),
    );
    diag.source = d.source ?? 'twig-analyzer';
    diag.code = d.code ?? '';
    return diag;
};

// ---- Partition diagnostics (pure) ----

const partitionDiagnostics = (diags: readonly vscode.Diagnostic[]): DiagnosticPartition => ({
    errors: diags.filter(d => d.severity === vscode.DiagnosticSeverity.Error),
    warnings: diags.filter(d => d.severity === vscode.DiagnosticSeverity.Warning),
    infos: diags.filter(d => d.severity === vscode.DiagnosticSeverity.Information),
    hints: diags.filter(d => d.severity === vscode.DiagnosticSeverity.Hint),
    total: diags.length,
});

// ---- CLI argument builder (pure) ----

const buildAnalyzerArgs = (): readonly string[] => {
    const config = vscode.workspace.getConfiguration('twigAnalyzer');
    const disabledRules: readonly string[] = config.get<string[]>('disabledRules', []);
    const severityOverrides: Readonly<Record<string, string>> = config.get<Record<string, string>>('severityOverrides', {});

    const disableArg = disabledRules.length > 0
        ? ['--disable', disabledRules.join(',')]
        : [];

    const severityArgs = Object.entries(severityOverrides)
        .flatMap(([ruleId, severity]) => ['--severity', `${ruleId}=${severity}`]);

    return [...disableArg, ...severityArgs];
};

// ---- Parse JSON output (pure, returns Result) ----

const parseAnalyzerOutput = (stdout: string): Result<AnalyzerOutput> => {
    try {
        return ok(JSON.parse(stdout) as AnalyzerOutput);
    } catch (e) {
        return fail(`JSON parse error: ${e instanceof Error ? e.message : String(e)}`);
    }
};

// ---- Extract diagnostics for a file (pure) ----

const findFileDiagnostics = (
    output: AnalyzerOutput,
    filePath: string,
): readonly LspDiagnostic[] =>
    output.files[filePath] ?? [];

// ---- Filename extraction (pure) ----

const basename = (filePath: string): string =>
    filePath.split('/').pop() ?? filePath;

// ═══════════════════════════════════════════════════════════════════════
// 3. Strategy functions — find commands via ordered strategies
// ═══════════════════════════════════════════════════════════════════════

type Strategy = () => CliCommand | undefined;

const firstOf = (strategies: readonly Strategy[]): CliCommand => {
    for (const s of strategies) {
        const result = s();
        if (result !== undefined) return result;
    }
    return { cmd: 'python3', args: ['-m', 'twig_analyzer'], env: { ...process.env } };
};

export const findAnalyzerCommand = (): CliCommand => {
    const config = vscode.workspace.getConfiguration('twigAnalyzer');
    const extDir = path.resolve(__dirname, '..');
    const homeDir = process.env.HOME ?? '/home/rlawjddn';

    const strategies: readonly Strategy[] = [
        // Strategy 1: User-configured pythonPath
        () => {
            const configured = config.get<string>('pythonPath', '');
            if (configured && fs.existsSync(configured)) {
                return { cmd: configured, args: ['-m', 'twig_analyzer'], env: { ...process.env } };
            }
            return undefined;
        },
        // Strategy 2: Known project venv
        () => {
            const candidates = [
                path.join(homeDir, 'symfony-twig', '.venv', 'bin', 'python3'),
                path.join(homeDir, 'symfony-twig', '.venv', 'bin', 'python'),
            ];
            const found = candidates.find(p => fs.existsSync(p));
            return found
                ? { cmd: found, args: ['-m', 'twig_analyzer'], env: { ...process.env } }
                : undefined;
        },
        // Strategy 3: python3 on PATH, with extension dir as fallback
        () => {
            const env = { ...process.env };
            const twigPath = path.join(extDir, 'twig_analyzer');
            if (fs.existsSync(twigPath)) {
                env.PYTHONPATH = extDir + (env.PYTHONPATH ? `:${env.PYTHONPATH}` : '');
            }
            return { cmd: 'python3', args: ['-m', 'twig_analyzer'], env };
        },
    ];

    return firstOf(strategies);
};

// ═══════════════════════════════════════════════════════════════════════
// 4. IO functions — side effects, wrapped in Result
// ═══════════════════════════════════════════════════════════════════════

const execFileAsync = promisify(execFile);

interface CliResult {
    readonly stdout: string;
    readonly stderr: string;
}

const runAnalyzerCli = async (cmd: CliCommand, filePath: string): Promise<Result<CliResult, CliError>> => {
    const analyzerArgs = buildAnalyzerArgs();
    const allArgs = [...cmd.args, ...analyzerArgs, '--format', 'json', filePath];

    try {
        const { stdout, stderr } = await execFileAsync(cmd.cmd, allArgs, {
            timeout: 30000,
            maxBuffer: 10 * 1024 * 1024,
            env: cmd.env,
        });
        return ok({ stdout, stderr });
    } catch (err: any) {
        const stdout: string = err.stdout ?? '';
        const stderr: string = err.stderr ?? '';

        if (err.code === 'ENOENT') return fail({ type: 'ENOENT', path: cmd.cmd });
        if (err.killed) return fail({ type: 'timeout' });
        if (stderr.includes('No module named')) return fail({ type: 'module_not_found', stderr });
        if (stdout.trim() === '') return fail({ type: 'no_output', message: err.message ?? 'unknown' });

        console.log(`[twig-analyzer] CLI exited with code ${err.code}, processing stdout`);
        return ok({ stdout, stderr });
    }
};

const setDiagnostics = (uri: vscode.Uri, diags: readonly vscode.Diagnostic[]): void => {
    if (diags.length > 0) {
        diagnosticCollection.set(uri, [...diags]);
    } else {
        diagnosticCollection.delete(uri);
    }
};

const showStatusMessage = (fileName: string, partition: DiagnosticPartition): void => {
    vscode.window.setStatusBarMessage(
        `$(check) Twig: ${fileName} – ${partition.errors.length} errors, ${partition.warnings.length} warnings`,
        5000,
    );
};

const reportCliError = (error: CliError): void => {
    const homeDir = process.env.HOME ?? '~';
    const installCmd = `bash ${homeDir}/symfony-twig/vscode-extension/install.sh`;

    switch (error.type) {
        case 'ENOENT':
            vscode.window.showErrorMessage(`Twig Analyzer: ${cliErrorLabel.ENOENT}\nRun: ${installCmd}`);
            break;
        case 'timeout':
            console.warn('[twig-analyzer] Timed out');
            break;
        case 'module_not_found':
            vscode.window.showErrorMessage(`Twig Analyzer: ${cliErrorLabel.module_not_found}\nRun: ${installCmd}`);
            break;
        case 'no_output':
            console.error('[twig-analyzer] CLI failed with no output:', error.message);
            break;
        case 'exit_code':
            console.log(`[twig-analyzer] CLI exited with code ${error.code}`);
            break;
    }
};

// ═══════════════════════════════════════════════════════════════════════
// 5. Composition — pipeline the analysis
// ═══════════════════════════════════════════════════════════════════════

const analyzeDocument = async (document: vscode.TextDocument): Promise<void> => {
    const config = vscode.workspace.getConfiguration('twigAnalyzer');
    if (config.get<boolean>('enabled', true) === false) {
        setDiagnostics(document.uri, []);
        return;
    }

    const filePath = document.uri.fsPath;
    const cmd = findAnalyzerCommand();
    const cliResult = await runAnalyzerCli(cmd, filePath);

    if (cliResult.ok === false) {
        reportCliError(cliResult.error);
        return;
    }

    const parseResult = parseAnalyzerOutput(cliResult.value.stdout);
    if (parseResult.ok === false) {
        console.error('[twig-analyzer]', parseResult.error);
        return;
    }

    const lspDiags = findFileDiagnostics(parseResult.value, filePath);
    const vsDiags = lspDiags.map(lspDiagToVsCodeDiag);
    const partition = partitionDiagnostics(vsDiags);

    setDiagnostics(document.uri, vsDiags);
    showStatusMessage(basename(document.fileName), partition);
};

// ═══════════════════════════════════════════════════════════════════════
// 6. Event wiring — functional event → handler mapping
// ═══════════════════════════════════════════════════════════════════════

const mkDebouncer = (ms: number) => {
    let timer: NodeJS.Timeout | undefined;
    return (fn: () => void) => {
        if (timer !== undefined) clearTimeout(timer);
        timer = setTimeout(() => { timer = undefined; fn(); }, ms);
    };
};

const wireEvents = (context: vscode.ExtensionContext): void => {
    const config = vscode.workspace.getConfiguration('twigAnalyzer');
    const runOnOpen = config.get<boolean>('runOnOpen', true);
    const runOnSave = config.get<boolean>('runOnSave', true);
    const debounce = mkDebouncer(1000);

    const analyzeIfTwig = (doc: vscode.TextDocument) => {
        if (isTwigFile(doc)) analyzeDocument(doc);
    };

    // Initial sweep
    if (runOnOpen) {
        vscode.window.visibleTextEditors.forEach(editor => analyzeIfTwig(editor.document));
        const active = vscode.window.activeTextEditor;
        if (active !== undefined) analyzeIfTwig(active.document);
    }

    // Editor switches
    context.subscriptions.push(
        vscode.window.onDidChangeActiveTextEditor(editor => {
            if (editor !== undefined && runOnOpen) analyzeIfTwig(editor.document);
        }),
    );

    // Save
    context.subscriptions.push(
        vscode.workspace.onDidSaveTextDocument(doc => {
            if (runOnSave && isTwigFile(doc)) analyzeDocument(doc);
        }),
    );

    // Change (debounced, only when not runOnSave)
    context.subscriptions.push(
        vscode.workspace.onDidChangeTextDocument(event => {
            if (runOnSave) return;
            if (!isTwigFile(event.document)) return;
            debounce(() => analyzeDocument(event.document));
        }),
    );

    // Cleanup on close
    context.subscriptions.push(
        vscode.workspace.onDidCloseTextDocument(doc => {
            diagnosticCollection.delete(doc.uri);
        }),
    );
};

// ═══════════════════════════════════════════════════════════════════════
// 7. HTML IntelliSense — pure data + composable providers
// ═══════════════════════════════════════════════════════════════════════

interface TagCompletion {
    readonly label: string;
    readonly detail: string;
    readonly insertText: string;
}

const HTML_TAGS: readonly TagCompletion[] = htmlCompletions.tags as readonly TagCompletion[];

const COMMON_ATTRS: readonly TagCompletion[] = htmlCompletions.attributes as readonly TagCompletion[];

const VOID_ELEMENTS: ReadonlySet<string> = new Set(htmlCompletions.voidElements);

// ---- Pure helpers for completion ----

export const isInsideTwigTag = (beforeCursor: string): boolean =>
    (beforeCursor.includes('{{') && !beforeCursor.includes('}}')) ||
    (beforeCursor.includes('{%') && !beforeCursor.includes('%}'));

export const isInsideHtmlTag = (beforeCursor: string): boolean =>
    /<\w+[\s>]/.test(beforeCursor) && !isInsideTwigTag(beforeCursor);

const toCompletionItems = (
    entries: readonly TagCompletion[],
    kind: vscode.CompletionItemKind,
): vscode.CompletionItem[] =>
    entries.map(entry => {
        const item = new vscode.CompletionItem(entry.label, kind);
        item.detail = entry.detail;
        item.insertText = new vscode.SnippetString(entry.insertText);
        item.filterText = entry.label;
        return item;
    });

// ---- Auto-close logic (pure) ----

const tryExtractOpenTag = (beforeGt: string): string | undefined => {
    const match = beforeGt.match(/<(\w+)[^>]*$/);
    if (match === null) return undefined;
    if (isInsideTwigTag(beforeGt)) return undefined;
    return match[1];
};

const shouldAutoClose = (tagName: string): boolean =>
    !VOID_ELEMENTS.has(tagName.toLowerCase());

// ═══════════════════════════════════════════════════════════════════════
// 8. Extension lifecycle (activation / deactivation)
// ═══════════════════════════════════════════════════════════════════════

const diagnosticCollection = vscode.languages.createDiagnosticCollection('twig-analyzer');

export function activate(context: vscode.ExtensionContext): void {
    console.log('Twig Static Analyzer is now active');

    // Manual analysis command
    context.subscriptions.push(
        vscode.commands.registerCommand('twig-analyzer.analyze', () => {
            const editor = vscode.window.activeTextEditor;
            if (editor !== undefined && isTwigFile(editor.document)) {
                analyzeDocument(editor.document);
            }
        }),
    );

    // Wire file events
    wireEvents(context);

    // Status bar
    const statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBar.command = 'twig-analyzer.analyze';
    statusBar.text = '$(check) Twig';
    statusBar.tooltip = 'Twig Static Analyzer';
    statusBar.show();
    context.subscriptions.push(statusBar);

    // Formatting provider (twig + html)
    const formattingProvider = new TwigFormattingProvider();
    context.subscriptions.push(
        vscode.languages.registerDocumentFormattingEditProvider({ language: 'twig', scheme: 'file' }, formattingProvider),
        vscode.languages.registerDocumentFormattingEditProvider({ language: 'html', scheme: 'file' }, formattingProvider),
    );

    // HTML tag completion
    context.subscriptions.push(
        vscode.languages.registerCompletionItemProvider(
            { language: 'twig', scheme: 'file' },
            {
                provideCompletionItems(document, position) {
                    const beforeCursor = document.lineAt(position).text.substring(0, position.character);
                    if (isInsideTwigTag(beforeCursor)) return [];
                    return toCompletionItems(HTML_TAGS, vscode.CompletionItemKind.Keyword);
                },
            },
            '<',
        ),
    );

    // HTML attribute completion
    context.subscriptions.push(
        vscode.languages.registerCompletionItemProvider(
            { language: 'twig', scheme: 'file' },
            {
                provideCompletionItems(document, position) {
                    const beforeCursor = document.lineAt(position).text.substring(0, position.character);
                    if (!isInsideHtmlTag(beforeCursor)) return [];
                    return toCompletionItems(COMMON_ATTRS, vscode.CompletionItemKind.Property);
                },
            },
            ' ',
        ),
    );

    // Auto-close HTML tags
    context.subscriptions.push(
        vscode.workspace.onDidChangeTextDocument(event => {
            if (!isTwigFile(event.document)) return;
            for (const change of event.contentChanges) {
                if (change.text !== '>') continue;

                const pos = change.range.start;
                const beforeGt = event.document.lineAt(pos.line).text.substring(0, pos.character);
                const tagName = tryExtractOpenTag(beforeGt);

                if (tagName !== undefined && shouldAutoClose(tagName)) {
                    const edit = new vscode.WorkspaceEdit();
                    edit.insert(event.document.uri, new vscode.Position(pos.line, pos.character + 1), `</${tagName}>`);
                    vscode.workspace.applyEdit(edit);
                }
            }
        }),
    );

    // Emmet for Twig
    vscode.workspace.getConfiguration('emmet').update(
        'includeLanguages', { twig: 'html' }, vscode.ConfigurationTarget.Global,
    ).then(() => {}, () => {});

    // ---- Hover: Twig built-in documentation ----
    context.subscriptions.push(
        vscode.languages.registerHoverProvider(
            { language: 'twig', scheme: 'file' },
            new TwigHoverProvider(),
        ),
    );

    // ---- Hover: HTML5 MDN documentation ----
    context.subscriptions.push(
        vscode.languages.registerHoverProvider(
            { language: 'twig', scheme: 'file' },
            new HtmlHoverProvider(),
        ),
    );

    // ---- Go-to-definition: extends/include template paths ----
    context.subscriptions.push(
        vscode.languages.registerDefinitionProvider(
            { language: 'twig', scheme: 'file' },
            new TwigDefinitionProvider(),
        ),
    );

    // ---- Completion: Twig keywords (tags, filters, functions) ----
    context.subscriptions.push(
        vscode.languages.registerCompletionItemProvider(
            { language: 'twig', scheme: 'file' },
            new TwigCompletionProvider(),
            ' ', '|', '.', '(',
        ),
    );

    // ---- Symbol provider: Outline / Breadcrumbs ----
    context.subscriptions.push(
        vscode.languages.registerDocumentSymbolProvider(
            { language: 'twig', scheme: 'file' },
            new TwigSymbolProvider(),
            { label: 'Twig Blocks' },
        ),
    );

    // ---- Folding: collapse block/if/for regions ----
    context.subscriptions.push(
        vscode.languages.registerFoldingRangeProvider(
            { language: 'twig', scheme: 'file' },
            new TwigFoldingProvider(),
        ),
    );

    // ---- Signature help: function/filter parameters ----
    context.subscriptions.push(
        vscode.languages.registerSignatureHelpProvider(
            { language: 'twig', scheme: 'file' },
            new TwigSignatureHelpProvider(),
            '(',
        ),
    );

    // ---- Code Actions: Quick Fix ----
    context.subscriptions.push(
        vscode.languages.registerCodeActionsProvider(
            { language: 'twig', scheme: 'file' },
            new TwigCodeActionProvider(),
            { providedCodeActionKinds: [vscode.CodeActionKind.QuickFix] },
        ),
    );

    // ---- Document Highlight: matching {% if %} ↔ {% endif %} ----
    context.subscriptions.push(
        vscode.languages.registerDocumentHighlightProvider(
            { language: 'twig', scheme: 'file' },
            new TwigHighlightProvider(),
        ),
    );

    // ---- Rename: F2 on block/macro names ----
    context.subscriptions.push(
        vscode.languages.registerRenameProvider(
            { language: 'twig', scheme: 'file' },
            new TwigRenameProvider(),
        ),
    );

    // ---- Color Provider: CSS color previews ----
    context.subscriptions.push(
        vscode.languages.registerColorProvider(
            { language: 'twig', scheme: 'file' },
            new TwigColorProvider(),
        ),
    );
}

export function deactivate(): void {
    diagnosticCollection.clear();
}

// ═══════════════════════════════════════════════════════════════════════
