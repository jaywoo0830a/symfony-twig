import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { execFile } from 'child_process';
import { promisify } from 'util';

const execFileAsync = promisify(execFile);

// ---- Resolve analyzer command ----

function getAnalyzerCommand(): { cmd: string; args: string[]; env: NodeJS.ProcessEnv } {
    const config = vscode.workspace.getConfiguration('twigAnalyzer');

    // Strategy 1: User-configured pythonPath
    const configured = config.get<string>('pythonPath', '');
    if (configured && fs.existsSync(configured)) {
        return { cmd: configured, args: ['-m', 'twig_analyzer'], env: { ...process.env } };
    }

    const extDir = path.resolve(__dirname, '..'); // twig-static-analyzer/
    const homeDir = process.env.HOME || '/home/rlawjddn';

    // Strategy 2: Known project venv
    const candidates = [
        path.join(homeDir, 'symfony-twig', '.venv', 'bin', 'python3'),
        path.join(homeDir, 'symfony-twig', '.venv', 'bin', 'python'),
    ];
    for (const python of candidates) {
        if (fs.existsSync(python)) {
            // Use the project's installed twig_analyzer
            return { cmd: python, args: ['-m', 'twig_analyzer'], env: { ...process.env } };
        }
    }

    // Strategy 3: python3 on PATH, with extension dir as fallback
    const env = { ...process.env };
    const twigPath = path.join(extDir, 'twig_analyzer');
    if (fs.existsSync(twigPath)) {
        env.PYTHONPATH = extDir + (env.PYTHONPATH ? ':' + env.PYTHONPATH : '');
    }

    return { cmd: 'python3', args: ['-m', 'twig_analyzer'], env };
}

// ---- LSP-compatible types (matches twig_analyzer.diagnostics output) ----

interface LspPosition {
    line: number;      // 0-indexed
    character: number; // 0-indexed
}

interface LspRange {
    start: LspPosition;
    end: LspPosition;
}

interface LspDiagnostic {
    message: string;
    severity: number;  // 1=Error, 2=Warning, 3=Info, 4=Hint
    range: LspRange;
    code: string;
    source: string;
}

interface AnalyzerOutput {
    files: Record<string, LspDiagnostic[]>;
    diagnostics: LspDiagnostic[];
    summary: {
        total: number;
        errors: number;
        warnings: number;
        info: number;
        hints: number;
    };
}

// ---- Diagnostics Collection ----

const diagnosticCollection = vscode.languages.createDiagnosticCollection('twig-analyzer');

// ---- Extension Activation ----

