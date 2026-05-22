import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { execFile } from 'child_process';
import { promisify } from 'util';

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

interface CliCommand {
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

const isTwigFile = (doc: Pick<vscode.TextDocument, 'languageId' | 'fileName'>): boolean => {
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

const findAnalyzerCommand = (): CliCommand => {
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

const HTML_TAGS: readonly TagCompletion[] = [
    { label: 'div',        detail: 'HTML Block Container',       insertText: 'div' },
    { label: 'span',       detail: 'HTML Inline Container',      insertText: 'span' },
    { label: 'p',          detail: 'HTML Paragraph',             insertText: 'p' },
    { label: 'a',          detail: 'HTML Anchor/Link',           insertText: 'a href="$1"$0' },
    { label: 'img',        detail: 'HTML Image',                 insertText: 'img src="$1" alt="$2"$0' },
    { label: 'ul',         detail: 'HTML Unordered List',        insertText: 'ul' },
    { label: 'ol',         detail: 'HTML Ordered List',          insertText: 'ol' },
    { label: 'li',         detail: 'HTML List Item',             insertText: 'li' },
    { label: 'table',      detail: 'HTML Table',                 insertText: 'table' },
    { label: 'tr',         detail: 'HTML Table Row',             insertText: 'tr' },
    { label: 'td',         detail: 'HTML Table Cell',            insertText: 'td' },
    { label: 'th',         detail: 'HTML Table Header',          insertText: 'th' },
    { label: 'thead',      detail: 'HTML Table Head',            insertText: 'thead' },
    { label: 'tbody',      detail: 'HTML Table Body',            insertText: 'tbody' },
    { label: 'form',       detail: 'HTML Form',                  insertText: 'form action="$1" method="$2"$0' },
    { label: 'input',      detail: 'HTML Input',                 insertText: 'input type="$1"$0' },
    { label: 'button',     detail: 'HTML Button',                insertText: 'button type="$1"$0' },
    { label: 'label',      detail: 'HTML Label',                 insertText: 'label for="$1"$0' },
    { label: 'select',     detail: 'HTML Select Dropdown',       insertText: 'select' },
    { label: 'option',     detail: 'HTML Option',                insertText: 'option value="$1"$0' },
    { label: 'textarea',   detail: 'HTML Textarea',              insertText: 'textarea' },
    { label: 'h1',         detail: 'HTML Heading 1',             insertText: 'h1' },
    { label: 'h2',         detail: 'HTML Heading 2',             insertText: 'h2' },
    { label: 'h3',         detail: 'HTML Heading 3',             insertText: 'h3' },
    { label: 'h4',         detail: 'HTML Heading 4',             insertText: 'h4' },
    { label: 'h5',         detail: 'HTML Heading 5',             insertText: 'h5' },
    { label: 'h6',         detail: 'HTML Heading 6',             insertText: 'h6' },
    { label: 'section',    detail: 'HTML Section',               insertText: 'section' },
    { label: 'article',    detail: 'HTML Article',               insertText: 'article' },
    { label: 'nav',        detail: 'HTML Navigation',            insertText: 'nav' },
    { label: 'header',     detail: 'HTML Header',                insertText: 'header' },
    { label: 'footer',     detail: 'HTML Footer',                insertText: 'footer' },
    { label: 'main',       detail: 'HTML Main Content',          insertText: 'main' },
    { label: 'aside',      detail: 'HTML Aside',                 insertText: 'aside' },
    { label: 'figure',     detail: 'HTML Figure',                insertText: 'figure' },
    { label: 'figcaption', detail: 'HTML Figure Caption',        insertText: 'figcaption' },
    { label: 'video',      detail: 'HTML Video',                 insertText: 'video src="$1"$0' },
    { label: 'audio',      detail: 'HTML Audio',                 insertText: 'audio src="$1"$0' },
    { label: 'canvas',     detail: 'HTML Canvas',                insertText: 'canvas' },
    { label: 'script',     detail: 'HTML Script',                insertText: 'script' },
    { label: 'style',      detail: 'HTML Style',                 insertText: 'style' },
    { label: 'link',       detail: 'HTML Link (CSS, etc.)',      insertText: 'link rel="$1" href="$2"$0' },
    { label: 'meta',       detail: 'HTML Meta',                  insertText: 'meta name="$1" content="$2"$0' },
    { label: 'title',      detail: 'HTML Title',                 insertText: 'title' },
    { label: 'br',         detail: 'HTML Line Break',            insertText: 'br' },
    { label: 'hr',         detail: 'HTML Horizontal Rule',       insertText: 'hr' },
    { label: 'strong',     detail: 'HTML Strong (bold)',         insertText: 'strong' },
    { label: 'em',         detail: 'HTML Emphasis (italic)',     insertText: 'em' },
    { label: 'code',       detail: 'HTML Code',                  insertText: 'code' },
    { label: 'pre',        detail: 'HTML Preformatted Text',     insertText: 'pre' },
    { label: 'blockquote', detail: 'HTML Blockquote',            insertText: 'blockquote' },
    { label: 'details',    detail: 'HTML Details/Accordion',     insertText: 'details' },
    { label: 'summary',    detail: 'HTML Summary (for details)',  insertText: 'summary' },
] as const;

const COMMON_ATTRS: readonly TagCompletion[] = [
    { label: 'class',       detail: 'HTML Attribute', insertText: 'class="$1"$0' },
    { label: 'id',          detail: 'HTML Attribute', insertText: 'id="$1"$0' },
    { label: 'style',       detail: 'HTML Attribute', insertText: 'style="$1"$0' },
    { label: 'title',       detail: 'HTML Attribute', insertText: 'title="$1"$0' },
    { label: 'href',        detail: 'HTML Attribute', insertText: 'href="$1"$0' },
    { label: 'src',         detail: 'HTML Attribute', insertText: 'src="$1"$0' },
    { label: 'alt',         detail: 'HTML Attribute', insertText: 'alt="$1"$0' },
    { label: 'type',        detail: 'HTML Attribute', insertText: 'type="$1"$0' },
    { label: 'name',        detail: 'HTML Attribute', insertText: 'name="$1"$0' },
    { label: 'value',       detail: 'HTML Attribute', insertText: 'value="$1"$0' },
    { label: 'placeholder', detail: 'HTML Attribute', insertText: 'placeholder="$1"$0' },
    { label: 'required',    detail: 'HTML Attribute', insertText: 'required' },
    { label: 'disabled',    detail: 'HTML Attribute', insertText: 'disabled' },
    { label: 'checked',     detail: 'HTML Attribute', insertText: 'checked' },
    { label: 'selected',    detail: 'HTML Attribute', insertText: 'selected' },
    { label: 'readonly',    detail: 'HTML Attribute', insertText: 'readonly' },
    { label: 'target',      detail: 'HTML Attribute', insertText: 'target="$1"$0' },
    { label: 'rel',         detail: 'HTML Attribute', insertText: 'rel="$1"$0' },
    { label: 'data-',       detail: 'HTML Attribute', insertText: 'data-$1="$2"$0' },
    { label: 'aria-',       detail: 'HTML Attribute', insertText: 'aria-$1="$2"$0' },
] as const;

const VOID_ELEMENTS: ReadonlySet<string> = new Set([
    'br', 'hr', 'img', 'input', 'meta', 'link', 'area', 'base',
    'col', 'embed', 'source', 'track', 'wbr',
]);

// ---- Pure helpers for completion ----

const isInsideTwigTag = (beforeCursor: string): boolean =>
    (beforeCursor.includes('{{') && !beforeCursor.includes('}}')) ||
    (beforeCursor.includes('{%') && !beforeCursor.includes('%}'));

const isInsideHtmlTag = (beforeCursor: string): boolean =>
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

    // ---- Go-to-definition: extends/include template paths ----
    context.subscriptions.push(
        vscode.languages.registerDefinitionProvider(
            { language: 'twig', scheme: 'file' },
            new TwigDefinitionProvider(),
        ),
    );
}

export function deactivate(): void {
    diagnosticCollection.clear();
}

// ═══════════════════════════════════════════════════════════════════════
// 9. Formatting provider
// ═══════════════════════════════════════════════════════════════════════

class TwigFormattingProvider implements vscode.DocumentFormattingEditProvider {
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
        const tmp = require('os').tmpdir();
        const tmpFile = require('path').join(tmp, `twig-fmt-${Date.now()}.twig`);

        try {
            require('fs').writeFileSync(tmpFile, document.getText(), 'utf-8');
            await execFileAsync(cmd.cmd, [...cmd.args, 'format', tmpFile], {
                timeout: 30000,
                env: cmd.env,
            });
            return require('fs').readFileSync(tmpFile, 'utf-8') as string;
        } catch {
            return undefined;
        } finally {
            try { require('fs').unlinkSync(tmpFile); } catch { /* ignore */ }
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

const TWIG_DOCS = 'https://twig.symfony.com/doc/3.x';

const BUILTIN_HOVER_DATA: Record<string, BuiltinEntry> = {
    // Tags
    apply:       { description: 'Applies a filter to a section of code',                               since: '1.0',  example: '{% apply upper %}Text{% endapply %}',                       link: `${TWIG_DOCS}/tags/apply.html` },
    autoescape:  { description: 'Controls auto-escaping strategy for a block',                          since: '1.0',  example: "{% autoescape 'html' %}...{% endautoescape %}",             link: `${TWIG_DOCS}/tags/autoescape.html` },
    block:       { description: 'Defines a block that child templates can override',                    since: '1.0',  example: '{% block title %}...{% endblock %}',                      link: `${TWIG_DOCS}/tags/block.html` },
    cache:       { description: 'Caches a template fragment',                                          since: '3.2',  example: '{% cache %}...{% endcache %}',                             link: `${TWIG_DOCS}/tags/cache.html` },
    deprecated:  { description: 'Marks a template section as deprecated',                              since: '1.36', example: "{% deprecated 'Use X instead' %}",                         link: `${TWIG_DOCS}/tags/deprecated.html` },
    do:          { description: 'Executes an expression without output',                               since: '1.0',  example: "{% do var = 'value' %}",                                  link: `${TWIG_DOCS}/tags/do.html` },
    embed:       { description: 'Embeds another template with block overrides',                        since: '1.8',  example: "{% embed 'template.twig' %}...{% endembed %}",             link: `${TWIG_DOCS}/tags/embed.html` },
    extends:     { description: 'Extends a parent template (must be the first tag)',                   since: '1.0',  example: "{% extends 'base.html.twig' %}",                          link: `${TWIG_DOCS}/tags/extends.html` },
    flush:       { description: 'Flushes the output buffer',                                           since: '1.5',  example: '{% flush %}',                                             link: `${TWIG_DOCS}/tags/flush.html` },
    for:         { description: 'Iterates over a sequence',                                           since: '1.0',  example: '{% for item in items %}...{% endfor %}',                  link: `${TWIG_DOCS}/tags/for.html` },
    from:        { description: 'Imports macro names from a template',                                since: '1.0',  example: "{% from 'macros.twig' import input %}",                   link: `${TWIG_DOCS}/tags/from.html` },
    guard:       { description: 'Conditionally outputs content based on a tag',                       since: '3.13', example: "{% guard function('route') %}...{% endguard %}",          link: `${TWIG_DOCS}/tags/guard.html` },
    if:          { description: 'Conditional block with elseif/else support',                         since: '1.0',  example: '{% if condition %}...{% endif %}',                       link: `${TWIG_DOCS}/tags/if.html` },
    import:      { description: 'Imports all macros from a template',                                 since: '1.0',  example: "{% import 'macros.twig' as macros %}",                    link: `${TWIG_DOCS}/tags/import.html` },
    include:     { description: 'Includes another template (use include() function instead)',          since: '1.0',  example: "{% include 'template.twig' %}",                          link: `${TWIG_DOCS}/tags/include.html` },
    macro:       { description: 'Defines a reusable macro',                                           since: '1.0',  example: '{% macro input(name, value) %}...{% endmacro %}',         link: `${TWIG_DOCS}/tags/macro.html` },
    sandbox:     { description: 'Enables sandbox mode for a block',                                   since: '1.0',  example: '{% sandbox %}...{% endsandbox %}',                        link: `${TWIG_DOCS}/tags/sandbox.html` },
    set:         { description: 'Assigns values to variables',                                        since: '1.0',  example: "{% set name = 'Fabien' %}",                               link: `${TWIG_DOCS}/tags/set.html` },
    use:         { description: 'Horizontal reuse — imports blocks from another template',            since: '1.0',  example: "{% use 'blocks.twig' %}",                                link: `${TWIG_DOCS}/tags/use.html` },
    verbatim:    { description: 'Outputs raw text without parsing Twig syntax',                       since: '1.0',  example: '{% verbatim %}...{% endverbatim %}',                      link: `${TWIG_DOCS}/tags/verbatim.html` },
    with:        { description: 'Creates a new inner scope with variables',                           since: '1.0',  example: "{% with {name: 'Fabien'} %}...{% endwith %}",              link: `${TWIG_DOCS}/tags/with.html` },
    types:       { description: 'Declares variable types for static analysis',                        since: '3.15', example: "{% types {name: 'string'} %}",                            link: `${TWIG_DOCS}/tags/types.html` },
    else:        { description: 'Default branch in if/for blocks',                                    since: '1.0',  example: '{% else %}',                                              link: `${TWIG_DOCS}/tags/if.html` },
    elseif:      { description: 'Conditional branch in if blocks',                                    since: '1.0',  example: '{% elseif condition %}',                                   link: `${TWIG_DOCS}/tags/if.html` },

    // Filters
    abs:         { description: 'Absolute value of a number',                                         since: '1.0',  example: '{{ -1|abs }}',                                             link: `${TWIG_DOCS}/filters/abs.html` },
    batch:       { description: 'Batches items into arrays of given size',                            since: '1.0',  example: '{{ items|batch(3) }}',                                      link: `${TWIG_DOCS}/filters/batch.html` },
    capitalize:  { description: 'Capitalizes the first character',                                    since: '1.0',  example: "{{ 'hello'|capitalize }}",                                  link: `${TWIG_DOCS}/filters/capitalize.html` },
    convert_encoding: { description: 'Converts string encoding',                                      since: '1.0',  example: "{{ data|convert_encoding('UTF-8', 'iso-2022-jp') }}",       link: `${TWIG_DOCS}/filters/convert_encoding.html` },
    date:        { description: 'Formats a date',                                                     since: '1.0',  example: "{{ post.publishedAt|date('Y-m-d') }}",                      link: `${TWIG_DOCS}/filters/date.html` },
    default:     { description: 'Returns default value if variable is empty/undefined',               since: '1.0',  example: "{{ var|default('fallback') }}",                             link: `${TWIG_DOCS}/filters/default.html` },
    escape:      { description: 'Escapes a string for safe HTML output',                              since: '1.0',  example: '{{ user.username|e }}',                                     link: `${TWIG_DOCS}/filters/escape.html` },
    e:           { description: 'Alias for escape — escapes for safe HTML output',                    since: '1.0',  example: '{{ user.username|e }}',                                     link: `${TWIG_DOCS}/filters/escape.html` },
    first:       { description: 'Returns the first element of a sequence',                            since: '1.0',  example: '{{ items|first }}',                                         link: `${TWIG_DOCS}/filters/first.html` },
    format:      { description: 'Formats a string by replacing placeholders',                         since: '1.0',  example: "{{ 'Hello %s!'|format(name) }}",                            link: `${TWIG_DOCS}/filters/format.html` },
    join:        { description: 'Joins array elements into a string',                                 since: '1.0',  example: "{{ items|join(', ') }}",                                     link: `${TWIG_DOCS}/filters/join.html` },
    json_encode: { description: 'Encodes value as JSON',                                              since: '1.0',  example: '{{ data|json_encode }}',                                     link: `${TWIG_DOCS}/filters/json_encode.html` },
    keys:        { description: 'Returns the keys of a mapping',                                      since: '1.0',  example: '{{ map|keys }}',                                            link: `${TWIG_DOCS}/filters/keys.html` },
    last:        { description: 'Returns the last element of a sequence',                             since: '1.0',  example: '{{ items|last }}',                                          link: `${TWIG_DOCS}/filters/last.html` },
    length:      { description: 'Returns the count of items',                                         since: '1.0',  example: '{{ items|length }}',                                        link: `${TWIG_DOCS}/filters/length.html` },
    lower:       { description: 'Converts a string to lowercase',                                     since: '1.0',  example: "{{ 'HELLO'|lower }}",                                       link: `${TWIG_DOCS}/filters/lower.html` },
    merge:       { description: 'Merges a mapping/sequence with another',                             since: '1.0',  example: '{{ arr|merge([3, 4]) }}',                                   link: `${TWIG_DOCS}/filters/merge.html` },
    nl2br:       { description: 'Inserts HTML line breaks before newlines',                           since: '1.0',  example: '{{ text|nl2br }}',                                          link: `${TWIG_DOCS}/filters/nl2br.html` },
    number_format: { description: 'Formats a number with grouped thousands',                          since: '1.0',  example: '{{ price|number_format(2, ".", ",") }}',                     link: `${TWIG_DOCS}/filters/number_format.html` },
    raw:         { description: 'Marks value as safe (disables auto-escaping) — use with caution',    since: '1.0',  example: '{{ html|raw }}',                                            link: `${TWIG_DOCS}/filters/raw.html` },
    replace:     { description: 'Replaces placeholders in a string',                                  since: '1.0',  example: "{{ 'Hello %name%'|replace({'%name%': 'Fabien'}) }}",        link: `${TWIG_DOCS}/filters/replace.html` },
    reverse:     { description: 'Reverses a sequence or string',                                      since: '1.0',  example: '{{ items|reverse }}',                                       link: `${TWIG_DOCS}/filters/reverse.html` },
    round:       { description: 'Rounds a number',                                                    since: '1.0',  example: '{{ 3.14|round }}',                                          link: `${TWIG_DOCS}/filters/round.html` },
    slice:       { description: 'Extracts a slice of a sequence',                                     since: '1.0',  example: '{{ items|slice(0, 10) }}',                                  link: `${TWIG_DOCS}/filters/slice.html` },
    sort:        { description: 'Sorts a sequence',                                                   since: '1.0',  example: '{{ items|sort }}',                                          link: `${TWIG_DOCS}/filters/sort.html` },
    spaceless:   { description: 'Removes whitespace between HTML tags (DEPRECATED in 3.x)',           since: '1.0',  example: '{{ html|spaceless }}',                                      link: `${TWIG_DOCS}/filters/spaceless.html` },
    split:       { description: 'Splits a string by a delimiter',                                     since: '1.0',  example: "{{ 'a,b,c'|split(',') }}",                                 link: `${TWIG_DOCS}/filters/split.html` },
    striptags:   { description: 'Strips HTML/XML tags from a string',                                 since: '1.0',  example: '{{ html|striptags }}',                                      link: `${TWIG_DOCS}/filters/striptags.html` },
    title:       { description: 'Converts a string to title case',                                    since: '1.0',  example: "{{ 'hello world'|title }}",                                 link: `${TWIG_DOCS}/filters/title.html` },
    trim:        { description: 'Trims whitespace from both ends of a string',                        since: '1.0',  example: "{{ '  hello  '|trim }}",                                   link: `${TWIG_DOCS}/filters/trim.html` },
    upper:       { description: 'Converts a string to uppercase',                                     since: '1.0',  example: "{{ 'hello'|upper }}",                                      link: `${TWIG_DOCS}/filters/upper.html` },
    url_encode:  { description: 'URL-encodes a string',                                               since: '1.0',  example: '{{ url|url_encode }}',                                      link: `${TWIG_DOCS}/filters/url_encode.html` },

    // Functions (excluding names that conflict with tags)
    attribute:   { description: 'Accesses a dynamic attribute/method of a variable',                  since: '1.0',  example: '{{ attribute(obj, method) }}',                              link: `${TWIG_DOCS}/functions/attribute.html` },
    block_func:  { description: 'Renders a block by name (function form)',                            since: '1.0',  example: "{{ block('title') }}",                                      link: `${TWIG_DOCS}/functions/block.html` },
    constant_func: { description: 'Returns the value of a PHP constant',                              since: '1.0',  example: "{{ constant('Post::PUBLISHED') }}",                          link: `${TWIG_DOCS}/functions/constant.html` },
    cycle:       { description: 'Cycles through values',                                              since: '1.0',  example: "{{ cycle(['odd', 'even'], i) }}",                            link: `${TWIG_DOCS}/functions/cycle.html` },
    date_func:   { description: 'Creates a date object (function form)',                              since: '1.0',  example: "{{ date('now') }}",                                         link: `${TWIG_DOCS}/functions/date.html` },
    dump:        { description: 'Dumps variable information for debugging',                           since: '1.0',  example: '{{ dump(user) }}',                                          link: `${TWIG_DOCS}/functions/dump.html` },
    include_func: { description: 'Includes and renders another template',                             since: '1.0',  example: "{{ include('sidebar.html.twig') }}",                         link: `${TWIG_DOCS}/functions/include.html` },
    max:         { description: 'Returns the largest value',                                          since: '1.0',  example: '{{ max(1, 3, 2) }}',                                       link: `${TWIG_DOCS}/functions/max.html` },
    min:         { description: 'Returns the smallest value',                                         since: '1.0',  example: '{{ min(1, 3, 2) }}',                                       link: `${TWIG_DOCS}/functions/min.html` },
    parent:      { description: 'Renders the parent block content',                                   since: '1.0',  example: '{{ parent() }}',                                            link: `${TWIG_DOCS}/functions/parent.html` },
    random:      { description: 'Returns a random value from a sequence',                             since: '1.0',  example: "{{ random(['a', 'b', 'c']) }}",                              link: `${TWIG_DOCS}/functions/random.html` },
    range:       { description: 'Returns a sequence of numbers',                                      since: '1.0',  example: '{% for i in range(0, 3) %}{{ i }}{% endfor %}',             link: `${TWIG_DOCS}/functions/range.html` },
    source:      { description: 'Returns the raw source of a template',                               since: '1.0',  example: "{{ source('template.twig') }}",                             link: `${TWIG_DOCS}/functions/source.html` },
    template_from_string: { description: 'Creates a template from a string',                          since: '1.0',  example: "{{ include(template_from_string('Hello {{ name }}')) }}",    link: `${TWIG_DOCS}/functions/template_from_string.html` },
    path:        { description: '[Symfony] Generates a relative URL path for a route',                since: '—',    example: "{{ path('route_name', {id: 1}) }}",                         link: 'https://symfony.com/doc/current/templates.html#linking-to-pages' },
    url:         { description: '[Symfony] Generates an absolute URL for a route',                    since: '—',    example: "{{ url('route_name', {id: 1}) }}",                          link: 'https://symfony.com/doc/current/templates.html#linking-to-pages' },
    asset:       { description: '[Symfony] Returns the public path of an asset',                      since: '—',    example: "{{ asset('images/logo.png') }}",                            link: 'https://symfony.com/doc/current/templates.html#linking-to-css-javascript-and-image-assets' },
    render:      { description: '[Symfony] Renders a controller fragment inline',                     since: '—',    example: "{{ render(controller('App\\\\Controller\\\\FooController::recent')) }}", link: 'https://symfony.com/doc/current/templates.html#embedding-controllers' },
    csrf_token:  { description: '[Symfony] Generates a CSRF token',                                   since: '—',    example: "{{ csrf_token('authenticate') }}",                          link: 'https://symfony.com/doc/current/security/csrf.html' },
    is_granted:  { description: '[Symfony] Checks if the current user has a given role',              since: '—',    example: "{{ is_granted('ROLE_ADMIN') }}",                            link: 'https://symfony.com/doc/current/security.html' },

    // Tests
    constant:    { description: 'Checks if a variable has the same value as a PHP constant',          since: '1.0',  example: "{% if post.status is constant('Post::PUBLISHED') %}",       link: `${TWIG_DOCS}/tests/constant.html` },
    defined:     { description: 'Checks if a variable is defined',                                    since: '1.0',  example: '{% if users is defined %}',                                 link: `${TWIG_DOCS}/tests/defined.html` },
    divisibleby: { description: 'Checks if a value is divisible by another number',                   since: '1.0',  example: '{% if i is divisibleby(2) %}',                              link: `${TWIG_DOCS}/tests/divisibleby.html` },
    empty:       { description: 'Checks if a sequence or mapping is empty',                           since: '1.0',  example: '{% if posts is empty %}',                                   link: `${TWIG_DOCS}/tests/empty.html` },
    even:        { description: 'Checks if a number is even',                                         since: '1.0',  example: '{% if i is even %}',                                       link: `${TWIG_DOCS}/tests/even.html` },
    iterable:    { description: 'Checks if a variable is iterable',                                   since: '1.0',  example: '{% if var is iterable %}',                                  link: `${TWIG_DOCS}/tests/iterable.html` },
    mapping:     { description: 'Checks if a variable is a mapping (key-value)',                      since: '3.14', example: '{% if x is mapping %}',                                   link: `${TWIG_DOCS}/tests/mapping.html` },
    null:        { description: 'Checks if a variable is null',                                       since: '1.0',  example: '{% if var is null %}',                                      link: `${TWIG_DOCS}/tests/null.html` },
    odd:         { description: 'Checks if a number is odd',                                          since: '1.0',  example: '{% if i is odd %}',                                        link: `${TWIG_DOCS}/tests/odd.html` },
    sameas:      { description: 'Checks if two values are strictly equal (===)',                      since: '1.0',  example: '{% if a is sameas(b) %}',                                   link: `${TWIG_DOCS}/tests/sameas.html` },
    sequence:    { description: 'Checks if a variable is a sequence (list)',                          since: '3.14', example: '{% if x is sequence %}',                                  link: `${TWIG_DOCS}/tests/sequence.html` },

    // Operators
    'not in':    { description: 'Negated containment test — checks if left operand is NOT in right',  since: '1.0',  example: '{% if 1 not in [2, 3] %}',                                  link: `${TWIG_DOCS}/templates.html#containment-operators` },
    'starts with': { description: 'Checks if a string starts with a given prefix',                    since: '1.0',  example: "{% if 'Fabien' starts with 'F' %}",                        link: `${TWIG_DOCS}/templates.html#containment-operators` },
    'ends with': { description: 'Checks if a string ends with a given suffix',                        since: '1.0',  example: "{% if 'Fabien' ends with 'n' %}",                          link: `${TWIG_DOCS}/templates.html#containment-operators` },
    matches:     { description: 'Checks if a string matches a regular expression',                    since: '1.0',  example: "{% if phone matches '/^[\\\\d.]+$/' %}",                    link: `${TWIG_DOCS}/templates.html#containment-operators` },
    'has some':  { description: 'Checks if an iterable has at least one element satisfying a test',   since: '3.x',  example: '{% if sizes has some v => v > 38 %}',                       link: `${TWIG_DOCS}/templates.html#iterable-operators` },
    'has every': { description: 'Checks if every element of an iterable satisfies a test',            since: '3.x',  example: '{% if sizes has every v => v > 38 %}',                      link: `${TWIG_DOCS}/templates.html#iterable-operators` },


    // -- Additional filters --
    column:      { description: 'Returns a column from a nested array/object',                     since: '2.8',  example: '{{ rows|column(0) }}',                                        link: `${TWIG_DOCS}/filters/column.html` },
    country_name: { description: 'Returns the country name for a country code',                     since: '2.12', example: "{{ 'FR'|country_name }}",                                     link: `${TWIG_DOCS}/filters/country_name.html` },
    currency_name: { description: 'Returns the currency name for a currency code',                  since: '2.12', example: "{{ 'EUR'|currency_name }}",                                   link: `${TWIG_DOCS}/filters/currency_name.html` },
    currency_symbol: { description: 'Returns the currency symbol for a currency code',              since: '2.12', example: "{{ 'EUR'|currency_symbol }}",                                 link: `${TWIG_DOCS}/filters/currency_symbol.html` },
    data_uri:    { description: 'Converts a file to a data URI',                                    since: '1.0',  example: '{{ image|data_uri }}',                                         link: `${TWIG_DOCS}/filters/data_uri.html` },
    date_modify: { description: 'Modifies a date with a relative format string',                    since: '1.0',  example: "{{ date|date_modify('+1 day') }}",                              link: `${TWIG_DOCS}/filters/date_modify.html` },
    filter:      { description: 'Applies a filter to each element of a sequence',                   since: '2.9',  example: '{{ items|filter(v => v.active) }}',                             link: `${TWIG_DOCS}/filters/filter.html` },
    find:        { description: 'Finds the first element matching an arrow function',               since: '3.2',  example: '{{ items|find(v => v.active) }}',                               link: `${TWIG_DOCS}/filters/find.html` },
    format_currency: { description: 'Formats a number as currency (Intl-based)',                    since: '2.12', example: "{{ price|format_currency('EUR') }}",                            link: `${TWIG_DOCS}/filters/format_currency.html` },
    format_date: { description: 'Formats a date (Intl-based)',                                      since: '2.12', example: "{{ date|format_date('long') }}",                                link: `${TWIG_DOCS}/filters/format_date.html` },
    format_datetime: { description: 'Formats a datetime (Intl-based)',                              since: '2.12', example: "{{ date|format_datetime('long', 'short') }}",                  link: `${TWIG_DOCS}/filters/format_datetime.html` },
    format_number: { description: 'Formats a number (Intl-based)',                                  since: '2.12', example: '{{ price|format_number }}',                                     link: `${TWIG_DOCS}/filters/format_number.html` },
    format_time: { description: 'Formats a time (Intl-based)',                                      since: '2.12', example: "{{ time|format_time('short') }}",                               link: `${TWIG_DOCS}/filters/format_time.html` },
    html_attr_merge: { description: 'Merges HTML attribute-value pairs',                            since: '3.18', example: '{{ attrs|html_attr_merge }}',                                   link: `${TWIG_DOCS}/filters/html_attr_merge.html` },
    html_attr_type: { description: 'Detects the type of an HTML attribute value',                   since: '3.18', example: "{{ 'text'|html_attr_type }}",                                   link: `${TWIG_DOCS}/filters/html_attr_type.html` },
    html_to_markdown: { description: 'Converts HTML to Markdown',                                   since: '2.12', example: '{{ html|html_to_markdown }}',                                    link: `${TWIG_DOCS}/filters/html_to_markdown.html` },
    inky_to_html: { description: 'Converts Inky (Foundation for Emails) to HTML',                   since: '2.12', example: '{{ email|inky_to_html }}',                                      link: `${TWIG_DOCS}/filters/inky_to_html.html` },
    inline_css:  { description: 'Inlines CSS styles into HTML elements',                            since: '3.10', example: '{{ html|inline_css }}',                                          link: `${TWIG_DOCS}/filters/inline_css.html` },
    invoke:      { description: 'Calls an arrow function with arguments',                           since: '3.19', example: '{{ fn|invoke(arg1, arg2) }}',                                   link: `${TWIG_DOCS}/filters/invoke.html` },
    language_name: { description: 'Returns the language name for a locale code',                    since: '2.12', example: "{{ 'fr'|language_name }}",                                      link: `${TWIG_DOCS}/filters/language_name.html` },
    locale_name: { description: 'Returns the locale name for a locale code',                        since: '2.12', example: "{{ 'fr_FR'|locale_name }}",                                     link: `${TWIG_DOCS}/filters/locale_name.html` },
    map:         { description: 'Applies an arrow function to each element of a sequence',          since: '2.9',  example: '{{ people|map(p => p.first_name)|join(", ") }}',               link: `${TWIG_DOCS}/filters/map.html` },
    markdown_to_html: { description: 'Converts Markdown to HTML',                                   since: '2.12', example: '{{ text|markdown_to_html }}',                                    link: `${TWIG_DOCS}/filters/markdown_to_html.html` },
    plural:      { description: 'Converts a noun to its plural form',                               since: '3.16', example: "{{ 'person'|plural }}",                                         link: `${TWIG_DOCS}/filters/plural.html` },
    reduce:      { description: 'Reduces a sequence to a single value via an arrow function',       since: '2.9',  example: '{{ items|reduce((carry, v) => carry + v) }}',                    link: `${TWIG_DOCS}/filters/reduce.html` },
    shuffle:     { description: 'Randomly shuffles the elements of a sequence',                     since: '3.16', example: '{{ items|shuffle }}',                                           link: `${TWIG_DOCS}/filters/shuffle.html` },
    singular:    { description: 'Converts a noun to its singular form',                             since: '3.16', example: "{{ 'people'|singular }}",                                       link: `${TWIG_DOCS}/filters/singular.html` },
    slug:        { description: 'Converts a string to a URL-safe slug',                             since: '1.0',  example: "{{ 'Hello World'|slug }}",                                      link: `${TWIG_DOCS}/filters/slug.html` },
    timezone_name: { description: 'Returns the timezone name for a timezone code',                  since: '2.12', example: "{{ 'Europe/Paris'|timezone_name }}",                            link: `${TWIG_DOCS}/filters/timezone_name.html` },
    u:           { description: 'Shortcut for Unicode-aware string conversion',                     since: '2.12', example: "{{ 'Hello'|u }}",                                              link: `${TWIG_DOCS}/filters/u.html` },

    // -- Additional functions --
    country_names: { description: 'Returns all country names keyed by country code',                since: '3.12', example: '{{ country_names() }}',                                         link: `${TWIG_DOCS}/functions/country_names.html` },
    country_timezones: { description: 'Returns all timezones for a given country code',             since: '3.12', example: "{{ country_timezones('FR') }}",                                 link: `${TWIG_DOCS}/functions/country_timezones.html` },
    currency_names: { description: 'Returns all currency names keyed by currency code',             since: '3.12', example: '{{ currency_names() }}',                                        link: `${TWIG_DOCS}/functions/currency_names.html` },
    enum:        { description: 'Creates an enum instance from a fully qualified class name',        since: '3.15', example: "{{ enum('App\\Enum\\Status') }}",                            link: `${TWIG_DOCS}/functions/enum.html` },
    enum_cases:  { description: 'Returns all cases of an enum',                                     since: '3.17', example: "{{ enum_cases('App\\Enum\\Status') }}",                      link: `${TWIG_DOCS}/functions/enum_cases.html` },
    html_attr:   { description: 'Generates HTML attribute-value pairs from a mapping',              since: '3.18', example: "{{ html_attr({class: 'btn', id: 'submit'}) }}",                  link: `${TWIG_DOCS}/functions/html_attr.html` },
    html_classes: { description: 'Generates CSS class strings with conditional logic',              since: '3.17', example: "{{ html_classes('btn', {primary: isPrimary}) }}",                link: `${TWIG_DOCS}/functions/html_classes.html` },
    html_cva:    { description: 'Class Variance Authority — generates class strings with variants', since: '3.17', example: "{{ html_cva({base: 'btn', variants: {size: {sm: 'btn-sm'}}}) }}", link: `${TWIG_DOCS}/functions/html_cva.html` },
    language_names: { description: 'Returns all language names keyed by language code',             since: '3.12', example: '{{ language_names() }}',                                        link: `${TWIG_DOCS}/functions/language_names.html` },
    locale_names: { description: 'Returns all locale names keyed by locale code',                   since: '3.12', example: '{{ locale_names() }}',                                          link: `${TWIG_DOCS}/functions/locale_names.html` },
    script_names: { description: 'Returns all script names keyed by script code',                   since: '3.12', example: '{{ script_names() }}',                                          link: `${TWIG_DOCS}/functions/script_names.html` },
    timezone_names: { description: 'Returns all timezone names keyed by timezone code',             since: '3.12', example: '{{ timezone_names() }}',                                        link: `${TWIG_DOCS}/functions/timezone_names.html` },

    // -- Additional tests --
    'divisible by': { description: 'Checks if a value is divisible by a number (multi-word)',       since: '1.0',  example: '{% if i is divisible by 2 %}',                                  link: `${TWIG_DOCS}/tests/divisibleby.html` },
    'same as':    { description: 'Checks if two values are strictly equal (===) (multi-word)',      since: '1.0',  example: '{% if a is same as(b) %}',                                      link: `${TWIG_DOCS}/tests/sameas.html` },

};

const END_TAG_MAP: Record<string, string> = {
    apply: 'endapply', autoescape: 'endautoescape', block: 'endblock',
    cache: 'endcache', deprecated: 'enddeprecated', embed: 'endembed',
    for: 'endfor', guard: 'endguard', if: 'endif', macro: 'endmacro',
    sandbox: 'endsandbox', set: 'endset', types: 'endtypes',
    verbatim: 'endverbatim', with: 'endwith',
};

// Add end tag entries
for (const [start, end] of Object.entries(END_TAG_MAP)) {
    BUILTIN_HOVER_DATA[end] = {
        description: `Closes a \`{% ${start} %}\` block`,
        since: '—',
        example: `{% ${end} %}`,
        link: BUILTIN_HOVER_DATA[start]?.link ?? `${TWIG_DOCS}/tags/${start}.html`,
    };
}

class TwigHoverProvider implements vscode.HoverProvider {
    provideHover(
        document: vscode.TextDocument,
        position: vscode.Position,
    ): vscode.ProviderResult<vscode.Hover> {
        const range = document.getWordRangeAtPosition(position, /[\w.]+/);
        if (range === undefined) return null;

        const word = document.getText(range);

        // Check for filter: word after |
        const linePrefix = document.lineAt(position).text.substring(0, position.character);
        const filterMatch = linePrefix.match(/\|\s*([\w.]+)$/);
        const lookup = filterMatch !== null ? filterMatch[1] : word;

        const entry = BUILTIN_HOVER_DATA[lookup];
        if (entry === undefined) return null;

        const content = new vscode.MarkdownString(
            `### \`${lookup}\`\n\n${entry.description}\n\n` +
            `> Since Twig ${entry.since}  \n` +
            `> Example: \`${entry.example}\`  \n\n` +
            `[Twig Docs](${entry.link})`,
        );
        content.isTrusted = true;

        return new vscode.Hover(content, range);
    }
}

// ═══════════════════════════════════════════════════════════════════════
// 11. Definition provider — go-to template for extends/include/embed
// ═══════════════════════════════════════════════════════════════════════

const TEMPLATE_PATH_TAGS = new Set(['extends', 'include', 'embed', 'import', 'from', 'use']);

class TwigDefinitionProvider implements vscode.DefinitionProvider {
    provideDefinition(
        document: vscode.TextDocument,
        position: vscode.Position,
    ): vscode.ProviderResult<vscode.Definition | vscode.LocationLink[]> {
        const line = document.lineAt(position).text;
        const beforeCursor = line.substring(0, position.character);
        const afterCursor = line.substring(position.character);

        console.log('[twig-def] line:', line);
        console.log('[twig-def] before:', beforeCursor);

        // Match {% tagname 'path' %} or {% tagname "path" %}
        const tagMatch = beforeCursor.match(/\{%\s*(\w+)\s*(['"])([^'"]*)$/);
        if (tagMatch === null) {
            console.log('[twig-def] no tag match');
            return null;
        }

        const tagName = tagMatch[1];
        const partialPath = tagMatch[3];
        console.log('[twig-def] tag:', tagName, 'partial:', partialPath);

        if (!TEMPLATE_PATH_TAGS.has(tagName)) return null;

        // Get the rest of the path after cursor
        const restMatch = afterCursor.match(/^([^'"]*)(['"])/);
        const fullPath = restMatch !== null
            ? partialPath + restMatch[1]
            : partialPath + afterCursor.replace(/['"].*$/, '');

        console.log('[twig-def] fullPath:', fullPath);

        const resolvedUri = this.resolveTemplatePath(document.uri, fullPath);
        if (resolvedUri === undefined) {
            console.log('[twig-def] not resolved');
            return null;
        }

        console.log('[twig-def] resolved:', resolvedUri.fsPath);
        return new vscode.Location(resolvedUri, new vscode.Position(0, 0));
    }

    private resolveTemplatePath(baseUri: vscode.Uri, templatePath: string): vscode.Uri | undefined {
        // Remove quotes if present
        const clean = templatePath.replace(/^['"]|['"]$/g, '');

        // Strategy 1: Relative to current file
        const baseDir = path.dirname(baseUri.fsPath);
        const relative = path.join(baseDir, clean);
        if (fs.existsSync(relative)) {
            return vscode.Uri.file(relative);
        }

        // Strategy 2: Try with .twig extension
        if (!clean.endsWith('.twig') && !clean.endsWith('.html.twig')) {
            const withTwig = path.join(baseDir, clean + '.twig');
            if (fs.existsSync(withTwig)) {
                return vscode.Uri.file(withTwig);
            }
            const withHtmlTwig = path.join(baseDir, clean + '.html.twig');
            if (fs.existsSync(withHtmlTwig)) {
                return vscode.Uri.file(withHtmlTwig);
            }
        }

        // Strategy 3: Relative to workspace templates/ directory
        const workspaceFolders = vscode.workspace.workspaceFolders;
        if (workspaceFolders !== undefined) {
            for (const folder of workspaceFolders) {
                const templateDir = path.join(folder.uri.fsPath, 'templates', clean);
                if (fs.existsSync(templateDir)) {
                    return vscode.Uri.file(templateDir);
                }
                if (!clean.endsWith('.twig')) {
                    const withExt = path.join(folder.uri.fsPath, 'templates', clean + '.twig');
                    if (fs.existsSync(withExt)) return vscode.Uri.file(withExt);
                    const withHtmlExt = path.join(folder.uri.fsPath, 'templates', clean + '.html.twig');
                    if (fs.existsSync(withHtmlExt)) return vscode.Uri.file(withHtmlExt);
                }
            }
        }

        return undefined;
    }
}