export function activate(context: vscode.ExtensionContext) {
    console.log('Twig Static Analyzer is now active');

    // Register command: manual analysis
    const analyzeCmd = vscode.commands.registerCommand('twig-analyzer.analyze', () => {
        const editor = vscode.window.activeTextEditor;
        if (editor) {
            analyzeDocument(editor.document);
        }
    });
    context.subscriptions.push(analyzeCmd);

    // Watch for file changes
    const config = vscode.workspace.getConfiguration('twigAnalyzer');

    if (config.get<boolean>('runOnOpen', true)) {
        // Analyze currently open files on activation
        vscode.window.visibleTextEditors.forEach(editor => {
            if (isTwigFile(editor.document)) {
                analyzeDocument(editor.document);
            }
        });
    }

    // Analyze on file open
    context.subscriptions.push(
        vscode.window.onDidChangeActiveTextEditor(editor => {
            if (editor && config.get<boolean>('runOnOpen', true)) {
                if (isTwigFile(editor.document)) {
                    analyzeDocument(editor.document);
                }
            }
        })
    );

    // Analyze on save
    context.subscriptions.push(
        vscode.workspace.onDidSaveTextDocument(document => {
            if (config.get<boolean>('runOnSave', true)) {
                if (isTwigFile(document)) {
                    analyzeDocument(document);
                }
            }
        })
    );

    // Analyze on change (debounced)
    let changeTimer: NodeJS.Timeout | undefined;
    context.subscriptions.push(
        vscode.workspace.onDidChangeTextDocument(event => {
            if (config.get<boolean>('runOnSave', true)) {
                return; // Only run on save
            }
            if (!isTwigFile(event.document)) {
                return;
            }
            if (changeTimer) {
                clearTimeout(changeTimer);
            }
            changeTimer = setTimeout(() => {
                analyzeDocument(event.document);
            }, 1000);
        })
    );

    // Clean up on close
    context.subscriptions.push(
        vscode.workspace.onDidCloseTextDocument(document => {
            diagnosticCollection.delete(document.uri);
        })
    );

    // Status bar item
    const statusBarItem = vscode.window.createStatusBarItem(
        vscode.StatusBarAlignment.Right, 100
    );
    statusBarItem.command = 'twig-analyzer.analyze';
    statusBarItem.text = '$(check) Twig';
    statusBarItem.tooltip = 'Twig Static Analyzer';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    // ---- Formatting Provider ----
    const formattingProvider = vscode.languages.registerDocumentFormattingEditProvider(
        { language: 'twig', scheme: 'file' },
        new TwigFormattingProvider()
    );
    context.subscriptions.push(formattingProvider);

    // Also register for HTML files that are actually Twig
    const htmlFormattingProvider = vscode.languages.registerDocumentFormattingEditProvider(
        { language: 'html', scheme: 'file' },
        new TwigFormattingProvider()
    );
    context.subscriptions.push(htmlFormattingProvider);
}

export function deactivate() {
    diagnosticCollection.clear();
}

// ---- Core Logic ----

function isTwigFile(document: vscode.TextDocument): boolean {
    const config = vscode.workspace.getConfiguration('twigAnalyzer');
    const extensions: string[] = config.get('fileExtensions', ['.twig', '.html.twig']);

    if (document.languageId === 'twig') {
        return true;
    }

    // Check file extensions
    for (const ext of extensions) {
        if (document.fileName.endsWith(ext)) {
            return true;
        }
    }

    return false;
}

async function analyzeDocument(document: vscode.TextDocument): Promise<void> {
    const config = vscode.workspace.getConfiguration('twigAnalyzer');

    if (!config.get<boolean>('enabled', true)) {
        diagnosticCollection.delete(document.uri);
        return;
    }

    try {
        const filePath = document.uri.fsPath;
        const analyzerArgs = buildAnalyzerArgs();
        const commonArgs = [...analyzerArgs, '--format', 'json', filePath];

        const { cmd, args, env } = getAnalyzerCommand();
        const allArgs = [...args, ...commonArgs];

        console.log(`[twig-analyzer] ${cmd} ${allArgs.join(' ')}`);

        const { stdout, stderr } = await execFileAsync(cmd, allArgs, {
            timeout: 30000,
            maxBuffer: 10 * 1024 * 1024,
            env: env,
        });

        if (stderr && stderr.trim()) {
            console.warn('twig-analyzer stderr:', stderr);
        }

        const output: AnalyzerOutput = JSON.parse(stdout);
        const fileDiags = output.files[filePath];

        if (fileDiags) {
            const vsDiags: vscode.Diagnostic[] = fileDiags.map(d =>
                lspToVsCodeDiagnostic(d, document)
            );
            diagnosticCollection.set(document.uri, vsDiags);
        } else {
            diagnosticCollection.delete(document.uri);
        }

    } catch (err: any) {
        const homeDir = process.env.HOME || '~';
        if (err.code === 'ENOENT') {
            vscode.window.showErrorMessage(
                `Twig Analyzer: python3 not found or twig_analyzer not installed.\n` +
                `Run: bash ${homeDir}/symfony-twig/vscode-extension/install.sh`
            );
        } else if (err.killed) {
            console.warn('[twig-analyzer] Timed out');
        } else if (err.stderr && err.stderr.includes('No module named')) {
            vscode.window.showErrorMessage(
                `Twig Analyzer: twig_analyzer module not found.\n` +
                `Run: bash ${homeDir}/symfony-twig/vscode-extension/install.sh`
            );
        } else {
            console.error('[twig-analyzer] Error:', err.message || err);
        }
    }
}

function buildAnalyzerArgs(): string[] {
    const config = vscode.workspace.getConfiguration('twigAnalyzer');
    const args: string[] = [];

    // Disabled rules
    const disabledRules: string[] = config.get('disabledRules', []);
    if (disabledRules.length > 0) {
        args.push('--disable', disabledRules.join(','));
    }

    // Severity overrides
    const severityOverrides: Record<string, string> = config.get('severityOverrides', {});
    for (const [ruleId, severity] of Object.entries(severityOverrides)) {
        args.push('--severity', `${ruleId}=${severity}`);
    }

    return args;
}

function lspToVsCodeDiagnostic(
    lspDiag: LspDiagnostic,
    document: vscode.TextDocument
): vscode.Diagnostic {
    // Convert LSP severity to VS Code severity
    const severityMap: Record<number, vscode.DiagnosticSeverity> = {
        1: vscode.DiagnosticSeverity.Error,
        2: vscode.DiagnosticSeverity.Warning,
        3: vscode.DiagnosticSeverity.Information,
        4: vscode.DiagnosticSeverity.Hint,
    };

    const range = new vscode.Range(
        new vscode.Position(lspDiag.range.start.line, lspDiag.range.start.character),
        new vscode.Position(lspDiag.range.end.line, lspDiag.range.end.character)
    );

    const diag = new vscode.Diagnostic(
        range,
        lspDiag.message,
        severityMap[lspDiag.severity] || vscode.DiagnosticSeverity.Warning
    );

    diag.source = lspDiag.source || 'twig-analyzer';
    diag.code = lspDiag.code;

    return diag;
}

// ---- Formatting Provider ----

class TwigFormattingProvider implements vscode.DocumentFormattingEditProvider {
    async provideDocumentFormattingEdits(
        document: vscode.TextDocument,
        options: vscode.FormattingOptions,
        token: vscode.CancellationToken
    ): Promise<vscode.TextEdit[]> {
        const { cmd, args, env } = getAnalyzerCommand();

        try {
            const filePath = document.uri.fsPath;
            const { stdout } = await execFileAsync(cmd, [...args, 'format', filePath, '--check'], {
                timeout: 30000,
                env: env,
            });

            // If the CLI says "Would reformat", we need to do the formatting ourselves
            // Otherwise, call format without --check to get the actual formatted output
            // Fallback: use built-in formatter directly
            const formatted = await this.formatWithCli(cmd, args, env, document);
            if (formatted === null) {
                return [];
            }

            const fullRange = new vscode.Range(
                document.positionAt(0),
                document.positionAt(document.getText().length)
            );

            return [vscode.TextEdit.replace(fullRange, formatted)];

        } catch (err: any) {
            console.error('[twig-format] Error:', err.message || err);
            return [];
        }
    }

    private async formatWithCli(
        cmd: string, args: string[], env: NodeJS.ProcessEnv, document: vscode.TextDocument
    ): Promise<string | null> {
        // Write temp file, format it, read it back
        const tmp = require('os').tmpdir();
        const tmpFile = require('path').join(tmp, `twig-fmt-${Date.now()}.twig`);

        try {
            require('fs').writeFileSync(tmpFile, document.getText(), 'utf-8');

            await execFileAsync(cmd, [...args, 'format', tmpFile], {
                timeout: 30000,
                env: env,
            });

            return require('fs').readFileSync(tmpFile, 'utf-8');
        } catch {
            return null;
        } finally {
            try { require('fs').unlinkSync(tmpFile); } catch {}
        }
    }
}
